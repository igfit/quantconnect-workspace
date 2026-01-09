from AlgorithmImports import *
import numpy as np

class EMADynamicAnnualV57(QCAlgorithm):
    """
    V57: SECTOR ROTATION REGIME STRATEGY

    Key insight: Going to CASH in bear markets causes us to miss recoveries.
    Instead: ROTATE into DEFENSIVE sectors during bear markets.

    REGIMES:
    - BULL (SPY > 200 SMA): Growth sectors (Tech, Consumer Discretionary, Communication)
    - BEAR (SPY < 200 SMA): Defensive sectors (Healthcare, Consumer Staples, Utilities)

    This keeps us invested but in sectors that historically do better in each regime.

    UNIVERSE:
    - Bull: Exclude defensive sectors, include growth
    - Bear: Include only defensive sectors

    Both use momentum + EMA signals, just different sector universes.
    """

    def initialize(self):
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100000)

        # SPY for regime
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.spy_sma200 = self.sma(self.spy, 200, Resolution.DAILY)

        self.is_bull_regime = True

        # Sector codes (Morningstar)
        # Growth: 311 (Tech), 102 (Consumer Cyclical), 308 (Communication)
        # Defensive: 206 (Healthcare), 205 (Consumer Defensive), 207 (Utilities)
        self.growth_sectors = [311, 102, 308]
        self.defensive_sectors = [206, 205, 207]

        # Universe settings
        self.universe_size = 25
        self.min_price = 10.0
        self.min_dollar_volume = 10_000_000
        self.momentum_lookback = 126
        self.short_momentum_lookback = 63

        # Position sizing
        self.max_positions = 5
        self.weight_per_stock = 0.20

        self.ema_fast = 20
        self.ema_slow = 100
        self.trailing_stop_pct = 0.22

        self.indicators = {}
        self.prev_ema = {}
        self.current_universe = set()
        self.held_symbols = set()
        self.momentum_scores = {}
        self.last_refresh_key = None
        self.universe_symbols = []
        self.highest_prices = {}
        self.last_regime_for_refresh = None

        self.add_universe(self.coarse_filter, self.fine_filter)
        self.universe_settings.resolution = Resolution.DAILY
        self.universe_settings.minimum_time_in_universe = timedelta(days=30)

        self.set_benchmark("SPY")
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)
        self.set_warm_up(220, Resolution.DAILY)

    def get_half_year_key(self):
        year = self.time.year
        half = 1 if self.time.month <= 6 else 2
        regime_str = "bull" if self.is_bull_regime else "bear"
        return f"{year}H{half}_{regime_str}"

    def coarse_filter(self, coarse):
        current_key = self.get_half_year_key()
        refresh_months = [1, 7]

        # Force refresh on regime change
        regime_changed = self.last_regime_for_refresh != self.is_bull_regime

        if self.last_refresh_key == current_key and not regime_changed:
            return list(set(self.universe_symbols) | self.held_symbols)
        if self.time.month not in refresh_months and self.last_refresh_key is not None and not regime_changed:
            return list(set(self.universe_symbols) | self.held_symbols)

        filtered = [x for x in coarse
                   if x.has_fundamental_data
                   and x.price > self.min_price
                   and x.dollar_volume > self.min_dollar_volume]

        sorted_by_volume = sorted(filtered, key=lambda x: x.dollar_volume, reverse=True)
        return [x.symbol for x in sorted_by_volume[:500]]

    def fine_filter(self, fine):
        current_key = self.get_half_year_key()
        refresh_months = [1, 7]

        regime_changed = self.last_regime_for_refresh != self.is_bull_regime

        if self.last_refresh_key == current_key and not regime_changed:
            return list(set(self.universe_symbols) | self.held_symbols)
        if self.time.month not in refresh_months and self.last_refresh_key is not None and not regime_changed:
            return list(set(self.universe_symbols) | self.held_symbols)

        # Select sectors based on regime
        if self.is_bull_regime:
            allowed_sectors = self.growth_sectors
            self.debug("BULL: Selecting growth sectors (Tech, Consumer Disc, Communication)")
        else:
            allowed_sectors = self.defensive_sectors
            self.debug("BEAR: Selecting defensive sectors (Healthcare, Staples, Utilities)")

        # Filter by allowed sectors
        filtered = [x for x in fine
                   if x.asset_classification.morningstar_sector_code in allowed_sectors]

        stock_metrics = []
        for x in filtered:
            symbol = x.symbol
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

                        # In BULL, require both positive; in BEAR, just require 3m positive
                        if self.is_bull_regime:
                            if momentum_6m > 0 and momentum_3m > 0:
                                stock_metrics.append((symbol, momentum_6m, vol))
                        else:
                            # In bear market, we want stocks that are holding up
                            if momentum_3m > -0.10:  # Not dropping more than 10%
                                stock_metrics.append((symbol, momentum_6m, vol))
            except:
                pass

        if not stock_metrics:
            return list(self.held_symbols)

        # Volatility filter based on regime
        vols = [x[2] for x in stock_metrics]
        if len(vols) >= 10:
            if self.is_bull_regime:
                # Bull: prefer higher vol
                vol_threshold = np.percentile(vols, 70)
                selected = [x for x in stock_metrics if x[2] >= vol_threshold]
            else:
                # Bear: prefer lower vol
                vol_threshold = np.percentile(vols, 50)
                selected = [x for x in stock_metrics if x[2] <= vol_threshold]
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
        self.last_regime_for_refresh = self.is_bull_regime

        return list(set(top_stocks) | self.held_symbols)

    def on_securities_changed(self, changes):
        for security in changes.removed_securities:
            symbol = security.symbol
            if symbol not in self.held_symbols and symbol != self.spy:
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

        # Regime detection
        spy_price = self.securities[self.spy].price
        sma200 = self.spy_sma200.current.value
        was_bull = self.is_bull_regime
        self.is_bull_regime = spy_price > sma200

        # If regime changed, log it but DON'T liquidate
        # Instead, let positions exit naturally via EMA/stop
        # New positions will be from the new universe
        if was_bull != self.is_bull_regime:
            regime_str = "BULL" if self.is_bull_regime else "BEAR"
            self.debug(f"REGIME -> {regime_str}: SPY={spy_price:.2f} vs SMA200={sma200:.2f}")
            # Force universe refresh on next coarse filter
            self.last_refresh_key = None

        position_count = len(self.held_symbols)
        entry_candidates = []

        for symbol in list(self.current_universe | self.held_symbols):
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
