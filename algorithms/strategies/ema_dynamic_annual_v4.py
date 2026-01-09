from AlgorithmImports import *
import numpy as np

class EMADynamicAnnualV4(QCAlgorithm):
    """
    EMA Crossover with Dynamic Universe - V4 AGGRESSIVE

    Changes from V2:
    - More concentrated: 6 positions at 16.67% (vs 8 at 12.5%)
    - Faster EMAs: 15/75 (vs 20/100)
    - Added RSI filter: only enter when RSI < 60 (not overbought)
    - Larger universe: top 60 (vs 40) for more opportunities

    Target: 30% CAGR with acceptable DD
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100000)

        # Universe settings - larger pool
        self.universe_size = 60
        self.min_price = 10.0
        self.min_dollar_volume = 10_000_000
        self.momentum_lookback = 126
        self.volatility_lookback = 60

        # More concentrated positions
        self.max_positions = 6
        self.weight_per_stock = 0.1667  # 16.67%

        # Faster EMAs
        self.ema_fast = 15
        self.ema_slow = 75

        # Tracking
        self.indicators = {}
        self.prev_ema = {}
        self.current_universe = set()
        self.held_symbols = set()
        self.last_refresh_year = -1
        self.universe_symbols = []

        self.add_universe(self.coarse_filter, self.fine_filter)
        self.universe_settings.resolution = Resolution.DAILY
        self.universe_settings.minimum_time_in_universe = timedelta(days=30)

        self.set_benchmark("SPY")
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)
        self.set_warm_up(100, Resolution.DAILY)

    def coarse_filter(self, coarse):
        current_year = self.time.year
        current_month = self.time.month

        if self.last_refresh_year == current_year:
            return list(set(self.universe_symbols) | self.held_symbols)

        if current_month != 1 and self.last_refresh_year != -1:
            return list(set(self.universe_symbols) | self.held_symbols)

        self.debug(f"ANNUAL REFRESH: Year {current_year}")

        filtered = [x for x in coarse
                   if x.has_fundamental_data
                   and x.price > self.min_price
                   and x.dollar_volume > self.min_dollar_volume]

        sorted_by_volume = sorted(filtered, key=lambda x: x.dollar_volume, reverse=True)
        return [x.symbol for x in sorted_by_volume[:500]]

    def fine_filter(self, fine):
        current_year = self.time.year
        current_month = self.time.month

        if self.last_refresh_year == current_year:
            return list(set(self.universe_symbols) | self.held_symbols)

        if current_month != 1 and self.last_refresh_year != -1:
            return list(set(self.universe_symbols) | self.held_symbols)

        # Filter sectors
        filtered = [x for x in fine
                   if x.asset_classification.morningstar_sector_code not in [103, 104, 207]]

        symbols = [x.symbol for x in filtered]

        stock_metrics = []
        for symbol in symbols:
            try:
                history = self.history(symbol, max(self.momentum_lookback, self.volatility_lookback), Resolution.DAILY)
                if len(history) >= self.momentum_lookback * 0.8:
                    start_price = history['close'].iloc[-self.momentum_lookback]
                    end_price = history['close'].iloc[-1]
                    if start_price > 0:
                        momentum = (end_price - start_price) / start_price
                        returns = history['close'].pct_change().dropna()
                        vol = returns.std() * np.sqrt(252)
                        if momentum > 0:
                            stock_metrics.append((symbol, momentum, vol))
            except:
                pass

        if not stock_metrics:
            return list(self.held_symbols)

        # Filter to above-median volatility
        vols = [x[2] for x in stock_metrics]
        median_vol = np.median(vols)

        volatile_momentum = [x for x in stock_metrics if x[2] >= median_vol]
        volatile_momentum.sort(key=lambda x: x[1], reverse=True)
        top_stocks = [x[0] for x in volatile_momentum[:self.universe_size]]

        self.universe_symbols = top_stocks
        self.last_refresh_year = current_year

        self.debug(f"Universe: {len(top_stocks)} stocks for {current_year}")
        if volatile_momentum:
            self.debug(f"Top: {volatile_momentum[0][0].value} mom={volatile_momentum[0][1]:.1%}")

        return list(set(top_stocks) | self.held_symbols)

    def on_securities_changed(self, changes):
        for security in changes.removed_securities:
            symbol = security.symbol
            if symbol not in self.held_symbols:
                if symbol in self.indicators:
                    del self.indicators[symbol]
                if symbol in self.prev_ema:
                    del self.prev_ema[symbol]
            self.current_universe.discard(symbol)

        for security in changes.added_securities:
            symbol = security.symbol
            self.current_universe.add(symbol)
            if symbol not in self.indicators:
                self.indicators[symbol] = {
                    'ema_fast': self.ema(symbol, self.ema_fast, Resolution.DAILY),
                    'ema_slow': self.ema(symbol, self.ema_slow, Resolution.DAILY),
                    'rsi': self.rsi(symbol, 14, MovingAverageType.SIMPLE, Resolution.DAILY),
                }
                self.prev_ema[symbol] = {'fast': None, 'slow': None}

    def on_data(self, data):
        if self.is_warming_up:
            return

        position_count = len(self.held_symbols)
        symbols_to_check = self.current_universe | self.held_symbols

        for symbol in list(symbols_to_check):
            if symbol not in data.bars:
                continue
            if symbol not in self.indicators:
                continue

            ind = self.indicators[symbol]
            if not ind['ema_fast'].is_ready or not ind['ema_slow'].is_ready:
                continue
            if not ind['rsi'].is_ready:
                continue

            ema_fast = ind['ema_fast'].current.value
            ema_slow = ind['ema_slow'].current.value
            rsi = ind['rsi'].current.value

            prev = self.prev_ema.get(symbol, {'fast': None, 'slow': None})
            if prev['fast'] is None:
                self.prev_ema[symbol] = {'fast': ema_fast, 'slow': ema_slow}
                continue

            bullish_cross = prev['fast'] <= prev['slow'] and ema_fast > ema_slow
            bearish_cross = prev['fast'] >= prev['slow'] and ema_fast < ema_slow

            # Entry: EMA cross + RSI not overbought
            if bullish_cross and rsi < 60 and symbol in self.current_universe:
                if symbol not in self.held_symbols and position_count < self.max_positions:
                    self.set_holdings(symbol, self.weight_per_stock)
                    self.held_symbols.add(symbol)
                    position_count += 1

            elif bearish_cross and symbol in self.held_symbols:
                self.liquidate(symbol)
                self.held_symbols.discard(symbol)
                position_count -= 1

            self.prev_ema[symbol] = {'fast': ema_fast, 'slow': ema_slow}
