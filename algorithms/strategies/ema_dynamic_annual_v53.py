from AlgorithmImports import *
import numpy as np

class EMADynamicAnnualV53(QCAlgorithm):
    """
    V53: PRACTICAL REGIME STRATEGY

    V52 over-filtered with 4 regimes and restrictive criteria.
    V53 simplifies: 2 regimes with faster detection.

    REGIME DETECTION (faster indicator):
    - BULL: SPY > 100 SMA (faster than 200 SMA, catches rallies earlier)
    - BEAR: SPY < 100 SMA → Cash

    STRATEGY IN BULL:
    - Run V30's aggressive approach (top 10% volatility, high momentum)
    - BUT add VIX overlay: if VIX > 25, reduce exposure to 50%

    The goal: Capture V30's bubble returns while avoiding major drawdowns.
    """

    def initialize(self):
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100000)

        # SPY for regime detection - use 100 SMA (faster than 200)
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.spy_sma100 = self.sma(self.spy, 100, Resolution.DAILY)

        # VIX for volatility overlay
        self.vix = self.add_data(CBOE, "VIX", Resolution.DAILY).symbol

        self.is_bull_regime = True
        self.high_vol_env = False  # VIX > 25

        # V30-style parameters (aggressive)
        self.universe_size = 30
        self.min_price = 10.0
        self.min_dollar_volume = 10_000_000
        self.momentum_lookback = 126
        self.short_momentum_lookback = 63

        # Position sizing (regime-dependent)
        self.base_max_positions = 5
        self.base_weight = 0.20
        self.max_positions = 5
        self.weight_per_stock = 0.20

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

        # V30-style filtering: exclude financials, RE, utilities
        filtered = [x for x in fine
                   if x.asset_classification.morningstar_sector_code not in [103, 104, 207]]

        stock_metrics = []
        for symbol in [x.symbol for x in filtered]:
            try:
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

                        # V30 requires both 6m and 3m positive momentum
                        if momentum_6m > 0 and momentum_3m > 0:
                            stock_metrics.append((symbol, momentum_6m, vol))
            except:
                pass

        if not stock_metrics:
            return list(self.held_symbols)

        # V30-style: top 10% volatility
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

        return list(set(top_stocks) | self.held_symbols)

    def on_securities_changed(self, changes):
        for security in changes.removed_securities:
            symbol = security.symbol
            if symbol not in self.held_symbols and symbol not in [self.spy, self.vix]:
                self.indicators.pop(symbol, None)
                self.prev_ema.pop(symbol, None)
            self.current_universe.discard(symbol)

        for security in changes.added_securities:
            symbol = security.symbol
            if symbol in [self.spy, self.vix]:
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

        if not self.spy_sma100.is_ready:
            return

        # Regime detection: SPY > 100 SMA
        spy_price = self.securities[self.spy].price
        sma100 = self.spy_sma100.current.value
        was_bull = self.is_bull_regime
        self.is_bull_regime = spy_price > sma100

        # VIX overlay for position sizing
        try:
            vix_value = self.securities[self.vix].price if self.vix in data else 20
            self.high_vol_env = vix_value > 25
        except:
            self.high_vol_env = False

        # Adjust position sizing based on VIX
        if self.high_vol_env:
            self.max_positions = 3  # Reduce positions in high VIX
            self.weight_per_stock = 0.15
        else:
            self.max_positions = self.base_max_positions
            self.weight_per_stock = self.base_weight

        # If regime changed to BEAR, exit all positions
        if was_bull and not self.is_bull_regime:
            self.debug(f"REGIME -> BEAR: SPY={spy_price:.2f} < SMA100={sma100:.2f}")
            for symbol in list(self.held_symbols):
                self.liquidate(symbol, "Regime -> BEAR")
                self.highest_prices.pop(symbol, None)
            self.held_symbols.clear()
            return

        # In BEAR regime, do nothing
        if not self.is_bull_regime:
            return

        position_count = len(self.held_symbols)
        entry_candidates = []

        for symbol in list(self.current_universe | self.held_symbols):
            if symbol in [self.spy, self.vix]:
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
