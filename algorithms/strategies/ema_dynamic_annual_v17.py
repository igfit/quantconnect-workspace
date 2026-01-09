from AlgorithmImports import *
import numpy as np

class EMADynamicAnnualV17(QCAlgorithm):
    """
    EMA Crossover with Dynamic Universe - V17 PROFIT TAKE + DIVERSIFICATION

    Combines V12's profit taking with more positions:
    - 8 positions at 12.5% each = 100% exposure
    - Take 50% profit at 40% gain
    - 15% trailing stop after profit take

    Target: 20%+ CAGR with <35% DD
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100000)

        self.universe_size = 50
        self.min_price = 10.0
        self.min_dollar_volume = 10_000_000
        self.momentum_lookback = 126
        self.volatility_lookback = 60

        # More diversification
        self.max_positions = 8
        self.weight_per_stock = 0.125

        self.ema_fast = 20
        self.ema_slow = 100

        # Profit taking
        self.profit_take_threshold = 0.40
        self.profit_take_amount = 0.50
        self.trailing_stop_pct = 0.15

        self.indicators = {}
        self.prev_ema = {}
        self.current_universe = set()
        self.held_symbols = set()
        self.momentum_scores = {}
        self.last_refresh_year = -1
        self.universe_symbols = []

        self.entry_prices = {}
        self.highest_prices = {}
        self.profit_taken = {}

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

        stock_metrics = []
        for symbol in [x.symbol for x in filtered]:
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

        median_vol = np.median([x[2] for x in stock_metrics])
        volatile_momentum = sorted([x for x in stock_metrics if x[2] >= median_vol], key=lambda x: x[1], reverse=True)
        top_stocks = [x[0] for x in volatile_momentum[:self.universe_size]]

        self.momentum_scores = {x[0]: x[1] for x in volatile_momentum[:self.universe_size]}
        self.universe_symbols = top_stocks
        self.last_refresh_year = current_year

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

    def clear_position_tracking(self, symbol):
        self.entry_prices.pop(symbol, None)
        self.highest_prices.pop(symbol, None)
        self.profit_taken.pop(symbol, None)

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

            if symbol in self.held_symbols:
                entry_price = self.entry_prices.get(symbol, current_price)

                if symbol not in self.highest_prices:
                    self.highest_prices[symbol] = current_price
                else:
                    self.highest_prices[symbol] = max(self.highest_prices[symbol], current_price)

                gain = (current_price - entry_price) / entry_price

                # Profit taking
                if not self.profit_taken.get(symbol, False) and gain >= self.profit_take_threshold:
                    current_holding = self.portfolio[symbol].quantity
                    sell_qty = int(current_holding * self.profit_take_amount)
                    if sell_qty > 0:
                        self.market_order(symbol, -sell_qty, tag="Profit Take")
                        self.profit_taken[symbol] = True

                # Trailing stop
                if self.profit_taken.get(symbol, False):
                    high = self.highest_prices[symbol]
                    stop_price = high * (1 - self.trailing_stop_pct)
                    if current_price < stop_price:
                        self.liquidate(symbol, "Trailing Stop")
                        self.held_symbols.discard(symbol)
                        self.clear_position_tracking(symbol)
                        position_count -= 1
                        self.prev_ema[symbol] = {'fast': ema_fast, 'slow': ema_slow}
                        continue

                # EMA exit
                if bearish_cross:
                    self.liquidate(symbol, "EMA Exit")
                    self.held_symbols.discard(symbol)
                    self.clear_position_tracking(symbol)
                    position_count -= 1

            elif bullish_cross and symbol in self.current_universe:
                entry_candidates.append((symbol, self.momentum_scores.get(symbol, 0), current_price))

            self.prev_ema[symbol] = {'fast': ema_fast, 'slow': ema_slow}

        if entry_candidates and position_count < self.max_positions:
            for symbol, _, price in sorted(entry_candidates, key=lambda x: x[1], reverse=True):
                if position_count >= self.max_positions:
                    break
                self.set_holdings(symbol, self.weight_per_stock)
                self.held_symbols.add(symbol)
                self.entry_prices[symbol] = price
                self.highest_prices[symbol] = price
                self.profit_taken[symbol] = False
                position_count += 1
