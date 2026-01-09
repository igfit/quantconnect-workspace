"""
Quality Growth v8 - Simplified Dynamic Universe

Strategy:
1. Dynamic universe: Top 100 US stocks by dollar volume (liquid mega caps)
2. Coarse filter only - no fundamental delays
3. Momentum rank: Top 10 by 3-month price momentum
4. Monthly rebalancing with regime filter
5. No sector restrictions - let momentum pick winners

Simpler = faster execution + less fundamental data lag
"""

from AlgorithmImports import *
from datetime import timedelta


class QualityGrowthV8Dynamic(QCAlgorithm):

    # Universe parameters
    MIN_PRICE = 20  # Higher price = better quality usually
    UNIVERSE_SIZE = 100  # Top 100 by dollar volume

    # Portfolio parameters
    TOP_N = 10
    LEVERAGE = 1.3
    MOMENTUM_LOOKBACK = 63  # 3 months
    MIN_MOMENTUM = -0.05  # Exclude stocks down >5%
    BEAR_EXPOSURE = 0.3

    def initialize(self):
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2026, 1, 9)
        self.set_cash(100000)

        # Coarse-only universe selection
        self.universe_settings.resolution = Resolution.DAILY
        self.add_universe(self.coarse_selection)

        # SPY for regime detection
        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.set_benchmark(self.spy)
        self.spy_sma = self.sma(self.spy, 200, Resolution.DAILY)

        # Track universe
        self.universe_stocks = []

        self.set_warmup(timedelta(days=210))

        # Monthly rebalancing
        self.schedule.on(
            self.date_rules.month_start(0),
            self.time_rules.after_market_open(self.spy, 60),
            self.rebalance
        )

    def coarse_selection(self, coarse):
        """Select top 100 stocks by dollar volume"""
        # Filter for tradeable stocks
        filtered = [x for x in coarse if
                    x.has_fundamental_data and
                    x.price > self.MIN_PRICE and
                    x.dollar_volume > 10_000_000]  # $10M daily minimum

        # Sort by dollar volume (proxy for market cap & liquidity)
        sorted_by_volume = sorted(filtered,
                                   key=lambda x: x.dollar_volume,
                                   reverse=True)

        # Return top 100
        selected = [x.symbol for x in sorted_by_volume[:self.UNIVERSE_SIZE]]
        return selected

    def on_securities_changed(self, changes):
        """Track universe changes"""
        for security in changes.added_securities:
            if security.symbol != self.spy:
                security.set_slippage_model(ConstantSlippageModel(0.001))

        # Update universe list
        self.universe_stocks = [s for s in self.active_securities.keys()
                                 if s != self.spy]

    def calculate_momentum(self, symbol):
        """Calculate 3-month momentum"""
        try:
            history = self.history(symbol, self.MOMENTUM_LOOKBACK + 1, Resolution.DAILY)
            if history.empty or len(history) < self.MOMENTUM_LOOKBACK:
                return None
            prices = history['close'].values
            return (prices[-1] / prices[0]) - 1
        except:
            return None

    def get_regime_exposure(self) -> float:
        if not self.spy_sma.is_ready:
            return 0.5
        if self.securities[self.spy].price > self.spy_sma.current.value:
            return 1.0
        return self.BEAR_EXPOSURE

    def rebalance(self):
        if self.is_warming_up:
            return

        regime = self.get_regime_exposure()

        # Calculate momentum for all universe stocks
        momentum_scores = {}
        for symbol in self.universe_stocks:
            try:
                if not self.securities[symbol].has_data:
                    continue
                if self.securities[symbol].price <= 0:
                    continue

                mom = self.calculate_momentum(symbol)
                if mom is not None and mom > self.MIN_MOMENTUM:
                    momentum_scores[symbol] = mom
            except:
                continue

        if len(momentum_scores) < 5:
            self.log(f"Only {len(momentum_scores)} stocks passed filter, holding")
            return

        # Sort by momentum, take top N
        sorted_stocks = sorted(momentum_scores.items(),
                               key=lambda x: x[1], reverse=True)
        top_stocks = [s for s, _ in sorted_stocks[:self.TOP_N]]

        # Equal weight among selected stocks
        weight = (self.LEVERAGE * regime) / len(top_stocks)

        # Get current holdings
        current_symbols = set(s for s in self.universe_stocks
                              if self.portfolio[s].invested)
        target_symbols = set(top_stocks)

        # Liquidate stocks no longer in top
        for symbol in current_symbols - target_symbols:
            self.liquidate(symbol)

        # Set holdings for top stocks
        for symbol in top_stocks:
            self.set_holdings(symbol, weight)

        # Log top 5
        top_5 = sorted_stocks[:5]
        symbols_str = ', '.join([f'{s.value}:{m:.1%}' for s, m in top_5])
        self.log(f"Regime: {regime:.0%}, Universe: {len(self.universe_stocks)}, Top: {symbols_str}")

    def on_data(self, data):
        pass
