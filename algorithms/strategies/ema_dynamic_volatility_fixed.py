from AlgorithmImports import *
import numpy as np

class EMADynamicVolatilityFixed(QCAlgorithm):
    """
    EMA Crossover with Dynamic Volatility Universe - FIXED VERSION

    BUG FIX: Don't liquidate when removed from universe.
    Keep positions open until EMA exit signal triggers.

    Universe: Top 50 by 60-day volatility, refreshed monthly
    Signal: EMA(10) crosses above EMA(50) AND RSI < 70
    Exit: EMA(10) crosses below EMA(50) ONLY
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100000)

        # Universe settings
        self.universe_size = 50
        self.min_price = 5.0
        self.min_dollar_volume = 10_000_000
        self.volatility_lookback = 60

        # Position settings
        self.max_positions = 8
        self.weight_per_stock = 0.125

        # Track indicators and positions
        self.indicators = {}
        self.prev_ema = {}
        self.in_position = {}
        self.current_universe = set()
        self.held_symbols = set()

        self.add_universe(self.coarse_filter, self.fine_filter)
        self.universe_settings.resolution = Resolution.DAILY

        self.set_benchmark("SPY")
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)
        self.set_warm_up(60, Resolution.DAILY)

    def coarse_filter(self, coarse):
        filtered = [x for x in coarse
                   if x.has_fundamental_data
                   and x.price > self.min_price
                   and x.dollar_volume > self.min_dollar_volume]

        sorted_by_volume = sorted(filtered, key=lambda x: x.dollar_volume, reverse=True)
        return [x.symbol for x in sorted_by_volume[:200]]

    def fine_filter(self, fine):
        filtered = [x for x in fine
                   if x.asset_classification.morningstar_sector_code not in [103, 104]]

        symbols = [x.symbol for x in filtered]

        volatility_scores = []
        for symbol in symbols:
            history = self.history(symbol, self.volatility_lookback, Resolution.DAILY)
            if len(history) >= self.volatility_lookback * 0.8:
                returns = history['close'].pct_change().dropna()
                if len(returns) > 0:
                    vol = returns.std() * np.sqrt(252)
                    volatility_scores.append((symbol, vol))

        volatility_scores.sort(key=lambda x: x[1], reverse=True)
        top_volatile = [x[0] for x in volatility_scores[:self.universe_size]]

        # Include held symbols to allow exits
        held_not_in_top = [s for s in self.held_symbols if s not in top_volatile]
        result = top_volatile + held_not_in_top

        if volatility_scores:
            self.debug(f"Universe: {len(top_volatile)} volatile + {len(held_not_in_top)} held")

        return result

    def on_securities_changed(self, changes):
        for security in changes.removed_securities:
            symbol = security.symbol
            if symbol not in self.held_symbols:
                if symbol in self.indicators:
                    del self.indicators[symbol]
                if symbol in self.prev_ema:
                    del self.prev_ema[symbol]
                if symbol in self.in_position:
                    del self.in_position[symbol]
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
                self.in_position[symbol] = False

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

            if bullish_cross and rsi < 70 and symbol in self.current_universe:
                if symbol not in self.held_symbols and position_count < self.max_positions:
                    self.set_holdings(symbol, self.weight_per_stock)
                    self.held_symbols.add(symbol)
                    self.in_position[symbol] = True
                    position_count += 1

            elif bearish_cross and symbol in self.held_symbols:
                self.liquidate(symbol)
                self.held_symbols.discard(symbol)
                self.in_position[symbol] = False
                position_count -= 1
                if symbol not in self.current_universe:
                    if symbol in self.indicators:
                        del self.indicators[symbol]
                    if symbol in self.prev_ema:
                        del self.prev_ema[symbol]

            self.prev_ema[symbol] = {'ema10': ema10, 'ema50': ema50}
