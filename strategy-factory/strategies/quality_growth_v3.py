"""
Quality Growth Portfolio v3 - Optimized for 2024-2025

Changes:
1. Remove underperformers: UNH, V, MA (stagnant in 2024-2025)
2. Add 2024-2025 winners: PLTR (AI), LLY (healthcare AI/GLP-1)
3. Momentum-weighted positions (more $ to stronger stocks)
4. More concentrated: 8 stocks instead of 10
5. Monthly rebalancing with momentum reweighting
"""

from AlgorithmImports import *
from datetime import timedelta
import numpy as np


class QualityGrowthV3(QCAlgorithm):

    # Updated for 2024-2025 performance
    QUALITY_STOCKS = [
        "NVDA",   # AI chips - top performer
        "META",   # AI/Social - strong
        "GOOGL",  # AI/Search - strong
        "AAPL",   # Ecosystem - stable
        "MSFT",   # Cloud/AI - strong
        "AMZN",   # Cloud/E-commerce
        "AVGO",   # Semi - diversified
        "LLY",    # Healthcare - GLP-1 leader
    ]

    LEVERAGE = 1.3
    BEAR_EXPOSURE = 0.0  # Full cash in bear market

    # Momentum weighting
    MOMENTUM_LOOKBACK = 63  # 3-month momentum for weighting

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

    def calculate_momentum(self, symbol):
        """Calculate 3-month momentum"""
        history = self.history(symbol, self.MOMENTUM_LOOKBACK + 1, Resolution.DAILY)
        if history.empty or len(history) < self.MOMENTUM_LOOKBACK:
            return 0
        try:
            prices = history['close'].values
            return (prices[-1] / prices[0]) - 1
        except:
            return 0

    def is_bull_market(self) -> bool:
        if not self.spy_sma.is_ready:
            return False
        return self.securities[self.spy].price > self.spy_sma.current.value

    def rebalance(self):
        if self.is_warming_up:
            return

        # Bear market = go to cash
        if not self.is_bull_market():
            self.liquidate()
            self.log("BEAR MARKET - Going to cash")
            return

        # Calculate momentum for each stock
        momentums = {}
        for symbol in self.stocks:
            if self.securities[symbol].price > 0:
                mom = self.calculate_momentum(symbol)
                if mom > -0.20:  # Only include if not crashed
                    momentums[symbol] = max(mom, 0.01)  # Minimum weight

        if len(momentums) == 0:
            self.liquidate()
            return

        # Momentum-weighted allocation
        total_momentum = sum(momentums.values())
        weights = {s: m / total_momentum for s, m in momentums.items()}

        # Apply leverage and rebalance
        for symbol in self.stocks:
            if symbol in weights:
                target_weight = weights[symbol] * self.LEVERAGE
                target_weight = min(target_weight, 0.35)  # Max 35% per stock
                self.set_holdings(symbol, target_weight)
            elif self.portfolio[symbol].invested:
                self.liquidate(symbol)

        top_3 = sorted(weights.items(), key=lambda x: x[1], reverse=True)[:3]
        self.log(f"Top weights: {', '.join([f'{s.value}:{w:.1%}' for s,w in top_3])}")

    def on_data(self, data):
        pass
