from AlgorithmImports import *
import numpy as np

class EMADynamicMomentumAnnual(QCAlgorithm):
    """
    EMA Crossover with Dynamic Momentum Universe - ANNUAL REFRESH

    Universe: Top 50 by 6-month momentum, refreshed ONCE PER YEAR (January)
    Signal: EMA(10) crosses above EMA(50) AND RSI < 70
    Exit: EMA(10) crosses below EMA(50)
    Position sizing: 8 positions at 12.5% each
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100000)

        # Universe settings
        self.universe_size = 50
        self.min_price = 10.0
        self.min_dollar_volume = 10_000_000
        self.momentum_lookback = 126  # 6 months

        # Position settings
        self.max_positions = 8
        self.weight_per_stock = 0.125

        # Track indicators and positions
        self.indicators = {}
        self.prev_ema = {}
        self.current_universe = set()
        self.held_symbols = set()

        # Annual refresh tracking
        self.last_refresh_year = -1
        self.universe_symbols = []

        # Manual universe - we'll populate it annually
        self.add_universe(self.coarse_filter, self.fine_filter)

        # Set universe to refresh less frequently
        self.universe_settings.resolution = Resolution.DAILY
        self.universe_settings.minimum_time_in_universe = timedelta(days=30)

        self.set_benchmark("SPY")
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)
        self.set_warm_up(60, Resolution.DAILY)

    def coarse_filter(self, coarse):
        """First pass: liquidity and price filters"""
        # Only refresh in January or if never refreshed
        current_year = self.time.year
        current_month = self.time.month

        if self.last_refresh_year == current_year:
            # Return existing universe + held symbols
            return list(set(self.universe_symbols) | self.held_symbols)

        if current_month != 1 and self.last_refresh_year != -1:
            # Not January and we have a universe - keep it
            return list(set(self.universe_symbols) | self.held_symbols)

        # January or first run - do full refresh
        self.debug(f"ANNUAL REFRESH: Year {current_year}")

        filtered = [x for x in coarse
                   if x.has_fundamental_data
                   and x.price > self.min_price
                   and x.dollar_volume > self.min_dollar_volume]

        sorted_by_volume = sorted(filtered, key=lambda x: x.dollar_volume, reverse=True)
        return [x.symbol for x in sorted_by_volume[:300]]

    def fine_filter(self, fine):
        """Second pass: calculate momentum and select top N"""
        current_year = self.time.year
        current_month = self.time.month

        # Only do momentum calculation in January
        if self.last_refresh_year == current_year:
            return list(set(self.universe_symbols) | self.held_symbols)

        if current_month != 1 and self.last_refresh_year != -1:
            return list(set(self.universe_symbols) | self.held_symbols)

        # Filter sectors
        filtered = [x for x in fine
                   if x.asset_classification.morningstar_sector_code not in [103, 104, 207]]

        symbols = [x.symbol for x in filtered]

        # Calculate momentum
        momentum_scores = []
        for symbol in symbols:
            history = self.history(symbol, self.momentum_lookback, Resolution.DAILY)
            if len(history) >= self.momentum_lookback * 0.8:
                try:
                    start_price = history['close'].iloc[0]
                    end_price = history['close'].iloc[-1]
                    if start_price > 0:
                        momentum = (end_price - start_price) / start_price
                        if momentum > 0:
                            momentum_scores.append((symbol, momentum))
                except:
                    pass

        momentum_scores.sort(key=lambda x: x[1], reverse=True)
        top_momentum = [x[0] for x in momentum_scores[:self.universe_size]]

        # Store universe and mark refresh
        self.universe_symbols = top_momentum
        self.last_refresh_year = current_year

        self.debug(f"Universe refreshed: {len(top_momentum)} stocks for {current_year}")
        if momentum_scores:
            self.debug(f"Top momentum: {momentum_scores[0][0].value} at {momentum_scores[0][1]:.1%}")

        # Include held symbols for exits
        result = list(set(top_momentum) | self.held_symbols)
        return result

    def on_securities_changed(self, changes):
        """Handle universe changes - don't liquidate on removal"""
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
                    'ema10': self.ema(symbol, 10, Resolution.DAILY),
                    'ema50': self.ema(symbol, 50, Resolution.DAILY),
                    'rsi': self.rsi(symbol, 14, MovingAverageType.SIMPLE, Resolution.DAILY)
                }
                self.prev_ema[symbol] = {'ema10': None, 'ema50': None}

    def on_data(self, data):
        """Apply EMA crossover signal"""
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
            if not ind['ema10'].is_ready or not ind['ema50'].is_ready or not ind['rsi'].is_ready:
                continue

            ema10 = ind['ema10'].current.value
            ema50 = ind['ema50'].current.value
            rsi = ind['rsi'].current.value

            prev = self.prev_ema.get(symbol, {'ema10': None, 'ema50': None})
            if prev['ema10'] is None:
                self.prev_ema[symbol] = {'ema10': ema10, 'ema50': ema50}
                continue

            bullish_cross = prev['ema10'] <= prev['ema50'] and ema10 > ema50
            bearish_cross = prev['ema10'] >= prev['ema50'] and ema10 < ema50

            # Entry: only for stocks in current universe
            if bullish_cross and rsi < 70 and symbol in self.current_universe:
                if symbol not in self.held_symbols and position_count < self.max_positions:
                    self.set_holdings(symbol, self.weight_per_stock)
                    self.held_symbols.add(symbol)
                    position_count += 1

            # Exit: for any held position
            elif bearish_cross and symbol in self.held_symbols:
                self.liquidate(symbol)
                self.held_symbols.discard(symbol)
                position_count -= 1

            self.prev_ema[symbol] = {'ema10': ema10, 'ema50': ema50}
