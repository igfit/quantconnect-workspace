"""
Momentum Burst Strategy

Captures explosive momentum moves in high-beta stocks.
Enters on strong momentum confirmation, rides the trend with trailing stop.

Universe: High-Beta Growth (Universe D)
Rebalance: Weekly scan, daily stops
Target: 30%+ CAGR with high-conviction entries

WHY THIS WORKS:
- High-beta stocks have larger price swings
- Momentum bursts often continue for weeks
- Quick entries capture the meat of the move
- Trailing stops protect gains

KEY PARAMETERS:
- ROC_PERIOD = 20 (rate of change)
- ROC_THRESHOLD = 15% (minimum momentum burst)
- ATR_STOP = 2.5 (trailing stop distance)
- MAX_POSITIONS = 5 (concentrated)
"""

from AlgorithmImports import *
from datetime import timedelta


class MomentumBurst(QCAlgorithm):
    """
    Momentum Burst on High-Beta Universe

    Rules:
    1. Weekly scan for stocks with ROC(20) > 15%
    2. Enter top 5 by momentum strength
    3. Trail stop at 2.5 ATR below high
    4. No regime filter - ride momentum
    """

    # Configuration
    ROC_PERIOD = 20
    ROC_THRESHOLD = 15  # Minimum 15% move in 20 days
    ATR_PERIOD = 14
    ATR_STOP = 2.5
    MAX_POSITIONS = 5
    USE_REGIME_FILTER = False

    def initialize(self):
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # High-beta universe
        self.universe_symbols = [
            # Highest beta tech
            "NVDA", "AMD", "TSLA", "SQ", "SHOP", "NFLX", "META",
            # Semiconductors
            "MU", "AVGO", "MRVL", "AMAT", "LRCX",
            # Growth tech
            "CRM", "ADBE", "NOW", "PANW",
            # Biotech
            "MRNA", "REGN", "VRTX", "BIIB",
            # Energy/Materials
            "FSLR", "ENPH", "FCX",
            # Consumer
            "LULU", "RCL", "WYNN",
            # Established growth
            "AMZN", "GOOGL", "AAPL", "MSFT",
        ]

        self.stocks = []
        self.roc_indicators = {}
        self.atr_indicators = {}

        for ticker in self.universe_symbols:
            try:
                equity = self.add_equity(ticker, Resolution.DAILY)
                equity.set_slippage_model(ConstantSlippageModel(0.001))
                equity.set_fee_model(InteractiveBrokersFeeModel())
                symbol = equity.symbol
                self.stocks.append(symbol)
                self.roc_indicators[symbol] = self.rocp(symbol, self.ROC_PERIOD, Resolution.DAILY)
                self.atr_indicators[symbol] = self.atr(symbol, self.ATR_PERIOD)
            except:
                pass

        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.set_benchmark(self.spy)
        self.spy_sma = self.sma(self.spy, 200, Resolution.DAILY)

        self.positions = {}
        self.completed_trades = []

        self.set_warmup(timedelta(days=30))

        # Weekly scan for new entries
        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.after_market_open(self.spy, 30),
            self.scan_for_entries
        )

        # Daily stop check
        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.before_market_close(self.spy, 5),
            self.check_stops
        )

    def scan_for_entries(self):
        if self.is_warming_up:
            return

        # Optional regime filter
        if self.USE_REGIME_FILTER and self.spy_sma.is_ready:
            if self.securities[self.spy].price < self.spy_sma.current.value:
                return

        # Find momentum burst candidates
        candidates = []
        for symbol in self.stocks:
            if symbol in self.positions:
                continue

            roc = self.roc_indicators.get(symbol)
            if roc is None or not roc.is_ready:
                continue

            roc_value = roc.current.value * 100  # Convert to percentage

            if roc_value > self.ROC_THRESHOLD:
                candidates.append((symbol, roc_value))

        if not candidates:
            return

        # Sort by momentum (strongest first)
        candidates.sort(key=lambda x: x[1], reverse=True)

        # Enter positions
        positions_to_add = self.MAX_POSITIONS - len(self.positions)
        for symbol, roc_value in candidates[:positions_to_add]:
            self.enter_position(symbol, roc_value)

    def enter_position(self, symbol, roc_value: float):
        price = self.securities[symbol].price
        atr = self.atr_indicators[symbol].current.value if self.atr_indicators[symbol].is_ready else price * 0.03

        initial_stop = price - (self.ATR_STOP * atr)

        weight = 0.99 / self.MAX_POSITIONS
        self.set_holdings(symbol, weight)

        self.positions[symbol] = {
            'entry_price': price,
            'entry_date': self.time,
            'entry_roc': roc_value,
            'highest_price': price,
            'trailing_stop': initial_stop,
        }

        self.log(f"ENTRY: {symbol} @ ${price:.2f} | ROC={roc_value:.1f}% | Stop=${initial_stop:.2f}")

    def check_stops(self):
        if self.is_warming_up:
            return

        for symbol in list(self.positions.keys()):
            pos = self.positions[symbol]
            price = self.securities[symbol].price
            atr = self.atr_indicators[symbol].current.value if self.atr_indicators[symbol].is_ready else price * 0.03

            # Update trailing stop
            if price > pos['highest_price']:
                pos['highest_price'] = price
                new_stop = price - (self.ATR_STOP * atr)
                if new_stop > pos['trailing_stop']:
                    pos['trailing_stop'] = new_stop

            # Check stop
            if price < pos['trailing_stop']:
                self.exit_position(symbol, f"Trailing stop @ ${pos['trailing_stop']:.2f}")

    def exit_position(self, symbol, reason: str):
        if symbol not in self.positions:
            return

        pos = self.positions[symbol]
        exit_price = self.securities[symbol].price
        pnl_pct = (exit_price - pos['entry_price']) / pos['entry_price']
        days_held = (self.time - pos['entry_date']).days

        self.liquidate(symbol)

        self.completed_trades.append({
            'symbol': str(symbol),
            'entry_date': str(pos['entry_date'].date()),
            'exit_date': str(self.time.date()),
            'entry_price': pos['entry_price'],
            'exit_price': exit_price,
            'pnl_pct': pnl_pct,
            'days_held': days_held,
        })

        self.log(f"EXIT: {symbol} | {reason} | P&L={pnl_pct*100:.1f}% | Days={days_held}")
        del self.positions[symbol]

    def on_end_of_algorithm(self):
        self.log("=" * 60)
        self.log("MOMENTUM BURST - SUMMARY")
        self.log("=" * 60)

        if not self.completed_trades:
            self.log("No completed trades")
            return

        total = len(self.completed_trades)
        winners = [t for t in self.completed_trades if t['pnl_pct'] > 0]
        losers = [t for t in self.completed_trades if t['pnl_pct'] <= 0]

        win_rate = len(winners) / total * 100
        avg_win = sum(t['pnl_pct'] for t in winners) / len(winners) * 100 if winners else 0
        avg_loss = sum(t['pnl_pct'] for t in losers) / len(losers) * 100 if losers else 0

        self.log(f"Total Trades: {total}")
        self.log(f"Win Rate: {win_rate:.1f}%")
        self.log(f"Avg Win: {avg_win:.1f}% | Avg Loss: {avg_loss:.1f}%")
        if avg_loss != 0:
            self.log(f"R:R: {abs(avg_win/avg_loss):.2f}")

    def on_data(self, data):
        pass
