from AlgorithmImports import *
import numpy as np

class EMADynamicAnnualV56(QCAlgorithm):
    """
    V56: ALL-WEATHER MOMENTUM (NO REGIME FILTER)

    Key insight: Regime filtering (SPY < 200 SMA) is a LAGGING indicator
    that causes us to capture losses but miss recoveries.

    New approach: ALWAYS be invested, but in ROBUST positions.

    UNIVERSE SELECTION (focus on quality + momentum):
    - Large cap only (>$10B market cap) - more stable
    - Must be profitable (positive EPS)
    - Top 30% volatility (not extreme 10%)
    - Positive 6m AND 3m momentum

    POSITION SIZING (risk-adjusted):
    - 6 positions @ 16% = 96% exposure
    - 20% trailing stop (tighter)

    The goal: Steady 15-20% CAGR across all market regimes.
    Accept lower peak returns for consistent performance.
    """

    def initialize(self):
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100000)

        # Universe settings
        self.universe_size = 25
        self.min_price = 10.0
        self.min_dollar_volume = 20_000_000  # Higher liquidity requirement
        self.min_market_cap = 10e9  # Large cap only
        self.momentum_lookback = 126
        self.short_momentum_lookback = 63

        # Position sizing (more diversified)
        self.max_positions = 6
        self.weight_per_stock = 0.16  # 96% exposure

        # Entry/exit signals
        self.ema_fast = 20
        self.ema_slow = 100
        self.trailing_stop_pct = 0.20  # Tighter stop

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
        self.set_warm_up(130, Resolution.DAILY)

    def get_half_year_key(self):
        year = self.time.year
        half = 1 if self.time.month <= 6 else 2
        return f"{year}H{half}"

    def coarse_filter(self, coarse):
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

        # Exclude financials, RE, utilities - they're rate-sensitive
        excluded_sectors = [103, 104, 207]

        stock_metrics = []
        for x in fine:
            try:
                # Sector filter
                if x.asset_classification.morningstar_sector_code in excluded_sectors:
                    continue

                # Market cap filter (large cap only)
                if not x.market_cap or x.market_cap < self.min_market_cap:
                    continue

                # Profitability filter
                if not x.earning_reports.basic_eps.three_months:
                    continue
                if x.earning_reports.basic_eps.three_months <= 0:
                    continue

                symbol = x.symbol
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

                        # Dual momentum requirement
                        if momentum_6m > 0 and momentum_3m > 0:
                            stock_metrics.append((symbol, momentum_6m, vol))
            except:
                pass

        if not stock_metrics:
            return list(self.held_symbols)

        # Apply volatility filter: top 30% (not extreme 10%)
        # This gives us momentum stocks that aren't too volatile
        vols = [x[2] for x in stock_metrics]
        if len(vols) >= 10:
            vol_70th = np.percentile(vols, 70)
            vol_95th = np.percentile(vols, 95)  # Exclude extreme outliers
            # Select stocks between 70th and 95th percentile volatility
            selected = [x for x in stock_metrics if vol_70th <= x[2] <= vol_95th]
        else:
            selected = stock_metrics

        if not selected:
            selected = stock_metrics

        # Sort by momentum
        selected.sort(key=lambda x: x[1], reverse=True)
        top_stocks = [x[0] for x in selected[:self.universe_size]]

        self.momentum_scores = {x[0]: x[1] for x in selected[:self.universe_size]}
        self.universe_symbols = top_stocks
        self.last_refresh_key = current_key

        self.debug(f"Universe: {len(top_stocks)} quality momentum stocks")

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

        # NO REGIME FILTER - always process signals

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
