from AlgorithmImports import *
import numpy as np

class EMADynamicAnnualV27(QCAlgorithm):
    """
    V27: SEMI-ANNUAL REFRESH + TOP 30 UNIVERSE

    Changes from V26:
    - Semi-annual universe refresh (January and July)
    - Smaller universe: top 30 (more selective)
    - Only top decile volatility (more aggressive)
    - Require positive 3-month momentum

    Max 1x leverage: 5 positions at 20%
    Target: 28%+ CAGR
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100000)

        self.universe_size = 30  # Smaller, more selective
        self.min_price = 10.0
        self.min_dollar_volume = 10_000_000
        self.momentum_lookback = 126  # 6-month momentum
        self.short_momentum_lookback = 63  # 3-month momentum
        self.volatility_lookback = 60

        self.max_positions = 5
        self.weight_per_stock = 0.20

        self.ema_fast = 20
        self.ema_slow = 100

        self.indicators = {}
        self.prev_ema = {}
        self.current_universe = set()
        self.held_symbols = set()
        self.momentum_scores = {}
        self.last_refresh_key = None  # Track half-year
        self.universe_symbols = []

        self.add_universe(self.coarse_filter, self.fine_filter)
        self.universe_settings.resolution = Resolution.DAILY
        self.universe_settings.minimum_time_in_universe = timedelta(days=30)

        self.set_benchmark("SPY")
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)
        self.set_warm_up(120, Resolution.DAILY)

    def get_half_year_key(self):
        """Return key for current half-year period"""
        year = self.time.year
        half = 1 if self.time.month <= 6 else 2
        return f"{year}H{half}"

    def coarse_filter(self, coarse):
        current_key = self.get_half_year_key()
        refresh_months = [1, 7]  # January and July

        if self.last_refresh_key == current_key:
            return list(set(self.universe_symbols) | self.held_symbols)

        if self.time.month not in refresh_months and self.last_refresh_key is not None:
            return list(set(self.universe_symbols) | self.held_symbols)

        self.debug(f"SEMI-ANNUAL REFRESH: {current_key}")

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

        filtered = [x for x in fine
                   if x.asset_classification.morningstar_sector_code not in [103, 104, 207]]

        stock_metrics = []
        for symbol in [x.symbol for x in filtered]:
            try:
                history = self.history(symbol, self.momentum_lookback + 10, Resolution.DAILY)
                if len(history) >= self.momentum_lookback:
                    # 6-month momentum
                    start_price_6m = history['close'].iloc[-self.momentum_lookback]
                    end_price = history['close'].iloc[-1]

                    # 3-month momentum
                    start_price_3m = history['close'].iloc[-self.short_momentum_lookback]

                    if start_price_6m > 0 and start_price_3m > 0:
                        momentum_6m = (end_price - start_price_6m) / start_price_6m
                        momentum_3m = (end_price - start_price_3m) / start_price_3m
                        returns = history['close'].pct_change().dropna()
                        vol = returns.std() * np.sqrt(252)

                        # Both 6m and 3m momentum must be positive
                        if momentum_6m > 0 and momentum_3m > 0:
                            stock_metrics.append((symbol, momentum_6m, vol))
            except:
                pass

        if not stock_metrics:
            return list(self.held_symbols)

        # TOP DECILE volatility (top 10%, more aggressive)
        vols = [x[2] for x in stock_metrics]
        if len(vols) >= 10:
            vol_90th = np.percentile(vols, 90)
            high_vol = [x for x in stock_metrics if x[2] >= vol_90th]
        else:
            high_vol = stock_metrics

        high_vol.sort(key=lambda x: x[1], reverse=True)
        top_stocks = [x[0] for x in high_vol[:self.universe_size]]

        self.momentum_scores = {x[0]: x[1] for x in high_vol[:self.universe_size]}
        self.universe_symbols = top_stocks
        self.last_refresh_key = current_key

        self.debug(f"V27 Universe: {len(top_stocks)} stocks for {current_key}")
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

            ema_fast = ind['ema_fast'].current.value
            ema_slow = ind['ema_slow'].current.value

            prev = self.prev_ema.get(symbol, {'fast': None, 'slow': None})
            if prev['fast'] is None:
                self.prev_ema[symbol] = {'fast': ema_fast, 'slow': ema_slow}
                continue

            bullish_cross = prev['fast'] <= prev['slow'] and ema_fast > ema_slow
            bearish_cross = prev['fast'] >= prev['slow'] and ema_fast < ema_slow

            if bearish_cross and symbol in self.held_symbols:
                self.liquidate(symbol)
                self.held_symbols.discard(symbol)
                position_count -= 1
            elif bullish_cross and symbol in self.current_universe and symbol not in self.held_symbols:
                mom_score = self.momentum_scores.get(symbol, 0)
                entry_candidates.append((symbol, mom_score))

            self.prev_ema[symbol] = {'fast': ema_fast, 'slow': ema_slow}

        if entry_candidates and position_count < self.max_positions:
            entry_candidates.sort(key=lambda x: x[1], reverse=True)
            for symbol, _ in entry_candidates:
                if position_count >= self.max_positions:
                    break
                self.set_holdings(symbol, self.weight_per_stock)
                self.held_symbols.add(symbol)
                position_count += 1
