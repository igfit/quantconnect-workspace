"""
Quality Growth v7 - Dynamic Universe Selection

Strategy:
1. Dynamic universe: Screen US equities for quality metrics
2. Coarse filter: Price > $10, Volume > 1M, Dollar Volume > $50M
3. Fine filter: Market Cap > $50B, ROE > 15%, Positive earnings
4. Momentum rank: Top 10 by 3-month momentum
5. Monthly rebalancing with regime filter

No hardcoded tickers - fully dynamic selection
"""

from AlgorithmImports import *
from datetime import timedelta
import numpy as np


class QualityGrowthV7Dynamic(QCAlgorithm):

    # Universe parameters
    MIN_PRICE = 10
    MIN_VOLUME = 1_000_000
    MIN_DOLLAR_VOLUME = 50_000_000
    MIN_MARKET_CAP = 50_000_000_000  # $50B
    MIN_ROE = 0.15  # 15%

    # Portfolio parameters
    TOP_N = 10
    LEVERAGE = 1.3
    MOMENTUM_LOOKBACK = 63
    BEAR_EXPOSURE = 0.3

    def initialize(self):
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2026, 1, 9)
        self.set_cash(100000)

        # Universe selection
        self.universe_settings.resolution = Resolution.DAILY
        self.add_universe(self.coarse_filter, self.fine_filter)

        # SPY for regime detection
        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.set_benchmark(self.spy)
        self.spy_sma = self.sma(self.spy, 200, Resolution.DAILY)

        # Track selected universe
        self.selected_stocks = []
        self.momentum_scores = {}

        self.set_warmup(timedelta(days=210))

        # Monthly rebalancing
        self.schedule.on(
            self.date_rules.month_start(0),
            self.time_rules.after_market_open(self.spy, 60),
            self.rebalance
        )

    def coarse_filter(self, coarse):
        """Filter by price, volume, and dollar volume"""
        filtered = [x for x in coarse if
                    x.has_fundamental_data and
                    x.price > self.MIN_PRICE and
                    x.volume > self.MIN_VOLUME and
                    x.dollar_volume > self.MIN_DOLLAR_VOLUME]

        # Sort by dollar volume, take top 500 for fine filter
        sorted_by_volume = sorted(filtered, key=lambda x: x.dollar_volume, reverse=True)
        return [x.symbol for x in sorted_by_volume[:500]]

    def fine_filter(self, fine):
        """Filter by fundamentals: market cap, ROE, profitability"""
        filtered = []

        for stock in fine:
            try:
                # Market cap filter
                if stock.market_cap < self.MIN_MARKET_CAP:
                    continue

                # ROE filter
                if stock.operation_ratios.roe.value < self.MIN_ROE:
                    continue

                # Must have positive earnings
                if stock.earning_reports.basic_eps.value <= 0:
                    continue

                # Exclude financials and utilities (different dynamics)
                sector = stock.asset_classification.morningstar_sector_code
                if sector in [MorningstarSectorCode.FINANCIAL_SERVICES,
                              MorningstarSectorCode.UTILITIES]:
                    continue

                filtered.append(stock)

            except Exception:
                continue

        # Sort by market cap, return symbols
        sorted_stocks = sorted(filtered, key=lambda x: x.market_cap, reverse=True)

        # Take top 50 quality stocks for momentum ranking
        self.log(f"Fine filter: {len(sorted_stocks)} quality stocks passed")
        return [x.symbol for x in sorted_stocks[:50]]

    def on_securities_changed(self, changes):
        """Track universe changes"""
        for security in changes.added_securities:
            if security.symbol != self.spy:
                security.set_slippage_model(ConstantSlippageModel(0.001))

        # Update selected stocks list
        self.selected_stocks = [s for s in self.active_securities.keys()
                                if s != self.spy and self.securities[s].has_data]

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

        # Calculate momentum for all selected stocks
        self.momentum_scores = {}
        for symbol in self.selected_stocks:
            if not self.securities[symbol].has_data:
                continue
            if self.securities[symbol].price <= 0:
                continue

            mom = self.calculate_momentum(symbol)
            if mom is not None and mom > -0.10:  # Exclude stocks down >10%
                self.momentum_scores[symbol] = mom

        if len(self.momentum_scores) == 0:
            self.log("No stocks passed momentum filter")
            self.liquidate()
            return

        # Sort by momentum, take top N
        sorted_stocks = sorted(self.momentum_scores.items(),
                               key=lambda x: x[1], reverse=True)
        top_stocks = [s for s, _ in sorted_stocks[:self.TOP_N]]

        # Equal weight among selected stocks
        weight = (self.LEVERAGE * regime) / len(top_stocks)

        # Get current holdings
        current_symbols = set(s for s in self.selected_stocks
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
        self.log(f"Regime: {regime:.0%}, Universe: {len(self.selected_stocks)}, Top: {symbols_str}")

    def on_data(self, data):
        pass
