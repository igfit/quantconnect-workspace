"""
Creative Combo #3: Dual EWO (Fast + Slow)

Use two EWO indicators with different timeframes:
- Fast EWO (3/13): Quick signals, more trades
- Slow EWO (5/34): Trend confirmation

Entry: Fast EWO > 0 AND Slow EWO > 0 (both bullish)
Exit: Fast EWO < 0 (quick exit) OR Slow EWO < 0 (trend reversal)

Hypothesis: Fast EWO catches the move early, Slow EWO filters
out false signals. Should improve win rate over single EWO.
"""

from AlgorithmImports import *


class DualEWOStrategy(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.set_security_initializer(lambda security: security.set_slippage_model(
            ConstantSlippageModel(0.001)
        ))
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        # Fast EWO parameters (more responsive)
        self.fast_f = 3
        self.fast_s = 13

        # Slow EWO parameters (trend confirmation)
        self.slow_f = 5
        self.slow_s = 34

        self.top_n = 10
        self.use_regime_filter = True

        # NO TOP3 UNIVERSE
        self.universe_tickers = [
            "AMD", "AVGO", "QCOM", "MU", "AMAT", "LRCX", "KLAC", "MRVL", "ON",
            "TXN", "ADI", "SNPS", "CDNS", "ASML",
            "CRM", "ADBE", "NOW", "INTU", "PANW", "VEEV", "WDAY",
            "V", "MA", "PYPL", "SQ",
            "AMZN", "SHOP",
            "BKNG", "RCL", "CCL", "MAR", "HLT", "WYNN",
            "XOM", "CVX", "OXY", "DVN", "SLB", "COP",
            "CAT", "DE", "URI", "BA",
            "NKE", "LULU", "CMG", "DECK",
            "GS", "MS",
            "NFLX", "ROKU",
        ]

        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.spy_sma = self.sma(self.spy, 200, Resolution.DAILY)

        self.symbols = []
        for ticker in self.universe_tickers:
            try:
                equity = self.add_equity(ticker, Resolution.DAILY)
                self.symbols.append(equity.symbol)
            except:
                pass

        # Fast EWO indicators
        self.fast_sma_f = {}
        self.fast_sma_s = {}

        # Slow EWO indicators
        self.slow_sma_f = {}
        self.slow_sma_s = {}

        for symbol in self.symbols:
            self.fast_sma_f[symbol] = self.sma(symbol, self.fast_f, Resolution.DAILY)
            self.fast_sma_s[symbol] = self.sma(symbol, self.fast_s, Resolution.DAILY)
            self.slow_sma_f[symbol] = self.sma(symbol, self.slow_f, Resolution.DAILY)
            self.slow_sma_s[symbol] = self.sma(symbol, self.slow_s, Resolution.DAILY)

        self.set_warm_up(self.slow_s + 10, Resolution.DAILY)

        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )
        self.set_benchmark("SPY")

    def get_fast_ewo(self, symbol):
        """Calculate fast EWO (3/13)"""
        if not self.fast_sma_f[symbol].is_ready or not self.fast_sma_s[symbol].is_ready:
            return None
        return self.fast_sma_f[symbol].current.value - self.fast_sma_s[symbol].current.value

    def get_slow_ewo(self, symbol):
        """Calculate slow EWO (5/34)"""
        if not self.slow_sma_f[symbol].is_ready or not self.slow_sma_s[symbol].is_ready:
            return None
        return self.slow_sma_f[symbol].current.value - self.slow_sma_s[symbol].current.value

    def rebalance(self):
        if self.is_warming_up:
            return

        # Regime filter
        if self.use_regime_filter:
            if not self.spy_sma.is_ready:
                return
            if self.securities[self.spy].price < self.spy_sma.current.value:
                self.liquidate()
                return

        scores = {}

        for symbol in self.symbols:
            fast_ewo = self.get_fast_ewo(symbol)
            slow_ewo = self.get_slow_ewo(symbol)

            if fast_ewo is None or slow_ewo is None:
                continue
            if not self.securities[symbol].has_data:
                continue

            price = self.securities[symbol].price
            if price < 5:
                continue

            # Entry: Both EWOs positive (dual confirmation)
            if fast_ewo > 0 and slow_ewo > 0:
                # Score: Combined strength (normalized)
                combined = (fast_ewo + slow_ewo) / price * 100
                scores[symbol] = combined

        # Exit: Either EWO turns negative
        for holding in list(self.portfolio.values()):
            if holding.invested and holding.symbol in self.symbols:
                fast_ewo = self.get_fast_ewo(holding.symbol)
                slow_ewo = self.get_slow_ewo(holding.symbol)

                if fast_ewo is not None and slow_ewo is not None:
                    # Exit if either goes negative
                    if fast_ewo < 0 or slow_ewo < 0:
                        self.liquidate(holding.symbol)

        if len(scores) < 3:
            return

        actual_n = min(self.top_n, len(scores))
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_symbols = [s for s, _ in ranked[:actual_n]]

        weight = 1.0 / actual_n

        for holding in self.portfolio.values():
            if holding.invested and holding.symbol not in top_symbols and holding.symbol != self.spy:
                self.liquidate(holding.symbol)

        for symbol in top_symbols:
            self.set_holdings(symbol, weight)
