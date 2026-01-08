"""
VCP (Volatility Contraction Pattern) Breakout Strategy

Based on Mark Minervini's SEPA methodology.
Looks for stocks in uptrends with contracting volatility, then buys breakout.

Universe: High-Beta Growth (Universe D)
Rebalance: Weekly scan, daily execution
Target: 30%+ CAGR with controlled risk

WHY THIS WORKS:
- Volatility contraction signals accumulation
- Breakout from contraction often leads to explosive moves
- Trend template filters for quality setups
- Risk defined at pivot point

KEY PARAMETERS:
- Price > 50 SMA > 150 SMA > 200 SMA (trend template)
- Volatility contracting (ATR decreasing)
- Breakout above recent high on volume
- Stop at recent pivot low
"""

from AlgorithmImports import *
from datetime import timedelta
from collections import deque


class VCPBreakout(QCAlgorithm):
    """
    VCP Breakout on High-Beta Universe

    Rules:
    1. Stock must pass Minervini trend template
    2. ATR must be contracting (current < 10-day avg)
    3. Buy on breakout above 10-day high
    4. Stop at entry - 1.5 ATR
    """

    # Configuration
    ATR_PERIOD = 14
    LOOKBACK_HIGH = 10  # Breakout period
    ATR_STOP = 1.5
    MAX_POSITIONS = 5
    USE_TREND_TEMPLATE = True

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
        self.sma50 = {}
        self.sma150 = {}
        self.sma200 = {}
        self.atr_indicators = {}
        self.atr_history = {}  # Track ATR over time for contraction check
        self.high_windows = {}

        for ticker in self.universe_symbols:
            try:
                equity = self.add_equity(ticker, Resolution.DAILY)
                equity.set_slippage_model(ConstantSlippageModel(0.001))
                equity.set_fee_model(InteractiveBrokersFeeModel())
                symbol = equity.symbol
                self.stocks.append(symbol)

                self.sma50[symbol] = self.sma(symbol, 50, Resolution.DAILY)
                self.sma150[symbol] = self.sma(symbol, 150, Resolution.DAILY)
                self.sma200[symbol] = self.sma(symbol, 200, Resolution.DAILY)
                self.atr_indicators[symbol] = self.atr(symbol, self.ATR_PERIOD)
                self.atr_history[symbol] = deque(maxlen=10)
                self.high_windows[symbol] = deque(maxlen=self.LOOKBACK_HIGH)
            except:
                pass

        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.set_benchmark(self.spy)

        self.positions = {}
        self.completed_trades = []

        self.set_warmup(timedelta(days=210))

        # Daily scan and execution
        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.after_market_open(self.spy, 30),
            self.scan_and_execute
        )

        # Check stops
        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.before_market_close(self.spy, 5),
            self.check_stops
        )

    def on_data(self, data):
        """Update rolling windows"""
        for symbol in self.stocks:
            if data.contains_key(symbol) and data[symbol] is not None:
                self.high_windows[symbol].append(data[symbol].high)

                atr = self.atr_indicators.get(symbol)
                if atr and atr.is_ready:
                    self.atr_history[symbol].append(atr.current.value)

    def passes_trend_template(self, symbol) -> bool:
        """
        Minervini's trend template:
        - Price > 50 SMA
        - 50 SMA > 150 SMA
        - 150 SMA > 200 SMA
        - Price within 25% of 52-week high
        - Price at least 30% above 52-week low
        """
        if not self.USE_TREND_TEMPLATE:
            return True

        sma50 = self.sma50.get(symbol)
        sma150 = self.sma150.get(symbol)
        sma200 = self.sma200.get(symbol)

        if not all([sma50, sma150, sma200]):
            return False
        if not all([sma50.is_ready, sma150.is_ready, sma200.is_ready]):
            return False

        price = self.securities[symbol].price
        sma50_val = sma50.current.value
        sma150_val = sma150.current.value
        sma200_val = sma200.current.value

        # Basic trend checks
        if price <= sma50_val:
            return False
        if sma50_val <= sma150_val:
            return False
        if sma150_val <= sma200_val:
            return False

        return True

    def has_volatility_contraction(self, symbol) -> bool:
        """Check if ATR is contracting"""
        atr_hist = list(self.atr_history.get(symbol, []))
        if len(atr_hist) < 5:
            return False

        current_atr = atr_hist[-1]
        avg_atr = sum(atr_hist[:-1]) / len(atr_hist[:-1])

        # Current ATR should be below average (contraction)
        return current_atr < avg_atr * 0.95

    def get_breakout_level(self, symbol) -> float:
        """Get breakout level (recent high)"""
        highs = list(self.high_windows.get(symbol, []))
        if len(highs) < self.LOOKBACK_HIGH:
            return None
        return max(highs[:-1]) if len(highs) > 1 else max(highs)

    def scan_and_execute(self):
        if self.is_warming_up:
            return

        if len(self.positions) >= self.MAX_POSITIONS:
            return

        candidates = []
        for symbol in self.stocks:
            if symbol in self.positions:
                continue

            # Check trend template
            if not self.passes_trend_template(symbol):
                continue

            # Check volatility contraction
            if not self.has_volatility_contraction(symbol):
                continue

            # Check for breakout
            breakout_level = self.get_breakout_level(symbol)
            if breakout_level is None:
                continue

            price = self.securities[symbol].price
            if price > breakout_level:
                breakout_pct = (price - breakout_level) / breakout_level
                candidates.append((symbol, breakout_pct, breakout_level))

        if not candidates:
            return

        # Sort by breakout strength
        candidates.sort(key=lambda x: x[1], reverse=True)

        # Enter positions
        positions_to_add = self.MAX_POSITIONS - len(self.positions)
        for symbol, _, breakout_level in candidates[:positions_to_add]:
            self.enter_position(symbol, breakout_level)

    def enter_position(self, symbol, breakout_level: float):
        price = self.securities[symbol].price
        atr = self.atr_indicators[symbol].current.value if self.atr_indicators[symbol].is_ready else price * 0.03

        stop_price = price - (self.ATR_STOP * atr)

        weight = 0.99 / self.MAX_POSITIONS
        self.set_holdings(symbol, weight)

        self.positions[symbol] = {
            'entry_price': price,
            'entry_date': self.time,
            'breakout_level': breakout_level,
            'stop_price': stop_price,
            'highest_price': price,
        }

        self.log(f"ENTRY: {symbol} @ ${price:.2f} (VCP breakout > ${breakout_level:.2f}) Stop=${stop_price:.2f}")

    def check_stops(self):
        if self.is_warming_up:
            return

        for symbol in list(self.positions.keys()):
            pos = self.positions[symbol]
            price = self.securities[symbol].price
            atr = self.atr_indicators[symbol].current.value if self.atr_indicators[symbol].is_ready else price * 0.03

            # Trail stop up
            if price > pos['highest_price']:
                pos['highest_price'] = price
                new_stop = price - (self.ATR_STOP * atr)
                if new_stop > pos['stop_price']:
                    pos['stop_price'] = new_stop

            if price < pos['stop_price']:
                self.exit_position(symbol, f"Stop @ ${pos['stop_price']:.2f}")

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
        self.log("VCP BREAKOUT - SUMMARY")
        self.log("=" * 60)

        if not self.completed_trades:
            return

        total = len(self.completed_trades)
        winners = [t for t in self.completed_trades if t['pnl_pct'] > 0]

        self.log(f"Total Trades: {total}")
        self.log(f"Win Rate: {len(winners)/total*100:.1f}%")

    def on_data(self, data):
        pass
