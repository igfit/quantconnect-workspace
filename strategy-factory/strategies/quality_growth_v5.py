"""
Quality Growth v5 - Simple and focused

Based on v1 but:
1. Remove UNH (healthcare struggling in 2025)
2. Remove MA (redundant with V)
3. Add AVGO (semi diversification)
4. Keep simple equal weight
5. Monthly rebalancing for faster response
"""

from AlgorithmImports import *
from datetime import timedelta


class QualityGrowthV5(QCAlgorithm):

    QUALITY_STOCKS = [
        "AAPL",   # Tech
        "MSFT",   # Cloud/AI
        "GOOGL",  # AI/Search
        "AMZN",   # Cloud/E-comm
        "NVDA",   # AI chips
        "META",   # Social/AI
        "V",      # Payments
        "COST",   # Consumer stable
        "AVGO",   # Semi diversified
    ]

    LEVERAGE = 1.3
    BEAR_EXPOSURE = 0.3  # Keep some exposure in bear (v1 approach)

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

        # Monthly rebalancing
        self.schedule.on(
            self.date_rules.month_start(0),
            self.time_rules.after_market_open(self.spy, 30),
            self.rebalance
        )

    def get_regime_exposure(self) -> float:
        if not self.spy_sma.is_ready:
            return 0.5
        if self.securities[self.spy].price > self.spy_sma.current.value:
            return 1.0
        else:
            return self.BEAR_EXPOSURE

    def rebalance(self):
        if self.is_warming_up:
            return

        regime = self.get_regime_exposure()
        weight = (self.LEVERAGE * regime) / len(self.stocks)

        for symbol in self.stocks:
            if self.securities[symbol].price > 0:
                self.set_holdings(symbol, weight)

    def on_data(self, data):
        pass
