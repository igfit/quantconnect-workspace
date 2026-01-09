"""
Quality Growth v6 Hybrid - Combines best elements

Strategy:
1. Broader universe: Quality growth + sector leaders
2. Momentum filter: Only hold stocks with positive 3-month momentum
3. Regime filter: SPY > 200 SMA
4. Dynamic rotation: Monthly rebalance to top momentum stocks
5. Equal weight within selected stocks

Goal: Better 2025 by avoiding weak stocks dynamically
"""

from AlgorithmImports import *
from datetime import timedelta
import numpy as np


class QualityGrowthV6Hybrid(QCAlgorithm):

    # Broader universe - quality + sector leaders
    UNIVERSE = [
        # Big Tech (quality growth)
        "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META",
        # Payments/Finance
        "V", "MA", "JPM", "GS",
        # Healthcare
        "LLY", "UNH", "JNJ",
        # Consumer
        "COST", "WMT", "HD",
        # Semiconductors
        "AVGO", "AMD", "QCOM",
        # Energy (for diversification)
        "XOM", "CVX",
    ]

    LEVERAGE = 1.0
    TOP_N = 10  # Hold top 10 momentum stocks
    MOMENTUM_LOOKBACK = 63  # 3-month momentum
    MIN_MOMENTUM = -0.10  # Exclude stocks down >10%
    BEAR_EXPOSURE = 0.3

    def initialize(self):
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2026, 1, 9)
        self.set_cash(100000)

        self.stocks = []
        for ticker in self.UNIVERSE:
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
            return None
        try:
            prices = history['close'].values
            return (prices[-1] / prices[0]) - 1
        except:
            return None

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

        # Calculate momentum for all stocks
        momentum_scores = {}
        for symbol in self.stocks:
            if self.securities[symbol].price <= 0:
                continue
            mom = self.calculate_momentum(symbol)
            if mom is not None and mom > self.MIN_MOMENTUM:
                momentum_scores[symbol] = mom

        if len(momentum_scores) == 0:
            self.liquidate()
            return

        # Sort by momentum, take top N
        sorted_stocks = sorted(momentum_scores.items(), key=lambda x: x[1], reverse=True)
        top_stocks = [s for s, _ in sorted_stocks[:self.TOP_N]]

        # Equal weight among selected stocks
        weight = (self.LEVERAGE * regime) / len(top_stocks)

        # Get current holdings
        current_symbols = set(s for s in self.stocks if self.portfolio[s].invested)
        target_symbols = set(top_stocks)

        # Liquidate stocks no longer in top
        for symbol in current_symbols - target_symbols:
            self.liquidate(symbol)

        # Set holdings for top stocks
        for symbol in top_stocks:
            self.set_holdings(symbol, weight)

        # Log top 3
        top_3 = sorted_stocks[:3]
        self.log(f"Regime: {regime:.0%}, Top: {', '.join([f'{s.value}:{m:.1%}' for s,m in top_3])}")

    def on_data(self, data):
        pass
