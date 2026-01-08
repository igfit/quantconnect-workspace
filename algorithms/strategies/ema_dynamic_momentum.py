from AlgorithmImports import *
import numpy as np

class EMADynamicMomentumUniverse(QCAlgorithm):
    """
    EMA Crossover with Dynamic Momentum-Screened Universe

    NO HINDSIGHT BIAS - stocks selected based on:
    - Top 50 stocks by 6-month price momentum (trending UP)
    - Minimum $10M daily dollar volume (liquidity)
    - Minimum $10 price (no penny stocks)
    - Universe refreshed monthly

    Key insight: Momentum screen filters for "good volatility" (uptrends)
    vs pure volatility screen which gets "bad volatility" (distress)

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
        self.min_price = 10.0  # Higher price floor
        self.min_dollar_volume = 10_000_000
        self.momentum_lookback = 126  # ~6 months

        # Position settings
        self.max_positions = 8
        self.weight_per_stock = 0.125

        # Track indicators and positions
        self.indicators = {}
        self.prev_ema = {}
        self.in_position = {}
        self.active_universe = []

        # Add universe selection
        self.add_universe(self.coarse_filter, self.fine_filter)
        self.universe_settings.resolution = Resolution.DAILY

        self.set_benchmark("SPY")
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)
        self.set_warm_up(60, Resolution.DAILY)

    def coarse_filter(self, coarse):
        """First pass: liquidity and price filters"""
        filtered = [x for x in coarse
                   if x.has_fundamental_data
                   and x.price > self.min_price
                   and x.dollar_volume > self.min_dollar_volume]

        # Top 300 by dollar volume for fine selection
        sorted_by_volume = sorted(filtered, key=lambda x: x.dollar_volume, reverse=True)
        return [x.symbol for x in sorted_by_volume[:300]]

    def fine_filter(self, fine):
        """Second pass: calculate momentum and select top N"""
        # Filter out financials, utilities, real estate
        filtered = [x for x in fine
                   if x.asset_classification.morningstar_sector_code not in [103, 104, 207]]

        symbols = [x.symbol for x in filtered]

        # Calculate 6-month momentum for each symbol
        momentum_scores = []
        for symbol in symbols:
            history = self.history(symbol, self.momentum_lookback, Resolution.DAILY)
            if len(history) >= self.momentum_lookback * 0.8:
                try:
                    start_price = history['close'].iloc[0]
                    end_price = history['close'].iloc[-1]
                    if start_price > 0:
                        momentum = (end_price - start_price) / start_price
                        # Only include positive momentum stocks
                        if momentum > 0:
                            momentum_scores.append((symbol, momentum))
                except:
                    pass

        # Sort by momentum (highest first) and take top N
        momentum_scores.sort(key=lambda x: x[1], reverse=True)
        top_momentum = [x[0] for x in momentum_scores[:self.universe_size]]

        if momentum_scores:
            self.debug(f"Universe: {len(top_momentum)} stocks, top momentum: {momentum_scores[0][1]:.1%}")

        return top_momentum

    def on_securities_changed(self, changes):
        """Handle universe changes"""
        for security in changes.removed_securities:
            symbol = security.symbol
            if symbol in self.indicators:
                del self.indicators[symbol]
            if symbol in self.prev_ema:
                del self.prev_ema[symbol]
            if symbol in self.in_position:
                if self.in_position[symbol]:
                    self.liquidate(symbol, "Removed from universe")
                del self.in_position[symbol]

        for security in changes.added_securities:
            symbol = security.symbol
            if symbol not in self.indicators:
                self.indicators[symbol] = {
                    'ema10': self.ema(symbol, 10, Resolution.DAILY),
                    'ema50': self.ema(symbol, 50, Resolution.DAILY),
                    'rsi': self.rsi(symbol, 14, MovingAverageType.SIMPLE, Resolution.DAILY)
                }
                self.prev_ema[symbol] = {'ema10': None, 'ema50': None}
                self.in_position[symbol] = False

        self.active_universe = [s.symbol for s in self.active_securities.values()
                               if s.symbol in self.indicators]

    def on_data(self, data):
        """Apply EMA crossover signal"""
        if self.is_warming_up:
            return

        position_count = sum(1 for v in self.in_position.values() if v)

        for symbol in self.active_universe:
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

            prev = self.prev_ema[symbol]
            if prev['ema10'] is None:
                self.prev_ema[symbol] = {'ema10': ema10, 'ema50': ema50}
                continue

            bullish_cross = prev['ema10'] <= prev['ema50'] and ema10 > ema50
            bearish_cross = prev['ema10'] >= prev['ema50'] and ema10 < ema50

            if bullish_cross and rsi < 70 and not self.in_position.get(symbol, False):
                if position_count < self.max_positions:
                    self.set_holdings(symbol, self.weight_per_stock)
                    self.in_position[symbol] = True
                    position_count += 1

            elif bearish_cross and self.in_position.get(symbol, False):
                self.liquidate(symbol)
                self.in_position[symbol] = False
                position_count -= 1

            self.prev_ema[symbol] = {'ema10': ema10, 'ema50': ema50}
