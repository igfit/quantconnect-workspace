from AlgorithmImports import *
import numpy as np

class EMADynamicAnnualV58(QCAlgorithm):
    """
    V58: HARDCODED REGIME UNIVERSE SELECTION

    Key insight: Regime detection doesn't need to be algorithmic.
    Regimes change on multi-year timeframes, so we can hardcode them
    and use different universe selection for each.

    REGIME DEFINITIONS (externally determined):

    QUALITY_BULL (2015-2019 style):
    - Normal bull market, fundamentals matter
    - Quality + momentum works best
    - Lower volatility preferred
    - Large cap safer

    SPECULATIVE_BULL (2020-2024 style):
    - Bubble/speculative environment
    - Pure momentum, high vol works
    - Small caps can explode
    - Quality doesn't matter

    REGIME CHARACTERISTICS (how to identify externally):

    SPECULATIVE_BULL signals:
    - VIX persistently < 15 while SPY at highs
    - IPO/SPAC frenzy
    - Meme stock activity
    - Momentum factor >> Value factor
    - Narrow market leadership
    - SPY > 15% above 200 SMA

    QUALITY_BULL signals:
    - VIX 15-25 range
    - Broad market participation
    - Quality stocks outperforming
    - Value and momentum both work
    - IPO activity normal

    UNIVERSE SELECTION BY REGIME:

    QUALITY_BULL:
    - Large cap only (>$10B)
    - Must be profitable (EPS > 0)
    - Moderate volatility (30th-70th percentile)
    - Good ROE (>10%)
    - Positive 6m AND 3m momentum

    SPECULATIVE_BULL:
    - No market cap floor
    - No profitability requirement
    - Top 10% volatility
    - Positive 6m AND 3m momentum

    HARDCODED DATES (adjust based on external analysis):
    - 2015-01-01 to 2019-12-31: QUALITY_BULL
    - 2020-01-01 to 2024-12-31: SPECULATIVE_BULL
    """

    def initialize(self):
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100000)

        # ============================================
        # REGIME DATE RANGES (HARDCODED - ADJUST EXTERNALLY)
        # ============================================
        self.regime_dates = [
            # (start_date, end_date, regime_name)
            (datetime(2015, 1, 1), datetime(2019, 12, 31), "QUALITY_BULL"),
            (datetime(2020, 1, 1), datetime(2024, 12, 31), "SPECULATIVE_BULL"),
        ]
        # ============================================

        self.current_regime = "QUALITY_BULL"

        # Common settings
        self.universe_size = 30
        self.min_price = 10.0
        self.min_dollar_volume = 10_000_000
        self.momentum_lookback = 126
        self.short_momentum_lookback = 63

        # Position sizing (same for both regimes)
        self.max_positions = 5
        self.weight_per_stock = 0.20

        # Entry/exit
        self.ema_fast = 20
        self.ema_slow = 100
        self.trailing_stop_pct = 0.25

        self.indicators = {}
        self.prev_ema = {}
        self.current_universe = set()
        self.held_symbols = set()
        self.momentum_scores = {}
        self.last_refresh_key = None
        self.universe_symbols = []
        self.highest_prices = {}

        self.add_universe(self.coarse_filter, self.fine_filter)
        self.universe_settings.resolution = Resolution.DAILY
        self.universe_settings.minimum_time_in_universe = timedelta(days=30)

        self.set_benchmark("SPY")
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)
        self.set_warm_up(120, Resolution.DAILY)

    def get_current_regime(self):
        """Determine regime based on hardcoded date ranges"""
        current_date = self.time
        for start_date, end_date, regime in self.regime_dates:
            if start_date <= current_date <= end_date:
                return regime
        # Default fallback
        return "QUALITY_BULL"

    def get_half_year_key(self):
        year = self.time.year
        half = 1 if self.time.month <= 6 else 2
        regime = self.get_current_regime()
        return f"{year}H{half}_{regime}"

    def coarse_filter(self, coarse):
        # Update regime
        new_regime = self.get_current_regime()
        if new_regime != self.current_regime:
            self.debug(f"REGIME CHANGE: {self.current_regime} -> {new_regime}")
            self.current_regime = new_regime
            # Force universe refresh
            self.last_refresh_key = None

        current_key = self.get_half_year_key()
        refresh_months = [1, 7]

        if self.last_refresh_key == current_key:
            return list(set(self.universe_symbols) | self.held_symbols)
        if self.time.month not in refresh_months and self.last_refresh_key is not None:
            return list(set(self.universe_symbols) | self.held_symbols)

        filtered = [x for x in coarse
                   if x.has_fundamental_data
                   and x.price > self.min_price
                   and x.dollar_volume > self.min_dollar_volume]

        sorted_by_volume = sorted(filtered, key=lambda x: x.dollar_volume, reverse=True)
        return [x.symbol for x in sorted_by_volume[:400]]

    def fine_filter(self, fine):
        current_key = self.get_half_year_key()
        refresh_months = [1, 7]

        if self.last_refresh_key == current_key:
            return list(set(self.universe_symbols) | self.held_symbols)
        if self.time.month not in refresh_months and self.last_refresh_key is not None:
            return list(set(self.universe_symbols) | self.held_symbols)

        regime = self.current_regime
        self.debug(f"Fine filter with regime: {regime}")

        # Exclude financials, RE, utilities in both regimes
        excluded_sectors = [103, 104, 207]

        stock_metrics = []

        for x in fine:
            try:
                # Sector filter
                if x.asset_classification.morningstar_sector_code in excluded_sectors:
                    continue

                symbol = x.symbol

                # ====== REGIME-SPECIFIC FILTERS ======

                if regime == "QUALITY_BULL":
                    # Large cap only
                    if not x.market_cap or x.market_cap < 10e9:
                        continue

                    # Must be profitable
                    if not x.earning_reports.basic_eps.three_months:
                        continue
                    if x.earning_reports.basic_eps.three_months <= 0:
                        continue

                    # Good ROE (>10%)
                    if x.operation_ratios.roe.value:
                        if x.operation_ratios.roe.value < 0.10:
                            continue

                # SPECULATIVE_BULL: No additional filters
                # (allow any market cap, unprofitable, etc.)

                # ====== MOMENTUM CALCULATION ======

                history = self.history(symbol, self.momentum_lookback + 10, Resolution.DAILY)
                if len(history) < self.momentum_lookback:
                    continue

                start_price_6m = history['close'].iloc[-self.momentum_lookback]
                end_price = history['close'].iloc[-1]
                start_price_3m = history['close'].iloc[-self.short_momentum_lookback]

                if start_price_6m <= 0 or start_price_3m <= 0:
                    continue

                momentum_6m = (end_price - start_price_6m) / start_price_6m
                momentum_3m = (end_price - start_price_3m) / start_price_3m

                # Both regimes require positive dual momentum
                if momentum_6m <= 0 or momentum_3m <= 0:
                    continue

                returns = history['close'].pct_change().dropna()
                vol = returns.std() * np.sqrt(252)

                stock_metrics.append((symbol, momentum_6m, vol))

            except:
                pass

        if not stock_metrics:
            return list(self.held_symbols)

        # ====== REGIME-SPECIFIC VOLATILITY FILTER ======

        vols = [x[2] for x in stock_metrics]

        if regime == "QUALITY_BULL":
            # Moderate volatility: 30th to 70th percentile
            # Avoid both low-vol (boring) and high-vol (risky)
            if len(vols) >= 10:
                vol_30th = np.percentile(vols, 30)
                vol_70th = np.percentile(vols, 70)
                selected = [x for x in stock_metrics if vol_30th <= x[2] <= vol_70th]
            else:
                selected = stock_metrics

        elif regime == "SPECULATIVE_BULL":
            # Top 10% volatility (V30 style)
            if len(vols) >= 10:
                vol_90th = np.percentile(vols, 90)
                selected = [x for x in stock_metrics if x[2] >= vol_90th]
            else:
                selected = stock_metrics

        else:
            selected = stock_metrics

        if not selected:
            selected = stock_metrics

        # Sort by momentum and take top
        selected.sort(key=lambda x: x[1], reverse=True)
        top_stocks = [x[0] for x in selected[:self.universe_size]]

        self.momentum_scores = {x[0]: x[1] for x in selected[:self.universe_size]}
        self.universe_symbols = top_stocks
        self.last_refresh_key = current_key

        self.debug(f"Universe: {len(top_stocks)} stocks for {regime}")

        return list(set(top_stocks) | self.held_symbols)

    def on_securities_changed(self, changes):
        for security in changes.removed_securities:
            symbol = security.symbol
            if symbol not in self.held_symbols:
                self.indicators.pop(symbol, None)
                self.prev_ema.pop(symbol, None)
            self.current_universe.discard(symbol)

        for security in changes.added_securities:
            symbol = security.symbol
            self.current_universe.add(symbol)
            if symbol not in self.indicators:
                self.indicators[symbol] = {
                    'ema_fast': self.ema(symbol, self.ema_fast, Resolution.DAILY),
                    'ema_slow': self.ema(symbol, self.ema_slow, Resolution.DAILY),
                }
                self.prev_ema[symbol] = {'fast': None, 'slow': None}

    def on_data(self, data):
        if self.is_warming_up:
            return

        position_count = len(self.held_symbols)
        entry_candidates = []

        for symbol in list(self.current_universe | self.held_symbols):
            if symbol not in data.bars or symbol not in self.indicators:
                continue

            ind = self.indicators[symbol]
            if not ind['ema_fast'].is_ready or not ind['ema_slow'].is_ready:
                continue

            current_price = data.bars[symbol].close
            ema_fast = ind['ema_fast'].current.value
            ema_slow = ind['ema_slow'].current.value

            prev = self.prev_ema.get(symbol, {'fast': None, 'slow': None})
            if prev['fast'] is None:
                self.prev_ema[symbol] = {'fast': ema_fast, 'slow': ema_slow}
                continue

            bullish_cross = prev['fast'] <= prev['slow'] and ema_fast > ema_slow
            bearish_cross = prev['fast'] >= prev['slow'] and ema_fast < ema_slow

            if symbol in self.held_symbols:
                if symbol not in self.highest_prices:
                    self.highest_prices[symbol] = current_price
                else:
                    self.highest_prices[symbol] = max(self.highest_prices[symbol], current_price)

                high = self.highest_prices[symbol]
                stop_price = high * (1 - self.trailing_stop_pct)
                if current_price < stop_price:
                    self.liquidate(symbol, "Trailing Stop")
                    self.held_symbols.discard(symbol)
                    self.highest_prices.pop(symbol, None)
                    position_count -= 1
                    self.prev_ema[symbol] = {'fast': ema_fast, 'slow': ema_slow}
                    continue

                if bearish_cross:
                    self.liquidate(symbol, "EMA Exit")
                    self.held_symbols.discard(symbol)
                    self.highest_prices.pop(symbol, None)
                    position_count -= 1

            elif bullish_cross and symbol in self.current_universe:
                entry_candidates.append((symbol, self.momentum_scores.get(symbol, 0), current_price))

            self.prev_ema[symbol] = {'fast': ema_fast, 'slow': ema_slow}

        if entry_candidates and position_count < self.max_positions:
            entry_candidates.sort(key=lambda x: x[1], reverse=True)
            for symbol, _, price in entry_candidates:
                if position_count >= self.max_positions:
                    break
                self.set_holdings(symbol, self.weight_per_stock)
                self.held_symbols.add(symbol)
                self.highest_prices[symbol] = price
                position_count += 1
