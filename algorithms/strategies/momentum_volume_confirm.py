"""
Momentum Strategy: Volume Confirmation

ITERATION: Test if volume confirmation improves signal quality
- Only enter when recent volume > average (confirms momentum)
- Use volume ratio as additional weight factor
- Hypothesis: Higher quality signals, better win rate
"""

from AlgorithmImports import *


class MomentumVolumeConfirm(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.set_security_initializer(lambda security: security.set_slippage_model(
            ConstantSlippageModel(0.001)
        ))
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        # PARAMETERS
        self.lookback_days = 126
        self.accel_period = 21
        self.volume_avg_period = 20
        self.volume_short_period = 5  # Recent volume
        self.min_volume_ratio = 1.1   # Recent vol must be 10% above average
        self.top_n = 10
        self.use_regime_filter = True
        self.min_dollar_volume = 5_000_000

        self.prev_short_mom = {}

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
        self.volume_short = {}
        for symbol in self.symbols:
            self.momentum[symbol] = self.roc(symbol, self.lookback_days, Resolution.DAILY)
            self.short_mom[symbol] = self.roc(symbol, self.accel_period, Resolution.DAILY)
            self.volume_sma[symbol] = self.sma(symbol, self.volume_avg_period, Resolution.DAILY, Field.VOLUME)
            self.volume_short[symbol] = self.sma(symbol, self.volume_short_period, Resolution.DAILY, Field.VOLUME)

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
                return

        scores = {}
        vol_ratios = {}

        for symbol in self.symbols:
            if not self.momentum[symbol].is_ready:
                continue
            if not self.short_mom[symbol].is_ready:
                continue
            if not self.volume_sma[symbol].is_ready:
                continue
            if not self.volume_short[symbol].is_ready:
                continue
            if not self.securities[symbol].has_data:
                continue

            price = self.securities[symbol].price
            if price < 5:
                continue

            avg_vol = self.volume_sma[symbol].current.value
            if avg_vol * price < self.min_dollar_volume:
                continue

            mom = self.momentum[symbol].current.value
            short_mom = self.short_mom[symbol].current.value
            prev_mom = self.prev_short_mom.get(symbol, 0)
            acceleration = short_mom - prev_mom
            self.prev_short_mom[symbol] = short_mom

            # Volume confirmation
            recent_vol = self.volume_short[symbol].current.value
            vol_ratio = recent_vol / avg_vol if avg_vol > 0 else 0

            # Require momentum, acceleration, AND volume confirmation
            if mom > 0 and acceleration > 0 and vol_ratio >= self.min_volume_ratio:
                scores[symbol] = mom
                vol_ratios[symbol] = vol_ratio

        # Fallback if too few stocks pass all filters
        if len(scores) < 5:
            scores = {}
            vol_ratios = {}
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
                    vol_ratios[symbol] = 1.0

        if len(scores) < 5:
            return

        actual_n = min(self.top_n, len(scores))
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_symbols = [s for s, _ in ranked[:actual_n]]

        # Weight by momentum * volume_ratio (higher volume = stronger conviction)
        raw_weights = {s: scores[s] * vol_ratios.get(s, 1.0) for s in top_symbols}
        total_weight = sum(raw_weights.values())
        weights = {s: raw_weights[s] / total_weight for s in top_symbols}

        for holding in self.portfolio.values():
            if holding.invested and holding.symbol not in top_symbols:
                self.liquidate(holding.symbol)

        for symbol in top_symbols:
            self.set_holdings(symbol, weights[symbol])
