"""
Momentum Strategy: Decay Exit Signal

TEST: Exit earlier when momentum decays significantly (50% from peak)
instead of waiting for momentum to go negative.

Hypothesis: Exit earlier to capture more gains, avoid reversals.
"""

from AlgorithmImports import *


class MomentumDecayExit(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.set_security_initializer(lambda security: security.set_slippage_model(
            ConstantSlippageModel(0.001)
        ))
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        self.lookback_days = 126
        self.accel_period = 21
        self.top_n = 10
        self.use_regime_filter = True
        self.min_dollar_volume = 5_000_000
        self.decay_threshold = 0.5  # Exit when momentum drops to 50% of peak

        self.prev_short_mom = {}
        self.peak_momentum = {}  # Track peak momentum for each held stock

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
        self.short_mom = {}
        self.volume_sma = {}
        for symbol in self.symbols:
            self.momentum[symbol] = self.roc(symbol, self.lookback_days, Resolution.DAILY)
            self.short_mom[symbol] = self.roc(symbol, self.accel_period, Resolution.DAILY)
            self.volume_sma[symbol] = self.sma(symbol, 20, Resolution.DAILY, Field.VOLUME)

        self.set_warm_up(self.lookback_days + 10, Resolution.DAILY)

        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )
        self.set_benchmark("SPY")

    def rebalance(self):
        if self.is_warming_up:
            return

        if self.use_regime_filter:
            if not self.spy_sma.is_ready:
                return
            if self.securities[self.spy].price < self.spy_sma.current.value:
                self.liquidate()
                self.peak_momentum.clear()
                return

        # First, check for momentum decay exits on current holdings
        for holding in list(self.portfolio.values()):
            if holding.invested and holding.symbol in self.symbols:
                symbol = holding.symbol
                if not self.momentum[symbol].is_ready:
                    continue

                current_mom = self.momentum[symbol].current.value
                peak_mom = self.peak_momentum.get(symbol, current_mom)

                # Update peak momentum
                if current_mom > peak_mom:
                    self.peak_momentum[symbol] = current_mom
                    peak_mom = current_mom

                # Check for decay exit: if momentum dropped below threshold * peak
                if peak_mom > 0 and current_mom < peak_mom * self.decay_threshold:
                    self.liquidate(symbol)
                    if symbol in self.peak_momentum:
                        del self.peak_momentum[symbol]

        # Now find new entries
        scores = {}

        for symbol in self.symbols:
            if not self.momentum[symbol].is_ready:
                continue
            if not self.short_mom[symbol].is_ready:
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
            short_mom = self.short_mom[symbol].current.value
            prev_mom = self.prev_short_mom.get(symbol, 0)
            acceleration = short_mom - prev_mom
            self.prev_short_mom[symbol] = short_mom

            if mom > 0 and acceleration > 0:
                scores[symbol] = mom

        if len(scores) < self.top_n:
            scores = {}
            for symbol in self.symbols:
                if not self.momentum[symbol].is_ready:
                    continue
                if not self.securities[symbol].has_data:
                    continue
                price = self.securities[symbol].price
                if price < 5:
                    continue
                mom = self.momentum[symbol].current.value
                if mom > 0:
                    scores[symbol] = mom

        if len(scores) < 5:
            return

        actual_n = min(self.top_n, len(scores))
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_symbols = [s for s, _ in ranked[:actual_n]]

        total_mom = sum(scores[s] for s in top_symbols)
        weights = {s: scores[s] / total_mom for s in top_symbols}

        # Liquidate holdings not in top symbols (if not already exited by decay)
        for holding in self.portfolio.values():
            if holding.invested and holding.symbol not in top_symbols:
                self.liquidate(holding.symbol)
                if holding.symbol in self.peak_momentum:
                    del self.peak_momentum[holding.symbol]

        for symbol in top_symbols:
            self.set_holdings(symbol, weights[symbol])
            # Initialize peak momentum for new entries
            if symbol not in self.peak_momentum:
                self.peak_momentum[symbol] = self.momentum[symbol].current.value
