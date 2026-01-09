"""
v12 Dynamic Universe - Selects high-beta growth stocks programmatically

Instead of hand-picking stocks, dynamically select based on:
- Beta > 1.3
- Market cap $2B - $500B
- Price > $10
- Dollar volume > $20M daily
- Positive 6-month momentum

Universe refresh: Configurable (once, 6 months, yearly)
"""

from AlgorithmImports import *
from datetime import timedelta


class V12DynamicUniverse(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.set_security_initializer(lambda security: security.set_slippage_model(
            ConstantSlippageModel(0.001)
        ))
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        # Strategy parameters
        self.lookback_days = 126
        self.accel_period = 21
        self.top_n = 8
        self.min_dollar_volume = 5_000_000

        # Universe selection parameters
        self.universe_size = 50  # Select top 50 high-beta stocks
        self.min_beta = 1.3
        self.min_market_cap = 2e9  # $2B
        self.max_market_cap = 500e9  # $500B
        self.min_price = 10
        self.min_avg_dollar_volume = 20e6  # $20M daily

        # Universe refresh frequency: "once", "6m", "yearly"
        self.universe_refresh = "yearly"
        self.last_universe_refresh = None

        self.prev_short_mom = {}
        self.rebalance_week = 0

        # Dynamic universe - will be populated
        self.active_symbols = []
        self.momentum = {}
        self.short_mom = {}
        self.volume_sma = {}

        # Regime filters
        self.qqq = self.add_equity("QQQ", Resolution.DAILY).symbol
        self.qqq_sma_10 = self.sma(self.qqq, 10, Resolution.DAILY)
        self.qqq_sma_20 = self.sma(self.qqq, 20, Resolution.DAILY)
        self.qqq_sma_50 = self.sma(self.qqq, 50, Resolution.DAILY)
        self.qqq_mom = self.roc(self.qqq, 63, Resolution.DAILY)

        # Add universe selection
        self.add_universe(self.coarse_filter, self.fine_filter)

        self.set_warm_up(self.lookback_days + 10, Resolution.DAILY)

        # Biweekly rebalance
        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.after_market_open("QQQ", 30),
            self.maybe_rebalance
        )
        self.set_benchmark("QQQ")

    def should_refresh_universe(self):
        """Check if universe should be refreshed based on frequency setting."""
        if self.last_universe_refresh is None:
            return True

        if self.universe_refresh == "once":
            return False
        elif self.universe_refresh == "6m":
            return (self.time - self.last_universe_refresh).days >= 180
        elif self.universe_refresh == "yearly":
            return (self.time - self.last_universe_refresh).days >= 365
        return False

    def coarse_filter(self, coarse):
        """First pass: filter by price, volume, and has fundamental data."""
        if not self.should_refresh_universe():
            return Universe.UNCHANGED

        # Filter for liquid stocks with fundamental data
        filtered = [x for x in coarse
                   if x.has_fundamental_data
                   and x.price > self.min_price
                   and x.dollar_volume > self.min_avg_dollar_volume]

        # Sort by dollar volume and take top candidates
        sorted_by_volume = sorted(filtered, key=lambda x: x.dollar_volume, reverse=True)

        return [x.symbol for x in sorted_by_volume[:500]]

    def fine_filter(self, fine):
        """Second pass: filter by market cap, beta, and sector."""
        if not self.should_refresh_universe():
            return Universe.UNCHANGED

        # Filter by market cap
        filtered = [x for x in fine
                   if x.market_cap > self.min_market_cap
                   and x.market_cap < self.max_market_cap]

        # Filter by beta (high beta stocks)
        # Note: Beta might not always be available
        high_beta = []
        for x in filtered:
            try:
                if hasattr(x, 'beta') and x.beta is not None and x.beta > self.min_beta:
                    high_beta.append(x)
                elif not hasattr(x, 'beta') or x.beta is None:
                    # Include stocks without beta data but in growth sectors
                    if x.asset_classification.morningstar_sector_code in [
                        MorningstarSectorCode.TECHNOLOGY,
                        MorningstarSectorCode.CONSUMER_CYCLICAL,
                        MorningstarSectorCode.HEALTHCARE,
                        MorningstarSectorCode.COMMUNICATION_SERVICES
                    ]:
                        high_beta.append(x)
            except:
                continue

        # Sort by market cap (prefer mid-caps) and momentum proxy (price performance)
        # Take top N by dollar volume within high-beta set
        sorted_stocks = sorted(high_beta, key=lambda x: x.dollar_volume, reverse=True)

        selected = [x.symbol for x in sorted_stocks[:self.universe_size]]

        self.last_universe_refresh = self.time
        self.log(f"Universe refreshed: {len(selected)} stocks selected at {self.time.date()}")

        return selected

    def on_securities_changed(self, changes):
        """Handle universe changes - set up indicators for new stocks."""
        for security in changes.added_securities:
            symbol = security.symbol
            if symbol == self.qqq:
                continue

            if symbol not in self.active_symbols:
                self.active_symbols.append(symbol)

            # Create indicators if not exists
            if symbol not in self.momentum:
                self.momentum[symbol] = self.roc(symbol, self.lookback_days, Resolution.DAILY)
                self.short_mom[symbol] = self.roc(symbol, self.accel_period, Resolution.DAILY)
                self.volume_sma[symbol] = self.sma(symbol, 20, Resolution.DAILY, Field.VOLUME)

        for security in changes.removed_securities:
            symbol = security.symbol
            if symbol in self.active_symbols:
                self.active_symbols.remove(symbol)
            # Liquidate removed stocks
            if self.portfolio[symbol].invested:
                self.liquidate(symbol)

    def maybe_rebalance(self):
        self.rebalance_week += 1
        if self.rebalance_week % 2 == 0:
            self.rebalance()

    def rebalance(self):
        if self.is_warming_up:
            return

        if len(self.active_symbols) == 0:
            return

        qqq_price = self.securities[self.qqq].price

        if not self.qqq_sma_10.is_ready or not self.qqq_sma_20.is_ready or not self.qqq_sma_50.is_ready:
            return

        above_10 = qqq_price > self.qqq_sma_10.current.value
        above_20 = qqq_price > self.qqq_sma_20.current.value
        above_50 = qqq_price > self.qqq_sma_50.current.value
        qqq_mom_positive = self.qqq_mom.is_ready and self.qqq_mom.current.value > 0

        # Fast exit: below 10 SMA
        if not above_10:
            self.liquidate()
            return

        # Exit weak positions
        for holding in list(self.portfolio.values()):
            if holding.invested and holding.symbol in self.active_symbols:
                if holding.symbol in self.short_mom and self.short_mom[holding.symbol].is_ready:
                    if self.short_mom[holding.symbol].current.value < -15:
                        self.liquidate(holding.symbol)

        # Determine leverage based on regime
        if above_10 and above_20 and above_50 and qqq_mom_positive:
            leverage = 1.0
        elif above_10 and above_20:
            leverage = 1.0
        else:
            leverage = 0.8

        scores = {}

        for symbol in self.active_symbols:
            if symbol not in self.momentum:
                continue
            if not self.momentum[symbol].is_ready:
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

            if short_mom < -10:
                continue

            prev_mom = self.prev_short_mom.get(symbol, 0)
            acceleration = short_mom - prev_mom
            self.prev_short_mom[symbol] = short_mom

            if mom > 0:
                accel_bonus = 1.4 if acceleration > 0 else 1.0
                scores[symbol] = mom * accel_bonus

        if len(scores) < 3:
            return

        actual_n = min(self.top_n, len(scores))
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_symbols = [s for s, _ in ranked[:actual_n]]

        total_score = sum(scores[s] for s in top_symbols)
        weights = {s: (scores[s] / total_score) * leverage for s in top_symbols}

        for holding in self.portfolio.values():
            if holding.invested and holding.symbol not in top_symbols:
                self.liquidate(holding.symbol)

        for symbol in top_symbols:
            self.set_holdings(symbol, weights[symbol])
