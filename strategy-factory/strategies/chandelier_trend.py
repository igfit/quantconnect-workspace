"""
Chandelier Exit Trend Following Strategy

Uses Chandelier Exit (ATR-based trailing stop from highest high)
to ride strong trends in high-beta stocks.

Universe: High-Beta Growth (Universe D)
Target: 30%+ CAGR with trend riding

WHY THIS WORKS:
- Chandelier stops let winners run while cutting losers
- High-beta stocks have larger trends to capture
- ATR-based stops adapt to volatility
- Concentrated positions maximize winning trades
"""

from AlgorithmImports import *
from datetime import timedelta


class ChandelierTrend(QCAlgorithm):
    """
    Chandelier Exit Trend Following

    Rules:
    1. Enter on momentum breakout (price > 20-day high)
    2. Chandelier stop at highest high - 3 ATR
    3. Let winners run until stopped out
    4. Concentrated 5-position portfolio
    """

    # Configuration
    ENTRY_PERIOD = 20
    ATR_PERIOD = 22
    CHANDELIER_MULT = 3.0  # ATR multiplier for stop
    MAX_POSITIONS = 5

    def initialize(self):
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # High-beta universe
        self.universe_symbols = [
            "NVDA", "AMD", "TSLA", "SQ", "SHOP", "NFLX", "META",
            "MU", "AVGO", "MRVL", "AMAT", "LRCX",
            "CRM", "ADBE", "NOW", "PANW",
            "MRNA", "REGN", "VRTX",
            "FSLR", "ENPH", "FCX",
            "LULU", "RCL",
            "AMZN", "GOOGL", "AAPL", "MSFT",
        ]

        self.stocks = []
        self.atr_indicators = {}
        self.highest_high = {}

        for ticker in self.universe_symbols:
            try:
                equity = self.add_equity(ticker, Resolution.DAILY)
                equity.set_slippage_model(ConstantSlippageModel(0.001))
                equity.set_fee_model(InteractiveBrokersFeeModel())
                symbol = equity.symbol
                self.stocks.append(symbol)
                self.atr_indicators[symbol] = self.atr(symbol, self.ATR_PERIOD)
                self.highest_high[symbol] = 0
            except:
                pass

        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.set_benchmark(self.spy)

        self.positions = {}
        self.completed_trades = []

        self.set_warmup(timedelta(days=30))

        # Weekly scan for entries
        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.after_market_open(self.spy, 30),
            self.scan_entries
        )

        # Daily stop management
        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.before_market_close(self.spy, 5),
            self.manage_stops
        )

    def get_entry_high(self, symbol) -> float:
        """Get entry level (20-day high)"""
        history = self.history(symbol, self.ENTRY_PERIOD + 1, Resolution.DAILY)
        if history.empty or len(history) < self.ENTRY_PERIOD:
            return None
        # Exclude today
        return history['high'].iloc[:-1].max()

    def scan_entries(self):
        if self.is_warming_up:
            return

        if len(self.positions) >= self.MAX_POSITIONS:
            return

        candidates = []
        for symbol in self.stocks:
            if symbol in self.positions:
                continue

            entry_high = self.get_entry_high(symbol)
            if entry_high is None:
                continue

            price = self.securities[symbol].price

            # Breakout condition
            if price > entry_high:
                breakout_pct = (price - entry_high) / entry_high
                candidates.append((symbol, breakout_pct, entry_high))

        if not candidates:
            return

        candidates.sort(key=lambda x: x[1], reverse=True)

        positions_to_add = self.MAX_POSITIONS - len(self.positions)
        for symbol, _, entry_high in candidates[:positions_to_add]:
            self.enter_position(symbol, entry_high)

    def enter_position(self, symbol, entry_high: float):
        price = self.securities[symbol].price
        atr = self.atr_indicators[symbol].current.value if self.atr_indicators[symbol].is_ready else price * 0.03

        # Initialize highest high tracking
        self.highest_high[symbol] = price

        # Initial Chandelier stop
        chandelier_stop = price - (self.CHANDELIER_MULT * atr)

        weight = 0.99 / self.MAX_POSITIONS
        self.set_holdings(symbol, weight)

        self.positions[symbol] = {
            'entry_price': price,
            'entry_date': self.time,
            'chandelier_stop': chandelier_stop,
        }

        self.log(f"ENTRY: {symbol} @ ${price:.2f} | Chandelier stop=${chandelier_stop:.2f}")

    def manage_stops(self):
        if self.is_warming_up:
            return

        for symbol in list(self.positions.keys()):
            pos = self.positions[symbol]
            price = self.securities[symbol].price
            atr = self.atr_indicators[symbol].current.value if self.atr_indicators[symbol].is_ready else price * 0.03

            # Update highest high
            if price > self.highest_high[symbol]:
                self.highest_high[symbol] = price

            # Update Chandelier stop
            new_stop = self.highest_high[symbol] - (self.CHANDELIER_MULT * atr)
            if new_stop > pos['chandelier_stop']:
                pos['chandelier_stop'] = new_stop

            # Check stop
            if price < pos['chandelier_stop']:
                self.exit_position(symbol, f"Chandelier stop @ ${pos['chandelier_stop']:.2f}")

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
            'pnl_pct': pnl_pct,
            'days_held': days_held,
        })

        self.log(f"EXIT: {symbol} | {reason} | P&L={pnl_pct*100:.1f}% | Days={days_held}")
        del self.positions[symbol]

    def on_end_of_algorithm(self):
        self.log("=" * 60)
        self.log("CHANDELIER TREND - SUMMARY")
        self.log("=" * 60)

        if not self.completed_trades:
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

    def on_data(self, data):
        pass
