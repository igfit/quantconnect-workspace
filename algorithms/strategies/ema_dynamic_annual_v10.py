from AlgorithmImports import *
import numpy as np

class EMADynamicAnnualV10(QCAlgorithm):
    """
    EMA Crossover with Dynamic Universe - V10 DRAWDOWN CONTROL

    Same as V5 (no leverage) but with portfolio drawdown control:
    - Track portfolio high water mark
    - When DD > 15%, reduce to 50% exposure
    - When DD > 25%, go to 100% cash
    - Re-enter when DD recovers to < 10%

    Target: 25%+ CAGR with <35% DD
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100000)

        # Universe settings
        self.universe_size = 50
        self.min_price = 10.0
        self.min_dollar_volume = 10_000_000
        self.momentum_lookback = 126
        self.volatility_lookback = 60

        # Position sizing (no leverage)
        self.max_positions = 5
        self.weight_per_stock = 0.20

        # EMAs
        self.ema_fast = 20
        self.ema_slow = 100

        # Drawdown control
        self.high_water_mark = 100000
        self.dd_reduce_threshold = 0.15  # Reduce at 15% DD
        self.dd_exit_threshold = 0.25    # Exit all at 25% DD
        self.dd_reentry_threshold = 0.10 # Re-enter when DD < 10%
        self.in_drawdown_mode = False

        # Tracking
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
        self.set_warm_up(120, Resolution.DAILY)

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
        return [x.symbol for x in sorted_by_volume[:400]]

    def fine_filter(self, fine):
        current_year = self.time.year
        current_month = self.time.month

        if self.last_refresh_year == current_year:
            return list(set(self.universe_symbols) | self.held_symbols)

        if current_month != 1 and self.last_refresh_year != -1:
            return list(set(self.universe_symbols) | self.held_symbols)

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

        vols = [x[2] for x in stock_metrics]
        median_vol = np.median(vols)

        volatile_momentum = [x for x in stock_metrics if x[2] >= median_vol]
        volatile_momentum.sort(key=lambda x: x[1], reverse=True)
        top_stocks = [x[0] for x in volatile_momentum[:self.universe_size]]

        self.momentum_scores = {x[0]: x[1] for x in volatile_momentum[:self.universe_size]}
        self.universe_symbols = top_stocks
        self.last_refresh_year = current_year

        self.debug(f"Universe: {len(top_stocks)} stocks for {current_year}")

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
                }
                self.prev_ema[symbol] = {'fast': None, 'slow': None}

    def on_data(self, data):
        if self.is_warming_up:
            return

        # Update high water mark
        current_equity = self.portfolio.total_portfolio_value
        if current_equity > self.high_water_mark:
            self.high_water_mark = current_equity

        # Calculate current drawdown
        current_dd = (self.high_water_mark - current_equity) / self.high_water_mark

        # Drawdown control logic
        if current_dd >= self.dd_exit_threshold:
            # Severe drawdown - exit all
            if self.held_symbols:
                self.debug(f"DD CONTROL: {current_dd:.1%} DD - Exiting all positions")
                for symbol in list(self.held_symbols):
                    self.liquidate(symbol, "DD Exit")
                self.held_symbols.clear()
            self.in_drawdown_mode = True
            return

        if current_dd >= self.dd_reduce_threshold:
            # Moderate drawdown - reduce exposure
            if not self.in_drawdown_mode:
                self.debug(f"DD CONTROL: {current_dd:.1%} DD - Reducing exposure")
                # Liquidate half of positions (keep best momentum)
                if len(self.held_symbols) > 2:
                    held_with_scores = [(s, self.momentum_scores.get(s, 0)) for s in self.held_symbols]
                    held_with_scores.sort(key=lambda x: x[1], reverse=True)
                    to_keep = len(self.held_symbols) // 2
                    to_sell = [s for s, _ in held_with_scores[to_keep:]]
                    for symbol in to_sell:
                        self.liquidate(symbol, "DD Reduce")
                        self.held_symbols.discard(symbol)
            self.in_drawdown_mode = True
            return

        # Check for recovery
        if self.in_drawdown_mode and current_dd < self.dd_reentry_threshold:
            self.debug(f"DD CONTROL: {current_dd:.1%} DD - Recovery, resuming trading")
            self.in_drawdown_mode = False

        # Don't enter new positions while in drawdown mode
        if self.in_drawdown_mode:
            return

        # Normal trading logic
        position_count = len(self.held_symbols)
        symbols_to_check = self.current_universe | self.held_symbols

        entry_candidates = []

        for symbol in list(symbols_to_check):
            if symbol not in data.bars:
                continue
            if symbol not in self.indicators:
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

            # Exit
            if bearish_cross and symbol in self.held_symbols:
                self.liquidate(symbol)
                self.held_symbols.discard(symbol)
                position_count -= 1

            # Entry candidates
            elif bullish_cross and symbol in self.current_universe:
                if symbol not in self.held_symbols:
                    mom_score = self.momentum_scores.get(symbol, 0)
                    entry_candidates.append((symbol, mom_score))

            self.prev_ema[symbol] = {'fast': ema_fast, 'slow': ema_slow}

        # Enter highest momentum candidates
        if entry_candidates and position_count < self.max_positions:
            entry_candidates.sort(key=lambda x: x[1], reverse=True)
            for symbol, mom in entry_candidates:
                if position_count >= self.max_positions:
                    break
                self.set_holdings(symbol, self.weight_per_stock)
                self.held_symbols.add(symbol)
                position_count += 1
