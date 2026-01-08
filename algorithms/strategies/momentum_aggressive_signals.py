"""
Momentum Strategy: Aggressive Signal-Based

SIGNAL ALPHA:
1. Top 3 ultra-concentrated
2. 1.5x leverage when regime is bullish
3. 8% stop-loss (cut losers very fast)
4. Re-entry only on new momentum high
"""

from AlgorithmImports import *


class MomentumAggressiveSignals(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.set_security_initializer(lambda security: security.set_slippage_model(
            ConstantSlippageModel(0.001)
        ))
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        # PARAMETERS
        self.lookback_days = 63           # 3 months (faster signal)
        self.top_n = 3                    # Ultra concentrated
        self.leverage = 1.5               # Modest leverage
        self.stop_loss_pct = 0.08         # 8% stop loss
        self.use_regime_filter = True
        self.min_dollar_volume = 5_000_000

        # Track for stops and re-entry
        self.entry_prices = {}
        self.stopped_out = {}  # Symbol -> date stopped out

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
        self.momentum_high = {}  # Track momentum highs for re-entry
        self.volume_sma = {}
        for symbol in self.symbols:
            self.momentum[symbol] = self.roc(symbol, self.lookback_days, Resolution.DAILY)
            self.volume_sma[symbol] = self.sma(symbol, 20, Resolution.DAILY, Field.VOLUME)

        self.set_warm_up(self.lookback_days + 10, Resolution.DAILY)

        # Weekly rebalancing
        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )
        self.set_benchmark("SPY")

    def on_data(self, data):
        """Daily stop-loss check"""
        if self.is_warming_up:
            return

        # Regime check
        if self.use_regime_filter and self.spy_sma.is_ready:
            if self.securities[self.spy].price < self.spy_sma.current.value:
                self.liquidate()
                self.entry_prices.clear()
                return

        for symbol in list(self.entry_prices.keys()):
            if not self.portfolio[symbol].invested:
                if symbol in self.entry_prices:
                    del self.entry_prices[symbol]
                continue

            if symbol not in data or not data[symbol]:
                continue

            price = data[symbol].close
            entry = self.entry_prices[symbol]

            # Stop-loss triggered - CUT FAST
            if price < entry * (1 - self.stop_loss_pct):
                self.liquidate(symbol)
                del self.entry_prices[symbol]
                self.stopped_out[symbol] = self.time.date()

    def rebalance(self):
        if self.is_warming_up:
            return

        if self.use_regime_filter:
            if not self.spy_sma.is_ready:
                return
            if self.securities[self.spy].price < self.spy_sma.current.value:
                self.liquidate()
                self.entry_prices.clear()
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

            # Track momentum high
            prev_high = self.momentum_high.get(symbol, float('-inf'))
            if mom > prev_high:
                self.momentum_high[symbol] = mom

            # Skip if recently stopped out unless making new momentum high
            if symbol in self.stopped_out:
                days_since = (self.time.date() - self.stopped_out[symbol]).days
                if days_since < 30 and mom < self.momentum_high.get(symbol, 0):
                    continue
                else:
                    del self.stopped_out[symbol]  # Clear cooldown

            if mom > 0:
                scores[symbol] = mom

        if len(scores) < self.top_n:
            return

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_symbols = [s for s, _ in ranked[:self.top_n]]

        # Momentum-weighted with leverage
        total_mom = sum(scores[s] for s in top_symbols)
        weights = {s: (scores[s] / total_mom) * self.leverage for s in top_symbols}

        for holding in self.portfolio.values():
            if holding.invested and holding.symbol not in top_symbols:
                self.liquidate(holding.symbol)
                if holding.symbol in self.entry_prices:
                    del self.entry_prices[holding.symbol]

        for symbol in top_symbols:
            self.set_holdings(symbol, weights[symbol])
            if symbol not in self.entry_prices:
                self.entry_prices[symbol] = self.securities[symbol].price
