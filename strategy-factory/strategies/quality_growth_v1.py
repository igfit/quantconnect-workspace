"""
Quality Growth Portfolio v1

Different approach - buy and hold the best quality growth stocks:
1. Select top quality companies (high ROE, earnings growth, moat)
2. Equal weight portfolio of 10 stocks
3. Quarterly rebalancing
4. Market regime filter (SPY > 200 SMA = stay invested)
5. 1.3x leverage when in bull market

The thesis: Quality compounds over time, regime filter avoids major crashes
"""

from AlgorithmImports import *
from datetime import timedelta
import numpy as np


class QualityGrowthV1(QCAlgorithm):

    # Quality growth stocks - manually selected blue chips
    QUALITY_STOCKS = [
        "AAPL",   # Tech - Best ecosystem
        "MSFT",   # Tech - Cloud dominance
        "GOOGL",  # Tech - Search/AI dominance
        "AMZN",   # Consumer - E-commerce/Cloud
        "NVDA",   # Semi - AI chips leader
        "META",   # Tech - Social/AI
        "V",      # Finance - Payment network
        "MA",     # Finance - Payment network
        "UNH",    # Healthcare - Managed care
        "COST",   # Consumer - Membership retail
    ]

    LEVERAGE = 1.3
    BEAR_EXPOSURE = 0.3  # Reduce to 30% in bear market (not fully cash)

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

        # Quarterly rebalancing
        self.schedule.on(
            self.date_rules.month_start(0),
            self.time_rules.after_market_open(self.spy, 30),
            self.check_rebalance
        )

        self.last_rebalance_month = -1

    def check_rebalance(self):
        """Rebalance quarterly (every 3 months)"""
        if self.is_warming_up:
            return

        current_month = self.time.month
        # Rebalance in Jan, Apr, Jul, Oct
        if current_month in [1, 4, 7, 10] and current_month != self.last_rebalance_month:
            self.last_rebalance_month = current_month
            self.rebalance()

    def get_regime_exposure(self) -> float:
        if not self.spy_sma.is_ready:
            return 0.5  # Conservative until ready
        if self.securities[self.spy].price > self.spy_sma.current.value:
            return 1.0  # Bull market
        else:
            return self.BEAR_EXPOSURE  # Bear market - reduce but don't exit

    def rebalance(self):
        regime = self.get_regime_exposure()

        # Equal weight across all quality stocks
        weight = (self.LEVERAGE * regime) / len(self.stocks)

        self.log(f"Rebalancing: Regime={regime:.1f}, Weight={weight:.2%}")

        for symbol in self.stocks:
            if self.securities[symbol].price > 0:
                self.set_holdings(symbol, weight)

    def on_data(self, data):
        pass
