from AlgorithmImports import *
import numpy as np

class EMADynamicAnnualV52(QCAlgorithm):
    """
    V52: FULL REGIME-ADAPTIVE META STRATEGY

    Changes EVERYTHING based on regime:
    - Universe selection criteria
    - Volatility filters
    - Quality requirements
    - Position sizing
    - Risk management

    REGIMES:
    1. EUPHORIA: SPY trending strongly up, making new highs
       -> Speculative high-vol momentum (V30 style)

    2. BULL: SPY in uptrend (above 200 SMA, golden cross)
       -> Quality growth momentum

    3. NEUTRAL: SPY above 200 SMA but no golden cross
       -> Low-vol quality, reduced exposure

    4. BEAR: SPY below 200 SMA
       -> Cash
    """

    def initialize(self):
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100000)

        # SPY for regime detection
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.spy_sma20 = self.sma(self.spy, 20, Resolution.DAILY)
        self.spy_sma50 = self.sma(self.spy, 50, Resolution.DAILY)
        self.spy_sma200 = self.sma(self.spy, 200, Resolution.DAILY)
        self.spy_high_252 = self.max(self.spy, 252, Resolution.DAILY)

        # Current regime
        self.current_regime = "NEUTRAL"
        self.last_regime = "NEUTRAL"

        # Regime-dependent parameters (defaults for NEUTRAL)
        self.vol_percentile = 50
        self.require_profitable = True
        self.min_market_cap = 10e9
        self.max_positions = 4
        self.weight_per_stock = 0.12
        self.trailing_stop_pct = 0.20
        self.ema_fast = 20
        self.ema_slow = 100

        # Universe settings
        self.universe_size = 30
        self.min_price = 10.0
        self.min_dollar_volume = 10_000_000
        self.momentum_lookback = 126
        self.short_momentum_lookback = 63

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
        self.set_warm_up(260, Resolution.DAILY)

        # Schedule regime detection
        self.schedule.on(
            self.date_rules.every_day(self.spy),
            self.time_rules.after_market_open(self.spy, 30),
            self.detect_regime
        )

    def detect_regime(self):
        """Detect market regime and update strategy parameters"""
        if not all([self.spy_sma20.is_ready, self.spy_sma50.is_ready,
                    self.spy_sma200.is_ready, self.spy_high_252.is_ready]):
            return

        spy_price = self.securities[self.spy].price
        sma20 = self.spy_sma20.current.value
        sma50 = self.spy_sma50.current.value
        sma200 = self.spy_sma200.current.value
        high_252 = self.spy_high_252.current.value

        self.last_regime = self.current_regime

        # Regime detection logic
        near_high = spy_price > high_252 * 0.97  # Within 3% of 52-week high
        golden_cross = sma50 > sma200
        above_200 = spy_price > sma200
        strong_trend = sma20 > sma50 > sma200

        if above_200 and strong_trend and near_high:
            self.current_regime = "EUPHORIA"
            self.set_euphoria_params()
        elif above_200 and golden_cross:
            self.current_regime = "BULL"
            self.set_bull_params()
        elif above_200:
            self.current_regime = "NEUTRAL"
            self.set_neutral_params()
        else:
            self.current_regime = "BEAR"
            self.set_bear_params()

        if self.current_regime != self.last_regime:
            self.debug(f"REGIME: {self.last_regime} -> {self.current_regime} | SPY={spy_price:.2f}")

            # Force universe refresh on regime change
            self.last_refresh_key = None

            # If entering BEAR, liquidate all
            if self.current_regime == "BEAR":
                for symbol in list(self.held_symbols):
                    self.liquidate(symbol, f"Regime -> BEAR")
                    self.highest_prices.pop(symbol, None)
                self.held_symbols.clear()

    def set_euphoria_params(self):
        """EUPHORIA: Speculative high-vol momentum"""
        self.vol_percentile = 90          # Top 10% volatility
        self.require_profitable = False   # Don't care about profits
        self.min_market_cap = 1e9         # Smaller caps OK
        self.max_positions = 5
        self.weight_per_stock = 0.22      # 110% exposure
        self.trailing_stop_pct = 0.30     # Wide stop

    def set_bull_params(self):
        """BULL: Quality growth momentum"""
        self.vol_percentile = 70          # Top 30% volatility
        self.require_profitable = True    # Must be profitable
        self.min_market_cap = 5e9         # Mid-cap+
        self.max_positions = 5
        self.weight_per_stock = 0.18      # 90% exposure
        self.trailing_stop_pct = 0.25

    def set_neutral_params(self):
        """NEUTRAL: Low-vol quality"""
        self.vol_percentile = 50          # Top 50% (avoid extremes)
        self.require_profitable = True
        self.min_market_cap = 10e9        # Large cap only
        self.max_positions = 4
        self.weight_per_stock = 0.12      # 48% exposure
        self.trailing_stop_pct = 0.20

    def set_bear_params(self):
        """BEAR: Cash"""
        self.max_positions = 0
        self.weight_per_stock = 0

    def get_half_year_key(self):
        year = self.time.year
        half = 1 if self.time.month <= 6 else 2
        return f"{year}H{half}_{self.current_regime}"  # Include regime in key

    def coarse_filter(self, coarse):
        # In BEAR, return empty (will hold cash)
        if self.current_regime == "BEAR":
            return list(self.held_symbols)

        current_key = self.get_half_year_key()
        refresh_months = [1, 7]

        if self.last_refresh_key == current_key:
            return list(set(self.universe_symbols) | self.held_symbols)
        if self.time.month not in refresh_months and self.last_refresh_key is not None:
            # But allow refresh on regime change
            if self.current_regime == self.last_regime:
                return list(set(self.universe_symbols) | self.held_symbols)

        filtered = [x for x in coarse
                   if x.has_fundamental_data
                   and x.price > self.min_price
                   and x.dollar_volume > self.min_dollar_volume]

        sorted_by_volume = sorted(filtered, key=lambda x: x.dollar_volume, reverse=True)
        return [x.symbol for x in sorted_by_volume[:500]]

    def fine_filter(self, fine):
        if self.current_regime == "BEAR":
            return list(self.held_symbols)

        current_key = self.get_half_year_key()
        refresh_months = [1, 7]

        if self.last_refresh_key == current_key:
            return list(set(self.universe_symbols) | self.held_symbols)
        if self.time.month not in refresh_months and self.last_refresh_key is not None:
            if self.current_regime == self.last_regime:
                return list(set(self.universe_symbols) | self.held_symbols)

        # Sector exclusions vary by regime
        if self.current_regime == "EUPHORIA":
            excluded_sectors = [103, 104, 207]  # Financials, RE, Utilities
        elif self.current_regime == "BULL":
            excluded_sectors = [103, 104, 207]  # Financials, RE, Utilities
        else:  # NEUTRAL - allow all sectors
            excluded_sectors = []

        # Apply filters
        filtered = []
        for x in fine:
            # Sector filter
            if x.asset_classification.morningstar_sector_code in excluded_sectors:
                continue

            # Market cap filter
            if x.market_cap and x.market_cap < self.min_market_cap:
                continue

            # Profitability filter (if required)
            if self.require_profitable:
                if not x.earning_reports.basic_eps.three_months:
                    continue
                if x.earning_reports.basic_eps.three_months <= 0:
                    continue

            filtered.append(x)

        # Calculate momentum and volatility
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

                        # Momentum requirement varies by regime
                        if self.current_regime == "EUPHORIA":
                            if momentum_6m > 0 and momentum_3m > 0:
                                stock_metrics.append((symbol, momentum_6m, vol))
                        elif self.current_regime == "BULL":
                            if momentum_6m > 0:  # Only need 6m positive
                                stock_metrics.append((symbol, momentum_6m, vol))
                        else:  # NEUTRAL
                            if momentum_3m > 0:  # Only need 3m positive
                                stock_metrics.append((symbol, momentum_6m, vol))
            except:
                pass

        if not stock_metrics:
            return list(self.held_symbols)

        # Apply volatility filter based on regime
        vols = [x[2] for x in stock_metrics]
        if len(vols) >= 10:
            vol_threshold = np.percentile(vols, self.vol_percentile)
            if self.current_regime == "NEUTRAL":
                # In NEUTRAL, we want LOWER volatility (below threshold)
                selected = [x for x in stock_metrics if x[2] <= vol_threshold]
            else:
                # In EUPHORIA/BULL, we want HIGHER volatility (above threshold)
                selected = [x for x in stock_metrics if x[2] >= vol_threshold]
        else:
            selected = stock_metrics

        if not selected:
            selected = stock_metrics

        # Sort by momentum and take top N
        selected.sort(key=lambda x: x[1], reverse=True)
        top_stocks = [x[0] for x in selected[:self.universe_size]]

        self.momentum_scores = {x[0]: x[1] for x in selected[:self.universe_size]}
        self.universe_symbols = top_stocks
        self.last_refresh_key = current_key

        self.debug(f"Universe refresh [{self.current_regime}]: {len(top_stocks)} stocks")

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

        # No trading in BEAR
        if self.current_regime == "BEAR":
            return

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
