from AlgorithmImports import *
import numpy as np

class EMADynamicVolatilityUniverse(QCAlgorithm):
    """
    EMA Crossover with Dynamic Volatility-Screened Universe

    NO HINDSIGHT BIAS - stocks selected based on real-time criteria:
    - Top 50 most volatile stocks by 60-day historical volatility
    - Minimum $10M daily dollar volume (liquidity)
    - Minimum $5 price (no penny stocks)
    - Universe refreshed monthly

    Signal: EMA(10) crosses above EMA(50) AND RSI < 70
    Exit: EMA(10) crosses below EMA(50)
    Position sizing: 8 positions at 12.5% each
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100000)

        # Universe settings
        self.universe_size = 50  # Top 50 most volatile
        self.min_price = 5.0
        self.min_dollar_volume = 10_000_000  # $10M daily
        self.volatility_lookback = 60  # 60-day volatility

        # Position settings
        self.max_positions = 8
        self.weight_per_stock = 0.125  # 12.5% each

        # Track indicators and positions
        self.indicators = {}  # {symbol: {'ema10': ind, 'ema50': ind, 'rsi': ind}}
        self.prev_ema = {}    # {symbol: {'ema10': val, 'ema50': val}}
        self.in_position = {} # {symbol: bool}
        self.active_universe = []

        # Add universe selection - refresh monthly
        self.add_universe(self.coarse_filter, self.fine_filter)
        self.universe_settings.resolution = Resolution.DAILY

        # Schedule universe refresh on first trading day of month
        self.schedule.on(
            self.date_rules.month_start(),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance_check
        )

        self.set_benchmark("SPY")
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)

        # Warmup for indicators
        self.set_warm_up(60, Resolution.DAILY)

    def coarse_filter(self, coarse):
        """First pass: liquidity and price filters"""
        # Filter by price and dollar volume
        filtered = [x for x in coarse
                   if x.has_fundamental_data
                   and x.price > self.min_price
                   and x.dollar_volume > self.min_dollar_volume]

        # Return top 200 by dollar volume for fine selection
        sorted_by_volume = sorted(filtered, key=lambda x: x.dollar_volume, reverse=True)
        return [x.symbol for x in sorted_by_volume[:200]]

    def fine_filter(self, fine):
        """Second pass: calculate volatility and select top N"""
        # Filter out financials and REITs (optional - they behave differently)
        filtered = [x for x in fine
                   if x.asset_classification.morningstar_sector_code not in [103, 104]]  # Financials, Real Estate

        # We need historical data to calculate volatility
        # Use the symbols that pass filters
        symbols = [x.symbol for x in filtered]

        # Calculate volatility for each symbol
        volatility_scores = []
        for symbol in symbols:
            history = self.history(symbol, self.volatility_lookback, Resolution.DAILY)
            if len(history) >= self.volatility_lookback * 0.8:  # Need at least 80% of data
                returns = history['close'].pct_change().dropna()
                if len(returns) > 0:
                    vol = returns.std() * np.sqrt(252)  # Annualized volatility
                    volatility_scores.append((symbol, vol))

        # Sort by volatility (highest first) and take top N
        volatility_scores.sort(key=lambda x: x[1], reverse=True)
        top_volatile = [x[0] for x in volatility_scores[:self.universe_size]]

        if volatility_scores:
            self.debug(f"Universe selected: {len(top_volatile)} stocks, top vol: {volatility_scores[0][1]:.2%}")
        else:
            self.debug("Universe selected: 0 stocks")

        return top_volatile

    def on_securities_changed(self, changes):
        """Handle universe changes - setup/teardown indicators"""
        # Remove securities no longer in universe
        for security in changes.removed_securities:
            symbol = security.symbol
            if symbol in self.indicators:
                del self.indicators[symbol]
            if symbol in self.prev_ema:
                del self.prev_ema[symbol]
            if symbol in self.in_position:
                # Liquidate if we have a position
                if self.in_position[symbol]:
                    self.liquidate(symbol, "Removed from universe")
                del self.in_position[symbol]

        # Add new securities
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

        # Update active universe list
        self.active_universe = [s.symbol for s in self.active_securities.values()
                               if s.symbol in self.indicators]

    def rebalance_check(self):
        """Monthly check - log current state"""
        position_count = sum(1 for v in self.in_position.values() if v)
        self.debug(f"Monthly check: {len(self.active_universe)} stocks in universe, {position_count} positions")

    def on_data(self, data):
        """Apply EMA crossover signal to dynamic universe"""
        if self.is_warming_up:
            return

        position_count = sum(1 for v in self.in_position.values() if v)

        for symbol in self.active_universe:
            if symbol not in data.bars:
                continue
            if symbol not in self.indicators:
                continue

            ind = self.indicators[symbol]

            # Check indicators are ready
            if not ind['ema10'].is_ready or not ind['ema50'].is_ready or not ind['rsi'].is_ready:
                continue

            ema10 = ind['ema10'].current.value
            ema50 = ind['ema50'].current.value
            rsi = ind['rsi'].current.value

            prev = self.prev_ema[symbol]
            if prev['ema10'] is None:
                self.prev_ema[symbol] = {'ema10': ema10, 'ema50': ema50}
                continue

            # Detect crossovers
            bullish_cross = prev['ema10'] <= prev['ema50'] and ema10 > ema50
            bearish_cross = prev['ema10'] >= prev['ema50'] and ema10 < ema50

            # Entry signal
            if bullish_cross and rsi < 70 and not self.in_position.get(symbol, False):
                if position_count < self.max_positions:
                    self.set_holdings(symbol, self.weight_per_stock)
                    self.in_position[symbol] = True
                    position_count += 1
                    self.debug(f"BUY {symbol.value}: EMA cross, RSI={rsi:.1f}")

            # Exit signal
            elif bearish_cross and self.in_position.get(symbol, False):
                self.liquidate(symbol)
                self.in_position[symbol] = False
                position_count -= 1
                self.debug(f"SELL {symbol.value}: EMA cross down")

            # Update previous values
            self.prev_ema[symbol] = {'ema10': ema10, 'ema50': ema50}
