"""
Creative Combo #6: Adaptive EWO with Volatility Adjustment

Adjust EWO sensitivity based on market volatility (ATR).
- Low volatility: Use faster EWO (3/21) for quicker signals
- High volatility: Use slower EWO (8/55) to filter noise

Also adjust position sizing based on inverse volatility.

Entry: EWO > threshold (dynamic based on ATR)
Exit: EWO < -threshold OR trailing stop hit

Hypothesis: Volatility-adjusted signals should reduce whipsaws
in choppy markets while capturing trends in calm markets.
"""

from AlgorithmImports import *


class AdaptiveEWOStrategy(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.set_security_initializer(lambda security: security.set_slippage_model(
            ConstantSlippageModel(0.001)
        ))
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        # Fast EWO params (for low vol)
        self.fast_f = 3
        self.fast_s = 21

        # Slow EWO params (for high vol)
        self.slow_f = 8
        self.slow_s = 55

        # ATR for volatility measurement
        self.atr_period = 14
        self.vol_lookback = 20  # Compare ATR to 20-day average

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

        # SPY ATR for market volatility
        self.spy_atr = self.atr(self.spy, self.atr_period, MovingAverageType.SIMPLE, Resolution.DAILY)
        self.spy_atr_sma = self.sma(self.spy, self.vol_lookback, Resolution.DAILY)

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

        # Individual ATRs for volatility-weighted sizing
        self.atr_ind = {}

        for symbol in self.symbols:
            self.fast_sma_f[symbol] = self.sma(symbol, self.fast_f, Resolution.DAILY)
            self.fast_sma_s[symbol] = self.sma(symbol, self.fast_s, Resolution.DAILY)
            self.slow_sma_f[symbol] = self.sma(symbol, self.slow_f, Resolution.DAILY)
            self.slow_sma_s[symbol] = self.sma(symbol, self.slow_s, Resolution.DAILY)
            self.atr_ind[symbol] = self.atr(symbol, self.atr_period, MovingAverageType.SIMPLE, Resolution.DAILY)

        self.set_warm_up(self.slow_s + 20, Resolution.DAILY)

        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )
        self.set_benchmark("SPY")

    def is_high_volatility(self):
        """Check if market is in high volatility regime"""
        if not self.spy_atr.is_ready or not self.spy_atr_sma.is_ready:
            return False
        # High vol = ATR > 1.2x average
        return self.spy_atr.current.value > self.spy_atr_sma.current.value * 1.2

    def get_adaptive_ewo(self, symbol):
        """Get EWO using adaptive parameters based on volatility"""
        high_vol = self.is_high_volatility()

        if high_vol:
            # Use slower EWO in high volatility
            if not self.slow_sma_f[symbol].is_ready or not self.slow_sma_s[symbol].is_ready:
                return None
            return self.slow_sma_f[symbol].current.value - self.slow_sma_s[symbol].current.value
        else:
            # Use faster EWO in low volatility
            if not self.fast_sma_f[symbol].is_ready or not self.fast_sma_s[symbol].is_ready:
                return None
            return self.fast_sma_f[symbol].current.value - self.fast_sma_s[symbol].current.value

    def get_volatility_weight(self, symbol):
        """Get inverse volatility weight for position sizing"""
        if not self.atr_ind[symbol].is_ready:
            return 1.0
        price = self.securities[symbol].price
        if price <= 0:
            return 1.0
        # Normalize ATR as % of price
        atr_pct = self.atr_ind[symbol].current.value / price
        # Inverse: lower vol = higher weight (capped at 2x)
        return min(2.0, 0.02 / max(atr_pct, 0.01))

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

        high_vol = self.is_high_volatility()
        # Higher threshold in high vol to filter noise
        ewo_threshold = 0.5 if high_vol else 0.1

        scores = {}
        vol_weights = {}

        for symbol in self.symbols:
            ewo = self.get_adaptive_ewo(symbol)

            if ewo is None:
                continue
            if not self.securities[symbol].has_data:
                continue

            price = self.securities[symbol].price
            if price < 5:
                continue

            # Entry: EWO > threshold
            if ewo > ewo_threshold:
                # Score by EWO strength (normalized)
                scores[symbol] = ewo / price * 100
                vol_weights[symbol] = self.get_volatility_weight(symbol)

        # Exit: EWO turns negative
        for holding in list(self.portfolio.values()):
            if holding.invested and holding.symbol in self.symbols:
                ewo = self.get_adaptive_ewo(holding.symbol)
                if ewo is not None and ewo < -ewo_threshold:
                    self.liquidate(holding.symbol)

        if len(scores) < 3:
            return

        actual_n = min(self.top_n, len(scores))
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_symbols = [s for s, _ in ranked[:actual_n]]

        # Calculate volatility-adjusted weights
        total_vol_weight = sum(vol_weights.get(s, 1.0) for s in top_symbols)

        for holding in self.portfolio.values():
            if holding.invested and holding.symbol not in top_symbols and holding.symbol != self.spy:
                self.liquidate(holding.symbol)

        for symbol in top_symbols:
            # Volatility-weighted position sizing
            weight = vol_weights.get(symbol, 1.0) / total_vol_weight
            self.set_holdings(symbol, weight)
