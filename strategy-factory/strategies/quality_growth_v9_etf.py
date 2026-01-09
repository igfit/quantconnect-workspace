"""
Quality Growth v9 - ETF Constituent Based

Strategy:
1. Use QQQ constituents as dynamic universe (top 100 NASDAQ stocks)
2. QQQ rebalances quarterly - stable but dynamic
3. Momentum rank: Top 10 by 3-month momentum
4. Monthly rebalancing with regime filter

Benefits: Universe is curated by NASDAQ, but still dynamic
"""

from AlgorithmImports import *
from datetime import timedelta


class QualityGrowthV9ETF(QCAlgorithm):

    # Portfolio parameters
    TOP_N = 10
    LEVERAGE = 1.3
    MOMENTUM_LOOKBACK = 63
    MIN_MOMENTUM = -0.05
    BEAR_EXPOSURE = 0.3

    def initialize(self):
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2026, 1, 9)
        self.set_cash(100000)

        # Add QQQ for constituent universe
        self.qqq = self.add_equity("QQQ", Resolution.DAILY).symbol
        self.set_benchmark(self.qqq)

        # SPY for regime detection (broader market)
        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma = self.sma(self.spy, 200, Resolution.DAILY)

        # Add ETF universe - will track QQQ holdings
        self.add_universe(self.universe.etf(self.qqq, self.universe_settings, self.etf_filter))

        self.universe_stocks = []
        self.set_warmup(timedelta(days=210))

        # Monthly rebalancing
        self.schedule.on(
            self.date_rules.month_start(0),
            self.time_rules.after_market_open(self.spy, 60),
            self.rebalance
        )

    def etf_filter(self, constituents):
        """Accept all QQQ constituents"""
        # Filter out very small weights (handle None)
        filtered = [c for c in constituents if c.weight is not None and c.weight > 0.001]
        return [c.symbol for c in filtered]

    def on_securities_changed(self, changes):
        """Track universe changes"""
        for security in changes.added_securities:
            sym = security.symbol
            if sym not in [self.spy, self.qqq]:
                security.set_slippage_model(ConstantSlippageModel(0.001))

        # Update universe list
        self.universe_stocks = [s for s in self.active_securities.keys()
                                 if s not in [self.spy, self.qqq]]

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

        # Calculate momentum for all QQQ constituents
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
            self.log(f"Only {len(momentum_scores)} stocks passed filter")
            return

        # Sort by momentum, take top N
        sorted_stocks = sorted(momentum_scores.items(),
                               key=lambda x: x[1], reverse=True)
        top_stocks = [s for s, _ in sorted_stocks[:self.TOP_N]]

        # Equal weight
        weight = (self.LEVERAGE * regime) / len(top_stocks)

        # Liquidate old positions
        for symbol in list(self.portfolio.keys()):
            if self.portfolio[symbol].invested and symbol not in top_stocks:
                if symbol not in [self.spy, self.qqq]:
                    self.liquidate(symbol)

        # Set new positions
        for symbol in top_stocks:
            self.set_holdings(symbol, weight)

        # Log
        top_5 = sorted_stocks[:5]
        symbols_str = ', '.join([f'{s.value}:{m:.1%}' for s, m in top_5])
        self.log(f"Regime: {regime:.0%}, QQQ constituents: {len(self.universe_stocks)}, Top: {symbols_str}")

    def on_data(self, data):
        pass
