"""
Momentum Strategy: Weighted Positions + Trailing Stops

SIGNAL ALPHA:
1. Position sizing by momentum strength (ride winners)
2. 15% trailing stop from highs (cut losers fast)
3. Weekly rebalancing (faster signal response)
"""

from AlgorithmImports import *


class MomentumWeightedTrailing(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.set_security_initializer(lambda security: security.set_slippage_model(
            ConstantSlippageModel(0.001)
        ))
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        # PARAMETERS
        self.lookback_days = 126          # 6 months
        self.top_n = 10
        self.trailing_stop_pct = 0.15     # 15% trailing stop
        self.use_regime_filter = True
        self.min_dollar_volume = 5_000_000

        # Track high watermarks for trailing stops
        self.high_watermark = {}

        # CLAUDE V3 UNIVERSE
        self.universe_tickers = [
            "NVDA", "AMD", "AVGO", "QCOM", "MU", "AMAT", "LRCX", "KLAC", "MRVL", "ON",
            "TXN", "ADI", "SNPS", "CDNS", "ASML",
            "CRM", "ADBE", "NOW", "INTU", "PANW", "VEEV", "WDAY",
            "V", "MA", "PYPL", "SQ",
            "AMZN", "SHOP",
            "BKNG", "RCL", "CCL", "MAR", "HLT", "WYNN",
            "XOM", "CVX", "OXY", "DVN", "SLB", "COP",
            "CAT", "DE", "URI", "BA",
            "TSLA", "NKE", "LULU", "CMG", "DECK",
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

        self.momentum = {}
        self.volume_sma = {}
        for symbol in self.symbols:
            self.momentum[symbol] = self.roc(symbol, self.lookback_days, Resolution.DAILY)
            self.volume_sma[symbol] = self.sma(symbol, 20, Resolution.DAILY, Field.VOLUME)

        self.set_warm_up(self.lookback_days + 10, Resolution.DAILY)

        # Weekly rebalancing for faster response
        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )
        self.set_benchmark("SPY")

    def on_data(self, data):
        """Check trailing stops daily"""
        if self.is_warming_up:
            return

        for symbol in list(self.high_watermark.keys()):
            if not self.portfolio[symbol].invested:
                if symbol in self.high_watermark:
                    del self.high_watermark[symbol]
                continue

            if symbol not in data or not data[symbol]:
                continue

            price = data[symbol].close

            # Update high watermark
            if price > self.high_watermark.get(symbol, 0):
                self.high_watermark[symbol] = price

            # Check trailing stop
            hwm = self.high_watermark[symbol]
            if hwm > 0 and price < hwm * (1 - self.trailing_stop_pct):
                self.liquidate(symbol, f"Trailing stop: {price:.2f} < {hwm * (1 - self.trailing_stop_pct):.2f}")
                del self.high_watermark[symbol]

    def rebalance(self):
        if self.is_warming_up:
            return

        if self.use_regime_filter:
            if not self.spy_sma.is_ready:
                return
            if self.securities[self.spy].price < self.spy_sma.current.value:
                self.liquidate()
                self.high_watermark.clear()
                return

        scores = {}
        for symbol in self.symbols:
            if not self.momentum[symbol].is_ready:
                continue
            if not self.securities[symbol].has_data:
                continue
            price = self.securities[symbol].price
            if price < 5:
                continue
            if self.volume_sma[symbol].is_ready:
                if self.volume_sma[symbol].current.value * price < self.min_dollar_volume:
                    continue
            mom = self.momentum[symbol].current.value
            if mom > 0:  # Only positive momentum
                scores[symbol] = mom

        if len(scores) < self.top_n:
            return

        # Rank and select top N
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_symbols = [s for s, _ in ranked[:self.top_n]]

        # MOMENTUM-WEIGHTED SIZING (ride winners)
        total_mom = sum(scores[s] for s in top_symbols)
        weights = {}
        for symbol in top_symbols:
            # Weight proportional to momentum strength
            weights[symbol] = scores[symbol] / total_mom

        # Liquidate non-top positions
        for holding in self.portfolio.values():
            if holding.invested and holding.symbol not in top_symbols:
                self.liquidate(holding.symbol)
                if holding.symbol in self.high_watermark:
                    del self.high_watermark[holding.symbol]

        # Rebalance with momentum weights
        for symbol in top_symbols:
            self.set_holdings(symbol, weights[symbol])
            # Initialize high watermark for new positions
            if symbol not in self.high_watermark:
                self.high_watermark[symbol] = self.securities[symbol].price
