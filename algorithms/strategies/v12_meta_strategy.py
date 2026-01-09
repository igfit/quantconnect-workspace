"""
v12 META-STRATEGY: Regime-Adaptive Universe & Trading

Hypothesis: Different market regimes require different approaches.

REGIME DETECTION (using VIX and momentum factor):
1. LOW-VOL BULL: VIX avg < 18, SPY > 200 SMA
   → Include mega-caps, longer lookback, less trading

2. HIGH-VOL / MOMENTUM: VIX avg > 18 OR strong momentum dispersion
   → Mid-cap focus, shorter lookback, more active

3. BEAR / CRISIS: SPY < 200 SMA
   → Defensive, minimal exposure

UNIVERSE ADJUSTMENT BY REGIME:
- Low-vol: $10B - $1T market cap (include mega-caps like FAANG)
- High-vol: $500M - $300B (current v12 approach, high-beta)

PARAMETER ADJUSTMENT BY REGIME:
- Low-vol: 200-day lookback, monthly rebalance
- High-vol: 126-day lookback, biweekly rebalance
"""

from AlgorithmImports import *
from collections import deque


class V12MetaStrategy(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2019, 12, 31)
        self.set_cash(100000)

        self.set_security_initializer(lambda security: security.set_slippage_model(
            ConstantSlippageModel(0.001)
        ))
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        # Core parameters (adjusted by regime)
        self.top_n = 8
        self.min_dollar_volume = 5_000_000

        # Regime state
        self.current_regime = "unknown"
        self.vix_history = deque(maxlen=20)  # 20-day VIX average

        # Universe (adjusted by regime)
        self.universe_size = 50
        self.last_universe_refresh = None

        self.prev_short_mom = {}
        self.rebalance_week = 0
        self.active_symbols = []
        self.momentum = {}
        self.short_mom = {}
        self.long_mom = {}  # For low-vol regime
        self.volume_sma = {}

        # Market indicators
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.qqq = self.add_equity("QQQ", Resolution.DAILY).symbol
        self.vix = self.add_data(CBOE, "VIX", Resolution.DAILY).symbol

        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)
        self.spy_sma_50 = self.sma(self.spy, 50, Resolution.DAILY)
        self.qqq_sma_10 = self.sma(self.qqq, 10, Resolution.DAILY)
        self.qqq_sma_50 = self.sma(self.qqq, 50, Resolution.DAILY)

        self.add_universe(self.coarse_filter, self.fine_filter)
        self.set_warm_up(250, Resolution.DAILY)

        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.after_market_open("SPY", 30),
            self.weekly_rebalance
        )
        self.set_benchmark("SPY")

    def detect_regime(self):
        """Detect current market regime based on volatility and trend."""
        if not self.spy_sma_200.is_ready:
            return "unknown"

        spy_price = self.securities[self.spy].price
        above_200 = spy_price > self.spy_sma_200.current.value
        above_50 = spy_price > self.spy_sma_50.current.value if self.spy_sma_50.is_ready else True

        # Get VIX level
        avg_vix = 20  # default
        if len(self.vix_history) > 0:
            avg_vix = sum(self.vix_history) / len(self.vix_history)

        # Regime detection
        if not above_200:
            return "bear"
        elif avg_vix < 18 and above_200 and above_50:
            return "low_vol_bull"
        else:
            return "high_vol_momentum"

    def get_regime_params(self):
        """Get universe and trading parameters based on regime."""
        regime = self.current_regime

        if regime == "low_vol_bull":
            return {
                "min_market_cap": 10e9,    # $10B - include large caps
                "max_market_cap": 1000e9,  # $1T
                "lookback_days": 200,       # Longer lookback
                "accel_period": 42,         # Longer accel
                "rebalance_freq": 4,        # Monthly (every 4 weeks)
                "sectors": "all_growth",    # Include all growth sectors
            }
        elif regime == "high_vol_momentum":
            return {
                "min_market_cap": 500e6,   # $500M - high beta small/mid
                "max_market_cap": 300e9,   # $300B
                "lookback_days": 126,       # Standard
                "accel_period": 21,
                "rebalance_freq": 2,        # Biweekly
                "sectors": "growth_only",
            }
        else:  # bear or unknown
            return {
                "min_market_cap": 10e9,
                "max_market_cap": 500e9,
                "lookback_days": 126,
                "accel_period": 21,
                "rebalance_freq": 2,
                "sectors": "defensive",
            }

    def should_refresh_universe(self):
        if self.last_universe_refresh is None:
            return True
        # Refresh quarterly or on regime change
        return (self.time - self.last_universe_refresh).days >= 90

    def coarse_filter(self, coarse):
        if not self.should_refresh_universe():
            return Universe.UNCHANGED

        params = self.get_regime_params()
        min_price = 5 if self.current_regime != "low_vol_bull" else 10
        min_volume = 10e6 if self.current_regime == "low_vol_bull" else 5e6

        filtered = [x for x in coarse
                   if x.has_fundamental_data
                   and x.price > min_price
                   and x.dollar_volume > min_volume]

        sorted_by_volume = sorted(filtered, key=lambda x: x.dollar_volume, reverse=True)
        return [x.symbol for x in sorted_by_volume[:800]]

    def fine_filter(self, fine):
        if not self.should_refresh_universe():
            return Universe.UNCHANGED

        params = self.get_regime_params()

        filtered = [x for x in fine
                   if x.market_cap > params["min_market_cap"]
                   and x.market_cap < params["max_market_cap"]]

        # Sector filter based on regime
        if params["sectors"] == "all_growth":
            # Broader - include financials, industrials in low-vol
            growth_sectors = [
                MorningstarSectorCode.TECHNOLOGY,
                MorningstarSectorCode.CONSUMER_CYCLICAL,
                MorningstarSectorCode.HEALTHCARE,
                MorningstarSectorCode.COMMUNICATION_SERVICES,
                MorningstarSectorCode.FINANCIAL_SERVICES,
                MorningstarSectorCode.INDUSTRIALS,
            ]
        elif params["sectors"] == "growth_only":
            growth_sectors = [
                MorningstarSectorCode.TECHNOLOGY,
                MorningstarSectorCode.CONSUMER_CYCLICAL,
                MorningstarSectorCode.HEALTHCARE,
                MorningstarSectorCode.COMMUNICATION_SERVICES,
            ]
        else:  # defensive
            growth_sectors = [
                MorningstarSectorCode.TECHNOLOGY,
                MorningstarSectorCode.HEALTHCARE,
                MorningstarSectorCode.CONSUMER_DEFENSIVE,
            ]

        sector_filtered = [x for x in filtered
                         if x.asset_classification.morningstar_sector_code in growth_sectors]

        sorted_stocks = sorted(sector_filtered, key=lambda x: x.dollar_volume, reverse=True)
        selected = [x.symbol for x in sorted_stocks[:self.universe_size]]

        self.last_universe_refresh = self.time
        self.log(f"Regime: {self.current_regime} | Universe: {len(selected)} stocks")

        return selected

    def on_securities_changed(self, changes):
        params = self.get_regime_params()
        lookback = params["lookback_days"]
        accel = params["accel_period"]

        for security in changes.added_securities:
            symbol = security.symbol
            if symbol in [self.spy, self.qqq, self.vix]:
                continue
            if symbol not in self.active_symbols:
                self.active_symbols.append(symbol)
            if symbol not in self.momentum:
                self.momentum[symbol] = self.roc(symbol, 126, Resolution.DAILY)
                self.long_mom[symbol] = self.roc(symbol, 200, Resolution.DAILY)
                self.short_mom[symbol] = self.roc(symbol, 21, Resolution.DAILY)
                self.volume_sma[symbol] = self.sma(symbol, 20, Resolution.DAILY, Field.VOLUME)

        for security in changes.removed_securities:
            symbol = security.symbol
            if symbol in self.active_symbols:
                self.active_symbols.remove(symbol)
            if self.portfolio[symbol].invested:
                self.liquidate(symbol)

    def on_data(self, data):
        # Track VIX
        if data.contains_key(self.vix):
            vix_value = data[self.vix].value
            if vix_value > 0:
                self.vix_history.append(vix_value)

    def weekly_rebalance(self):
        if self.is_warming_up:
            return

        # Update regime
        new_regime = self.detect_regime()
        if new_regime != self.current_regime:
            self.log(f"Regime change: {self.current_regime} -> {new_regime}")
            self.current_regime = new_regime
            # Force universe refresh on regime change
            self.last_universe_refresh = None

        self.rebalance_week += 1
        params = self.get_regime_params()

        if self.rebalance_week % params["rebalance_freq"] != 0:
            return

        self.rebalance()

    def rebalance(self):
        if len(self.active_symbols) == 0:
            return

        params = self.get_regime_params()

        # Check market trend
        if not self.spy_sma_200.is_ready:
            return

        spy_price = self.securities[self.spy].price
        above_200 = spy_price > self.spy_sma_200.current.value
        above_50 = spy_price > self.spy_sma_50.current.value if self.spy_sma_50.is_ready else True

        # Bear regime - go to cash
        if self.current_regime == "bear" or not above_200:
            self.liquidate()
            return

        # Quick exit if below 50 SMA
        if not above_50:
            self.liquidate()
            return

        # Exit weak positions
        for holding in list(self.portfolio.values()):
            if holding.invested and holding.symbol in self.active_symbols:
                if holding.symbol in self.short_mom and self.short_mom[holding.symbol].is_ready:
                    threshold = -20 if self.current_regime == "low_vol_bull" else -15
                    if self.short_mom[holding.symbol].current.value < threshold:
                        self.liquidate(holding.symbol)

        # Score stocks based on regime
        scores = {}
        for symbol in self.active_symbols:
            # Use different lookback based on regime
            if self.current_regime == "low_vol_bull":
                mom_indicator = self.long_mom.get(symbol)
            else:
                mom_indicator = self.momentum.get(symbol)

            if mom_indicator is None or not mom_indicator.is_ready:
                continue
            if symbol not in self.short_mom or not self.short_mom[symbol].is_ready:
                continue
            if not self.securities[symbol].has_data:
                continue

            price = self.securities[symbol].price
            if price < 5:
                continue
            if symbol in self.volume_sma and self.volume_sma[symbol].is_ready:
                if self.volume_sma[symbol].current.value * price < self.min_dollar_volume:
                    continue

            mom = mom_indicator.current.value
            short_mom = self.short_mom[symbol].current.value

            # Regime-specific filters
            if self.current_regime == "low_vol_bull":
                if short_mom < -15:  # Looser filter for low-vol
                    continue
            else:
                if short_mom < -10:
                    continue

            prev_mom = self.prev_short_mom.get(symbol, 0)
            acceleration = short_mom - prev_mom
            self.prev_short_mom[symbol] = short_mom

            if mom > 0:
                # Stronger acceleration bonus in high-vol regime
                if self.current_regime == "high_vol_momentum":
                    accel_bonus = 1.5 if acceleration > 0 else 1.0
                else:
                    accel_bonus = 1.2 if acceleration > 0 else 1.0
                scores[symbol] = mom * accel_bonus

        if len(scores) < 3:
            return

        actual_n = min(self.top_n, len(scores))
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_symbols = [s for s, _ in ranked[:actual_n]]

        total_score = sum(scores[s] for s in top_symbols)
        weights = {s: (scores[s] / total_score) for s in top_symbols}

        for holding in self.portfolio.values():
            if holding.invested and holding.symbol not in top_symbols:
                self.liquidate(holding.symbol)

        for symbol in top_symbols:
            self.set_holdings(symbol, weights[symbol])
