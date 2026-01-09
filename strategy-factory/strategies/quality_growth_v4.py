"""
Quality Growth Portfolio v4 - Balanced for consistent returns

Learnings from v1-v3:
- v1: Good consistency but 2025 only +4.5%
- v3: Amazing 2023-2024 but -11% in 2025 (momentum over-concentrated)

v4 approach:
1. Equal weight (no momentum weighting - too volatile)
2. Better diversification: Mix of AI winners + stable compounders
3. Remove healthcare (UNH struggled)
4. Keep payment networks (V, MA) for stability
5. Add COST for consumer stability
"""

from AlgorithmImports import *
from datetime import timedelta
import numpy as np


class QualityGrowthV4(QCAlgorithm):

    # Balanced portfolio: AI leaders + stable compounders
    QUALITY_STOCKS = [
        # AI/Tech leaders (growth)
        "NVDA",   # AI chips
        "META",   # AI/Social
        "GOOGL",  # AI/Search
        "MSFT",   # Cloud/AI
        # Stable compounders (consistency)
        "AAPL",   # Ecosystem
        "V",      # Payments - stable
        "COST",   # Consumer - defensive
        "AVGO",   # Semi - diversified
    ]

    LEVERAGE = 1.25  # Slightly lower for stability
    BEAR_EXPOSURE = 0.0

    def initialize(self):
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2026, 1, 9)
        self.set_cash(100000)

        self.stocks = []
        for ticker in self.QUALITY_STOCKS:
            try:
                equity = self.add_equity(ticker, Resolution.DAILY)
                equity.set_slippage_model(ConstantSlippageModel(0.001))
                self.stocks.append(equity.symbol)
            except Exception as e:
                self.debug(f"Could not add {ticker}: {e}")

        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.set_benchmark(self.spy)
        self.spy_sma = self.sma(self.spy, 200, Resolution.DAILY)

        self.set_warmup(timedelta(days=210))

        # Quarterly rebalancing (less turnover)
        self.schedule.on(
            self.date_rules.month_start(0),
            self.time_rules.after_market_open(self.spy, 30),
            self.check_rebalance
        )

        self.last_rebalance_month = -1

    def check_rebalance(self):
        if self.is_warming_up:
            return
        current_month = self.time.month
        if current_month in [1, 4, 7, 10] and current_month != self.last_rebalance_month:
            self.last_rebalance_month = current_month
            self.rebalance()

    def is_bull_market(self) -> bool:
        if not self.spy_sma.is_ready:
            return False
        return self.securities[self.spy].price > self.spy_sma.current.value

    def rebalance(self):
        if not self.is_bull_market():
            self.liquidate()
            self.log("BEAR - Cash")
            return

        # Simple equal weight
        weight = self.LEVERAGE / len(self.stocks)

        for symbol in self.stocks:
            if self.securities[symbol].price > 0:
                self.set_holdings(symbol, weight)

    def on_data(self, data):
        pass
