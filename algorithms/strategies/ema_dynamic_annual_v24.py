from AlgorithmImports import *
import numpy as np

class EMADynamicAnnualV24(QCAlgorithm):
    """
    V24: MAX CONCENTRATION - NO DD CONTROL

    Same as V23 but with maximum concentration:
    - 4 positions at 25% (1x leverage, max concentration)
    - Top 15 highest momentum stocks with top quartile volatility
    - 15/60 EMAs
    - Short-term momentum filter > 15%

    Target: 30%+ CAGR (accepting higher DD for higher returns)
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100000)

        self.universe_size = 15  # Very concentrated
        self.min_price = 15.0
        self.min_dollar_volume = 15_000_000
        self.momentum_lookback = 126
        self.short_momentum_lookback = 21

        # MAX CONCENTRATION
        self.max_positions = 4
        self.weight_per_stock = 0.25

        self.ema_fast = 15
        self.ema_slow = 60

        self.indicators = {}
        self.prev_ema = {}
        self.current_universe = set()
        self.held_symbols = set()
        self.momentum_scores = {}
        self.last_refresh_year = -1
        self.universe_symbols = []

        self.add_universe(self.coarse_filter, self.fine_filter)
        self.universe_settings.resolution = Resolution.DAILY
        self.universe_settings.minimum_time_in_universe = timedelta(days=30)

        self.set_benchmark("SPY")
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)
        self.set_warm_up(70, Resolution.DAILY)

    def coarse_filter(self, coarse):
        current_year = self.time.year
        current_month = self.time.month

        if self.last_refresh_year == current_year:
            return list(set(self.universe_symbols) | self.held_symbols)
        if current_month != 1 and self.last_refresh_year != -1:
            return list(set(self.universe_symbols) | self.held_symbols)

        filtered = [x for x in coarse
                   if x.has_fundamental_data
                   and x.price > self.min_price
                   and x.dollar_volume > self.min_dollar_volume]

        sorted_by_volume = sorted(filtered, key=lambda x: x.dollar_volume, reverse=True)
        return [x.symbol for x in sorted_by_volume[:400]]

    def fine_filter(self, fine):
        current_year = self.time.year
        current_month = self.time.month

        if self.last_refresh_year == current_year:
            return list(set(self.universe_symbols) | self.held_symbols)
        if current_month != 1 and self.last_refresh_year != -1:
            return list(set(self.universe_symbols) | self.held_symbols)

        # Exclude defensive sectors
        filtered = [x for x in fine
                   if x.asset_classification.morningstar_sector_code not in [103, 104, 207, 205, 206]]

        stock_metrics = []
        for symbol in [x.symbol for x in filtered]:
            try:
                history = self.history(symbol, self.momentum_lookback + 10, Resolution.DAILY)
                if len(history) >= self.momentum_lookback:
                    start_price = history['close'].iloc[-self.momentum_lookback]
                    end_price = history['close'].iloc[-1]

                    start_price_1m = history['close'].iloc[-self.short_momentum_lookback]
                    short_mom = (end_price - start_price_1m) / start_price_1m

                    if start_price > 0:
                        momentum = (end_price - start_price) / start_price
                        returns = history['close'].pct_change().dropna()
                        vol = returns.std() * np.sqrt(252)

                        # Stricter filter: short-term momentum > 15%
                        if momentum > 0 and short_mom > 0.15:
                            stock_metrics.append((symbol, momentum, vol))
            except:
                pass

        if not stock_metrics:
            return list(self.held_symbols)

        # Top quartile volatility
        vols = [x[2] for x in stock_metrics]
        if len(vols) >= 4:
            vol_75th = np.percentile(vols, 75)
            high_vol = [x for x in stock_metrics if x[2] >= vol_75th]
        else:
            high_vol = stock_metrics

        high_vol.sort(key=lambda x: x[1], reverse=True)
        top_stocks = [x[0] for x in high_vol[:self.universe_size]]

        self.momentum_scores = {x[0]: x[1] for x in high_vol[:self.universe_size]}
        self.universe_symbols = top_stocks
        self.last_refresh_year = current_year

        self.debug(f"V24 Universe: {len(top_stocks)} top momentum stocks")
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

            if bearish_cross and symbol in self.held_symbols:
                self.liquidate(symbol, "EMA Exit")
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
