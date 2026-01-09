"""
v12 ADAPTIVE META-STRATEGY

Key insight: Different regimes require different universe AND strategy.

REGIME DETECTION (backward-looking, no look-ahead):
- High Momentum Regime: QQQ 6-month ROC > 15% AND QQQ > 50 SMA
- Low Momentum Regime: Otherwise

HIGH MOMENTUM REGIME (2020-2024 style):
- Universe: Mid-cap growth ($5B-$300B), high-beta sectors
- Strategy: Aggressive momentum ranking + acceleration bonus
- Rebalance: Biweekly
- Allocation: Momentum-weighted

LOW MOMENTUM REGIME (2015-2019 style):
- Universe: Large/mega-cap ($20B-$1T), quality stocks
- Strategy: Trend following (golden cross) + consistency
- Rebalance: Monthly
- Allocation: Equal weight
"""

from AlgorithmImports import *


class V12AdaptiveMeta(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2019, 12, 31)
        self.set_cash(100000)

        self.set_security_initializer(lambda security: security.set_slippage_model(
            ConstantSlippageModel(0.001)
        ))
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        # Common parameters
        self.lookback_days = 126
        self.min_dollar_volume = 10_000_000

        # Regime-specific parameters
        self.high_mom_top_n = 8
        self.low_mom_top_n = 12

        # Universe will be refreshed on regime change
        self.universe_size = 75
        self.last_universe_refresh = None
        self.current_regime = None  # Will be set on first run

        # Track regime for universe refresh
        self.prev_regime = None

        self.rebalance_week = 0
        self.active_symbols = []
        self.stock_added_in_regime = {}  # Track which regime each stock was added in

        # Indicators per symbol
        self.momentum = {}
        self.short_mom = {}
        self.sma_50 = {}
        self.sma_200 = {}
        self.volume_sma = {}

        # Previous short momentum for acceleration
        self.prev_short_mom = {}

        # Market regime indicators
        self.qqq = self.add_equity("QQQ", Resolution.DAILY).symbol
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol

        self.qqq_mom_126 = self.roc(self.qqq, 126, Resolution.DAILY)
        self.qqq_mom_63 = self.roc(self.qqq, 63, Resolution.DAILY)
        self.qqq_sma_50 = self.sma(self.qqq, 50, Resolution.DAILY)
        self.qqq_sma_200 = self.sma(self.qqq, 200, Resolution.DAILY)
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)

        # Volatility indicator (20-day realized vol)
        self.spy_returns = []
        self.vol_lookback = 20

        self.add_universe(self.coarse_filter, self.fine_filter)
        self.set_warm_up(210, Resolution.DAILY)

        # Weekly check - actual rebalance depends on regime
        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.after_market_open("SPY", 30),
            self.weekly_check
        )
        self.set_benchmark("SPY")

    def get_regime(self):
        """
        Determine market regime based on QQQ behavior.
        HIGH_MOMENTUM: Strong trending market (2020-2024 style)
        LOW_MOMENTUM: Range-bound or slow trending (2015-2019 style)
        """
        if not self.qqq_mom_126.is_ready or not self.qqq_sma_50.is_ready:
            return "LOW_MOMENTUM"  # Default to conservative

        qqq_price = self.securities[self.qqq].price
        mom_126 = self.qqq_mom_126.current.value
        mom_63 = self.qqq_mom_63.current.value if self.qqq_mom_63.is_ready else 0
        above_50_sma = qqq_price > self.qqq_sma_50.current.value

        # HIGH MOMENTUM: Strong 6-month momentum AND above 50 SMA
        # This captures strong trending markets like 2020-2021, 2023-2024
        if mom_126 > 15 and above_50_sma and mom_63 > 5:
            return "HIGH_MOMENTUM"

        # Everything else is LOW_MOMENTUM (range-bound, slow grind)
        return "LOW_MOMENTUM"

    def should_refresh(self):
        """Refresh universe on regime change or every 90 days"""
        current_regime = self.get_regime()

        # Force refresh on regime change
        if self.prev_regime is not None and current_regime != self.prev_regime:
            self.log(f"REGIME CHANGE: {self.prev_regime} -> {current_regime}")
            return True

        if self.last_universe_refresh is None:
            return True

        return (self.time - self.last_universe_refresh).days >= 90

    def coarse_filter(self, coarse):
        if not self.should_refresh():
            return Universe.UNCHANGED

        self.current_regime = self.get_regime()

        # Regime-specific price/volume thresholds
        if self.current_regime == "HIGH_MOMENTUM":
            min_price = 10
            min_dollar_vol = 20e6
        else:  # LOW_MOMENTUM
            min_price = 20
            min_dollar_vol = 50e6

        filtered = [x for x in coarse
                   if x.has_fundamental_data
                   and x.price > min_price
                   and x.dollar_volume > min_dollar_vol]

        sorted_by_volume = sorted(filtered, key=lambda x: x.dollar_volume, reverse=True)
        return [x.symbol for x in sorted_by_volume[:500]]

    def fine_filter(self, fine):
        if not self.should_refresh():
            return Universe.UNCHANGED

        regime = self.current_regime

        if regime == "HIGH_MOMENTUM":
            # Mid-cap growth focus ($5B-$300B)
            filtered = [x for x in fine
                       if x.market_cap > 5e9
                       and x.market_cap < 300e9]

            # Growth sectors only
            growth_sectors = [
                MorningstarSectorCode.TECHNOLOGY,
                MorningstarSectorCode.CONSUMER_CYCLICAL,
                MorningstarSectorCode.HEALTHCARE,
                MorningstarSectorCode.COMMUNICATION_SERVICES,
            ]
            sector_filtered = [x for x in filtered
                             if x.asset_classification.morningstar_sector_code in growth_sectors]

        else:  # LOW_MOMENTUM
            # Large/mega-cap focus ($20B-$1T)
            filtered = [x for x in fine
                       if x.market_cap > 20e9
                       and x.market_cap < 1000e9]

            # Broader sector inclusion (exclude only utilities/RE)
            excluded_sectors = [
                MorningstarSectorCode.UTILITIES,
                MorningstarSectorCode.REAL_ESTATE,
            ]
            sector_filtered = [x for x in filtered
                             if x.asset_classification.morningstar_sector_code not in excluded_sectors]

        sorted_stocks = sorted(sector_filtered, key=lambda x: x.dollar_volume, reverse=True)
        selected = [x.symbol for x in sorted_stocks[:self.universe_size]]

        self.prev_regime = regime
        self.last_universe_refresh = self.time
        self.log(f"Universe refresh ({regime}): {len(selected)} stocks at {self.time.date()}")

        return selected

    def on_securities_changed(self, changes):
        current_regime = self.get_regime()

        for security in changes.added_securities:
            symbol = security.symbol
            if symbol in [self.spy, self.qqq]:
                continue
            if symbol not in self.active_symbols:
                self.active_symbols.append(symbol)
                self.stock_added_in_regime[symbol] = current_regime

            if symbol not in self.momentum:
                self.momentum[symbol] = self.roc(symbol, self.lookback_days, Resolution.DAILY)
                self.short_mom[symbol] = self.roc(symbol, 21, Resolution.DAILY)
                self.sma_50[symbol] = self.sma(symbol, 50, Resolution.DAILY)
                self.sma_200[symbol] = self.sma(symbol, 200, Resolution.DAILY)
                self.volume_sma[symbol] = self.sma(symbol, 20, Resolution.DAILY, Field.VOLUME)

        for security in changes.removed_securities:
            symbol = security.symbol
            if symbol in self.active_symbols:
                self.active_symbols.remove(symbol)
            if symbol in self.stock_added_in_regime:
                del self.stock_added_in_regime[symbol]
            if self.portfolio[symbol].invested:
                self.liquidate(symbol)

    def weekly_check(self):
        self.rebalance_week += 1
        regime = self.get_regime()

        if regime == "HIGH_MOMENTUM":
            # Biweekly rebalance in high momentum regime
            if self.rebalance_week % 2 == 0:
                self.rebalance_high_momentum()
        else:
            # Monthly rebalance in low momentum regime
            if self.rebalance_week % 4 == 0:
                self.rebalance_low_momentum()

    def rebalance_high_momentum(self):
        """
        HIGH MOMENTUM STRATEGY:
        - Aggressive momentum ranking
        - Acceleration bonus
        - Momentum-weighted allocation
        """
        if self.is_warming_up:
            return
        if len(self.active_symbols) == 0:
            return

        # Check market regime - must be above 200 SMA
        if not self.spy_sma_200.is_ready:
            return
        spy_price = self.securities[self.spy].price
        if spy_price < self.spy_sma_200.current.value:
            self.liquidate()
            return

        # Also check QQQ conditions for extra safety
        if not self.qqq_sma_50.is_ready:
            return
        qqq_price = self.securities[self.qqq].price
        if qqq_price < self.qqq_sma_50.current.value:
            # Scale down if QQQ weakening
            pass

        # Exit weak positions first
        for holding in list(self.portfolio.values()):
            if holding.invested and holding.symbol in self.active_symbols:
                if holding.symbol in self.short_mom and self.short_mom[holding.symbol].is_ready:
                    if self.short_mom[holding.symbol].current.value < -15:
                        self.liquidate(holding.symbol)

        scores = {}
        for symbol in self.active_symbols:
            if symbol not in self.momentum or not self.momentum[symbol].is_ready:
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

            mom = self.momentum[symbol].current.value
            short_mom = self.short_mom[symbol].current.value

            # Filter: positive momentum, not crashing
            if mom <= 0 or short_mom < -10:
                continue

            # Acceleration bonus
            prev_mom = self.prev_short_mom.get(symbol, 0)
            acceleration = short_mom - prev_mom
            self.prev_short_mom[symbol] = short_mom

            accel_bonus = 1.4 if acceleration > 0 else 1.0
            scores[symbol] = mom * accel_bonus

        if len(scores) < 3:
            return

        actual_n = min(self.high_mom_top_n, len(scores))
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_symbols = [s for s, _ in ranked[:actual_n]]

        # Momentum-weighted allocation
        total_score = sum(scores[s] for s in top_symbols)
        weights = {s: (scores[s] / total_score) for s in top_symbols}

        for holding in self.portfolio.values():
            if holding.invested and holding.symbol not in top_symbols:
                self.liquidate(holding.symbol)

        for symbol in top_symbols:
            self.set_holdings(symbol, weights[symbol])

    def rebalance_low_momentum(self):
        """
        LOW MOMENTUM STRATEGY:
        - Trend following (golden cross filter)
        - Quality bias (larger caps)
        - Equal weight allocation
        """
        if self.is_warming_up:
            return
        if len(self.active_symbols) == 0:
            return

        # Check market regime
        if not self.spy_sma_200.is_ready:
            return
        spy_price = self.securities[self.spy].price
        if spy_price < self.spy_sma_200.current.value:
            self.liquidate()
            return

        scores = {}
        for symbol in self.active_symbols:
            if symbol not in self.momentum or not self.momentum[symbol].is_ready:
                continue
            if symbol not in self.sma_50 or not self.sma_50[symbol].is_ready:
                continue
            if symbol not in self.sma_200 or not self.sma_200[symbol].is_ready:
                continue
            if not self.securities[symbol].has_data:
                continue

            price = self.securities[symbol].price
            if price < 10:
                continue
            if symbol in self.volume_sma and self.volume_sma[symbol].is_ready:
                if self.volume_sma[symbol].current.value * price < self.min_dollar_volume:
                    continue

            sma50 = self.sma_50[symbol].current.value
            sma200 = self.sma_200[symbol].current.value
            mom = self.momentum[symbol].current.value

            # TREND FILTER (golden cross + price above both)
            if price <= sma50:
                continue
            if sma50 <= sma200:
                continue
            if mom <= 0:
                continue

            # Score by momentum, but less aggressive
            scores[symbol] = mom

        if len(scores) < 3:
            self.liquidate()
            return

        actual_n = min(self.low_mom_top_n, len(scores))
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_symbols = [s for s, _ in ranked[:actual_n]]

        # Equal weight allocation (more conservative)
        target_weight = 1.0 / actual_n

        for holding in self.portfolio.values():
            if holding.invested and holding.symbol not in top_symbols:
                self.liquidate(holding.symbol)

        for symbol in top_symbols:
            self.set_holdings(symbol, target_weight)
