from AlgorithmImports import *
import numpy as np

class EMADynamicAnnualV55(QCAlgorithm):
    """
    V55: CORE-SATELLITE REGIME BLENDING

    Instead of binary regime switching, BLEND strategies:

    CORE (always held, 40% of portfolio):
    - Quality large-cap momentum stocks
    - Lower volatility, profitable companies
    - Provides stable base returns

    SATELLITE (regime-dependent, 0-60% of portfolio):
    - High-vol speculative momentum (V30 style)
    - Full allocation in BULL, zero in BEAR

    REGIME:
    - BULL (SPY > 200 SMA): Core 40% + Satellite 60% = 100%
    - BEAR (SPY < 200 SMA): Core 40% + Cash 60%

    The goal: Capture some bubble returns while maintaining stability.
    """

    def initialize(self):
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100000)

        # SPY for regime
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.spy_sma200 = self.sma(self.spy, 200, Resolution.DAILY)

        self.is_bull_regime = True

        # Universe settings
        self.universe_size = 30
        self.min_price = 10.0
        self.min_dollar_volume = 10_000_000
        self.momentum_lookback = 126
        self.short_momentum_lookback = 63

        # Core settings (quality large-cap)
        self.core_positions = 2
        self.core_weight = 0.20  # 40% total

        # Satellite settings (high-vol momentum)
        self.satellite_positions = 3
        self.satellite_weight = 0.20  # 60% total in bull

        self.ema_fast = 20
        self.ema_slow = 100
        self.trailing_stop_pct = 0.25

        self.indicators = {}
        self.prev_ema = {}
        self.current_universe = set()

        # Separate tracking for core vs satellite
        self.core_symbols = set()
        self.satellite_symbols = set()

        self.core_universe = []
        self.satellite_universe = []

        self.momentum_scores = {}
        self.last_refresh_key = None
        self.universe_symbols = []
        self.highest_prices = {}

        self.add_universe(self.coarse_filter, self.fine_filter)
        self.universe_settings.resolution = Resolution.DAILY
        self.universe_settings.minimum_time_in_universe = timedelta(days=30)

        self.set_benchmark("SPY")
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)
        self.set_warm_up(220, Resolution.DAILY)

    def get_half_year_key(self):
        year = self.time.year
        half = 1 if self.time.month <= 6 else 2
        return f"{year}H{half}"

    def coarse_filter(self, coarse):
        current_key = self.get_half_year_key()
        refresh_months = [1, 7]

        all_held = self.core_symbols | self.satellite_symbols

        if self.last_refresh_key == current_key:
            return list(set(self.universe_symbols) | all_held)
        if self.time.month not in refresh_months and self.last_refresh_key is not None:
            return list(set(self.universe_symbols) | all_held)

        filtered = [x for x in coarse
                   if x.has_fundamental_data
                   and x.price > self.min_price
                   and x.dollar_volume > self.min_dollar_volume]

        sorted_by_volume = sorted(filtered, key=lambda x: x.dollar_volume, reverse=True)
        return [x.symbol for x in sorted_by_volume[:500]]

    def fine_filter(self, fine):
        current_key = self.get_half_year_key()
        refresh_months = [1, 7]

        all_held = self.core_symbols | self.satellite_symbols

        if self.last_refresh_key == current_key:
            return list(set(self.universe_symbols) | all_held)
        if self.time.month not in refresh_months and self.last_refresh_key is not None:
            return list(set(self.universe_symbols) | all_held)

        # Exclude financials, RE, utilities
        filtered = [x for x in fine
                   if x.asset_classification.morningstar_sector_code not in [103, 104, 207]]

        # Separate into quality (large cap, profitable) and speculative candidates
        quality_metrics = []
        speculative_metrics = []

        for x in filtered:
            symbol = x.symbol
            try:
                # Check profitability
                is_profitable = False
                if x.earning_reports.basic_eps.three_months:
                    is_profitable = x.earning_reports.basic_eps.three_months > 0

                # Check market cap (>$10B for quality)
                is_large_cap = x.market_cap and x.market_cap > 10e9

                history = self.history(symbol, self.momentum_lookback + 10, Resolution.DAILY)
                if len(history) >= self.momentum_lookback:
                    start_price_6m = history['close'].iloc[-self.momentum_lookback]
                    end_price = history['close'].iloc[-1]
                    start_price_3m = history['close'].iloc[-self.short_momentum_lookback]

                    if start_price_6m > 0 and start_price_3m > 0:
                        momentum_6m = (end_price - start_price_6m) / start_price_6m
                        momentum_3m = (end_price - start_price_3m) / start_price_3m
                        returns = history['close'].pct_change().dropna()
                        vol = returns.std() * np.sqrt(252)

                        if momentum_6m > 0 and momentum_3m > 0:
                            # Quality: large cap + profitable + lower vol
                            if is_large_cap and is_profitable and vol < 0.5:
                                quality_metrics.append((symbol, momentum_6m, vol))

                            # Speculative: high vol
                            speculative_metrics.append((symbol, momentum_6m, vol))
            except:
                pass

        # Select top quality stocks (sorted by momentum)
        quality_metrics.sort(key=lambda x: x[1], reverse=True)
        self.core_universe = [x[0] for x in quality_metrics[:10]]

        # Select top 10% vol speculative stocks
        if speculative_metrics:
            vols = [x[2] for x in speculative_metrics]
            if len(vols) >= 10:
                vol_90th = np.percentile(vols, 90)
                high_vol = [x for x in speculative_metrics if x[2] >= vol_90th]
            else:
                high_vol = speculative_metrics

            high_vol.sort(key=lambda x: x[1], reverse=True)
            self.satellite_universe = [x[0] for x in high_vol[:20]]
        else:
            self.satellite_universe = []

        # Combine for momentum scores
        all_metrics = quality_metrics + speculative_metrics
        self.momentum_scores = {x[0]: x[1] for x in all_metrics}

        # Combine universes
        self.universe_symbols = list(set(self.core_universe + self.satellite_universe))
        self.last_refresh_key = current_key

        self.debug(f"Universe: {len(self.core_universe)} core, {len(self.satellite_universe)} satellite")

        return list(set(self.universe_symbols) | all_held)

    def on_securities_changed(self, changes):
        all_held = self.core_symbols | self.satellite_symbols

        for security in changes.removed_securities:
            symbol = security.symbol
            if symbol not in all_held and symbol != self.spy:
                self.indicators.pop(symbol, None)
                self.prev_ema.pop(symbol, None)
            self.current_universe.discard(symbol)

        for security in changes.added_securities:
            symbol = security.symbol
            if symbol == self.spy:
                continue
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

        if not self.spy_sma200.is_ready:
            return

        # Regime check
        spy_price = self.securities[self.spy].price
        sma200 = self.spy_sma200.current.value
        was_bull = self.is_bull_regime
        self.is_bull_regime = spy_price > sma200

        # If regime changed to BEAR, exit satellite positions only
        if was_bull and not self.is_bull_regime:
            self.debug(f"REGIME -> BEAR: Liquidating satellite positions")
            for symbol in list(self.satellite_symbols):
                self.liquidate(symbol, "Regime -> BEAR")
                self.highest_prices.pop(symbol, None)
            self.satellite_symbols.clear()

        # Process all positions
        core_count = len(self.core_symbols)
        satellite_count = len(self.satellite_symbols)

        core_candidates = []
        satellite_candidates = []

        all_held = self.core_symbols | self.satellite_symbols

        for symbol in list(self.current_universe | all_held):
            if symbol == self.spy:
                continue
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

            # Handle existing positions
            if symbol in all_held:
                if symbol not in self.highest_prices:
                    self.highest_prices[symbol] = current_price
                else:
                    self.highest_prices[symbol] = max(self.highest_prices[symbol], current_price)

                high = self.highest_prices[symbol]
                stop_price = high * (1 - self.trailing_stop_pct)

                should_exit = current_price < stop_price or bearish_cross

                if should_exit:
                    self.liquidate(symbol, "Exit")
                    self.highest_prices.pop(symbol, None)
                    if symbol in self.core_symbols:
                        self.core_symbols.discard(symbol)
                        core_count -= 1
                    if symbol in self.satellite_symbols:
                        self.satellite_symbols.discard(symbol)
                        satellite_count -= 1

            # Entry signals
            elif bullish_cross:
                # Check if candidate for core or satellite
                if symbol in self.core_universe:
                    core_candidates.append((symbol, self.momentum_scores.get(symbol, 0), current_price))
                if symbol in self.satellite_universe and self.is_bull_regime:
                    satellite_candidates.append((symbol, self.momentum_scores.get(symbol, 0), current_price))

            self.prev_ema[symbol] = {'fast': ema_fast, 'slow': ema_slow}

        # Add core positions
        if core_candidates and core_count < self.core_positions:
            core_candidates.sort(key=lambda x: x[1], reverse=True)
            for symbol, _, price in core_candidates:
                if core_count >= self.core_positions:
                    break
                if symbol not in self.core_symbols and symbol not in self.satellite_symbols:
                    self.set_holdings(symbol, self.core_weight)
                    self.core_symbols.add(symbol)
                    self.highest_prices[symbol] = price
                    core_count += 1

        # Add satellite positions (only in BULL)
        if self.is_bull_regime and satellite_candidates and satellite_count < self.satellite_positions:
            satellite_candidates.sort(key=lambda x: x[1], reverse=True)
            for symbol, _, price in satellite_candidates:
                if satellite_count >= self.satellite_positions:
                    break
                if symbol not in self.core_symbols and symbol not in self.satellite_symbols:
                    self.set_holdings(symbol, self.satellite_weight)
                    self.satellite_symbols.add(symbol)
                    self.highest_prices[symbol] = price
                    satellite_count += 1
