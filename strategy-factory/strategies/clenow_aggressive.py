"""
Clenow Momentum - Aggressive Variant

More concentrated version targeting 30%+ CAGR:
- 5 positions instead of 10 (higher conviction)
- NO regime filter (stay fully invested)
- Higher minimum momentum threshold
- Shorter lookback for faster signals

Universe: Large-Cap Liquid (Universe C)
Rebalance: Monthly
Target: 30% CAGR with 20-30% max drawdown
"""

from AlgorithmImports import *
from datetime import timedelta
import numpy as np


class ClenowMomentumAggressive(QCAlgorithm):
    """
    Aggressive Clenow Momentum - High Concentration

    Changes from base version:
    - TOP_N = 5 (concentrated)
    - MOMENTUM_LOOKBACK = 60 (faster signals)
    - USE_REGIME_FILTER = False (always invested)
    - MIN_MOMENTUM = 20 (only strong momentum)
    """

    # Configuration - AGGRESSIVE
    MOMENTUM_LOOKBACK = 60  # Shorter lookback for faster signals
    TOP_N = 5  # Concentrated portfolio
    USE_REGIME_FILTER = False  # Stay invested through volatility
    MIN_MOMENTUM = 20  # Higher threshold - only strong momentum

    def initialize(self):
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Large-cap universe with some growth names
        self.universe_symbols = [
            # Technology (higher beta)
            "AAPL", "MSFT", "GOOGL", "NVDA", "AMD", "ADBE", "CRM", "AVGO",
            "QCOM", "TXN", "INTC", "CSCO",
            # Growth/Consumer
            "AMZN", "NFLX", "META", "TSLA",
            # Financials
            "JPM", "GS", "MS", "V", "MA", "AXP",
            # Healthcare/Biotech
            "UNH", "LLY", "ABBV", "MRK", "TMO", "ISRG",
            # Industrials
            "BA", "CAT", "DE", "HON", "UNP",
            # Consumer
            "HD", "NKE", "SBUX", "MCD", "COST",
            # Energy (cyclical)
            "XOM", "CVX",
        ]

        self.stocks = []
        for ticker in self.universe_symbols:
            equity = self.add_equity(ticker, Resolution.DAILY)
            equity.set_slippage_model(ConstantSlippageModel(0.001))
            equity.set_fee_model(InteractiveBrokersFeeModel())
            self.stocks.append(equity.symbol)

        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.set_benchmark(self.spy)
        self.spy_sma = self.sma(self.spy, 200, Resolution.DAILY)

        self.current_holdings = set()
        self.rebalance_log = []
        self.set_warmup(timedelta(days=100))

        self.schedule.on(
            self.date_rules.month_start(self.spy),
            self.time_rules.after_market_open(self.spy, 30),
            self.rebalance
        )

    def calculate_momentum(self, symbol) -> float:
        """Exponential regression momentum score"""
        history = self.history(symbol, self.MOMENTUM_LOOKBACK + 1, Resolution.DAILY)
        if history.empty or len(history) < self.MOMENTUM_LOOKBACK:
            return None

        try:
            prices = history['close'].values
            if len(prices) < 20:
                return None

            log_prices = np.log(prices)
            x = np.arange(len(log_prices))
            slope, intercept = np.polyfit(x, log_prices, 1)
            annualized_slope = (np.exp(slope * 252) - 1) * 100

            predictions = slope * x + intercept
            ss_res = np.sum((log_prices - predictions) ** 2)
            ss_tot = np.sum((log_prices - np.mean(log_prices)) ** 2)
            r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

            return annualized_slope * r_squared
        except:
            return None

    def rebalance(self):
        if self.is_warming_up:
            return

        # Optional soft regime filter - reduce exposure in bear market
        if self.USE_REGIME_FILTER and self.spy_sma.is_ready:
            if self.securities[self.spy].price < self.spy_sma.current.value:
                if self.current_holdings:
                    self.liquidate()
                    self.current_holdings = set()
                return

        rankings = []
        for symbol in self.stocks:
            mom = self.calculate_momentum(symbol)
            if mom is not None and mom > self.MIN_MOMENTUM:
                rankings.append((symbol, mom))

        if len(rankings) < self.TOP_N:
            self.log(f"Only {len(rankings)} stocks with momentum > {self.MIN_MOMENTUM}")
            # Lower threshold if not enough candidates
            rankings = []
            for symbol in self.stocks:
                mom = self.calculate_momentum(symbol)
                if mom is not None and mom > 0:
                    rankings.append((symbol, mom))

        if len(rankings) < self.TOP_N:
            return

        rankings.sort(key=lambda x: x[1], reverse=True)
        top_stocks = [r[0] for r in rankings[:self.TOP_N]]
        top_stocks_set = set(top_stocks)

        self.log(f"TOP {self.TOP_N}: {' > '.join([f'{r[0].value}({r[1]:.0f})' for r in rankings[:self.TOP_N]])}")

        entering = top_stocks_set - self.current_holdings
        exiting = self.current_holdings - top_stocks_set

        for symbol in exiting:
            self.liquidate(symbol)

        weight = 0.99 / self.TOP_N
        for symbol in top_stocks:
            self.set_holdings(symbol, weight)

        self.current_holdings = top_stocks_set

    def on_data(self, data):
        pass
