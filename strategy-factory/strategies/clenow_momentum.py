"""
Clenow Momentum Ranking Strategy

Based on Andreas Clenow's "Stocks on the Move" methodology.
Ranks stocks by exponential regression momentum, holds top N performers.

Universe: Large-Cap Liquid (Universe C) - 80+ mega-cap stocks
Rebalance: Monthly (first trading day)
Holding Period: ~1 month

WHY THIS WORKS:
- Momentum is the most documented market anomaly (Jegadeesh & Titman)
- Exponential regression captures trend quality better than simple returns
- Large-cap stocks have more persistent momentum trends
- Monthly rebalancing balances signal quality vs transaction costs

KEY PARAMETERS:
- MOMENTUM_LOOKBACK = 90 (3 months of data for regression)
- TOP_N = 10 (number of stocks to hold)
- REGIME_FILTER = True (only invest when SPY > 200 SMA)

EXPECTED CHARACTERISTICS:
- Win rate: 45-55%
- Strong in bull markets
- Regime filter protects in crashes
- Risk/reward typically > 2:1
"""

from AlgorithmImports import *
from datetime import timedelta
import numpy as np


class ClenowMomentumRanking(QCAlgorithm):
    """
    Clenow Momentum Ranking on Large-Cap Universe

    Rules:
    1. Monthly rebalance on first trading day
    2. Calculate exponential regression momentum for each stock
    3. Rank by momentum, hold top N stocks with equal weight
    4. Only invest when SPY > 200 SMA (regime filter)
    """

    # Configuration
    MOMENTUM_LOOKBACK = 90  # Days for momentum calculation
    TOP_N = 10  # Number of stocks to hold
    USE_REGIME_FILTER = True
    MIN_MOMENTUM = 0  # Minimum momentum to buy (filter out negative momentum)

    def initialize(self):
        # Backtest period
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Large-cap liquid universe (Universe C)
        self.universe_symbols = [
            # Technology
            "AAPL", "MSFT", "GOOGL", "INTC", "CSCO", "ORCL", "IBM", "QCOM", "TXN", "ADBE", "CRM", "AVGO",
            # Financials
            "JPM", "BAC", "WFC", "C", "GS", "MS", "BLK", "AXP", "USB", "PNC",
            # Healthcare
            "JNJ", "UNH", "PFE", "MRK", "ABBV", "TMO", "ABT", "MDT", "AMGN", "GILD", "BMY", "LLY",
            # Consumer
            "AMZN", "HD", "MCD", "NKE", "SBUX", "TGT", "COST", "LOW", "TJX",
            # Industrials
            "BA", "HON", "UNP", "CAT", "GE", "MMM", "LMT", "RTX", "DE", "FDX",
            # Energy
            "XOM", "CVX", "COP", "SLB", "EOG",
            # Communications
            "META", "NFLX", "DIS", "CMCSA", "VZ", "T",
            # Consumer Staples
            "KO", "PEP", "PM", "WMT", "PG", "CL",
            # Other
            "BRK.B", "V", "MA",
            # Utilities
            "NEE", "DUK", "SO",
        ]

        # Add all stocks
        self.stocks = []
        for ticker in self.universe_symbols:
            equity = self.add_equity(ticker, Resolution.DAILY)
            equity.set_slippage_model(ConstantSlippageModel(0.001))
            equity.set_fee_model(InteractiveBrokersFeeModel())
            self.stocks.append(equity.symbol)

        # SPY for regime filter and benchmark
        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.set_benchmark(self.spy)

        # Regime filter: 200-day SMA
        self.spy_sma = self.sma(self.spy, 200, Resolution.DAILY)

        # Track current holdings
        self.current_holdings = set()

        # Trade logging
        self.rebalance_log = []

        # Warmup
        self.set_warmup(timedelta(days=250))

        # Schedule monthly rebalance
        self.schedule.on(
            self.date_rules.month_start(self.spy),
            self.time_rules.after_market_open(self.spy, 30),
            self.rebalance
        )

    def calculate_momentum(self, symbol) -> float:
        """
        Calculate exponential regression momentum (Clenow style).
        Returns annualized slope * R-squared (momentum quality).
        """
        history = self.history(symbol, self.MOMENTUM_LOOKBACK + 1, Resolution.DAILY)

        if history.empty or len(history) < self.MOMENTUM_LOOKBACK:
            return None

        try:
            prices = history['close'].values
            if len(prices) < 20:  # Need minimum data
                return None

            # Log prices for exponential regression
            log_prices = np.log(prices)

            # Simple linear regression on log prices
            x = np.arange(len(log_prices))
            slope, intercept = np.polyfit(x, log_prices, 1)

            # Annualize the slope (252 trading days)
            annualized_slope = (np.exp(slope * 252) - 1) * 100  # As percentage

            # Calculate R-squared
            predictions = slope * x + intercept
            ss_res = np.sum((log_prices - predictions) ** 2)
            ss_tot = np.sum((log_prices - np.mean(log_prices)) ** 2)
            r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

            # Momentum score = annualized return * R-squared
            momentum_score = annualized_slope * r_squared

            return momentum_score

        except Exception as e:
            return None

    def rebalance(self):
        """Monthly momentum ranking rebalance"""
        if self.is_warming_up:
            return

        # Check regime filter
        if self.USE_REGIME_FILTER:
            if not self.spy_sma.is_ready:
                return
            if self.securities[self.spy].price < self.spy_sma.current.value:
                # Bear market - go to cash
                if self.current_holdings:
                    self.liquidate()
                    self.current_holdings = set()
                    self.log(f"REGIME FILTER: SPY below 200 SMA → CASH")
                return

        # Calculate momentum for each stock
        rankings = []
        for symbol in self.stocks:
            mom = self.calculate_momentum(symbol)
            if mom is not None and mom > self.MIN_MOMENTUM:
                rankings.append((symbol, mom))

        if len(rankings) < self.TOP_N:
            self.log(f"Not enough stocks with positive momentum: {len(rankings)}")
            return

        # Sort by momentum (highest first)
        rankings.sort(key=lambda x: x[1], reverse=True)

        # Select top N
        top_stocks = [r[0] for r in rankings[:self.TOP_N]]
        top_stocks_set = set(top_stocks)

        # Log top 5 rankings
        self.log(f"TOP 5: {' > '.join([f'{r[0].value}({r[1]:.1f})' for r in rankings[:5]])}")

        # Log rotation
        entering = top_stocks_set - self.current_holdings
        exiting = self.current_holdings - top_stocks_set

        if entering or exiting:
            self.rebalance_log.append({
                'date': str(self.time.date()),
                'entering': [str(s) for s in entering],
                'exiting': [str(s) for s in exiting],
            })

        # Liquidate stocks no longer in top N
        for symbol in exiting:
            self.liquidate(symbol)
            self.log(f"EXIT: {symbol}")

        # Equal weight allocation to top N
        weight = 0.99 / self.TOP_N

        for symbol in top_stocks:
            self.set_holdings(symbol, weight)
            if symbol in entering:
                self.log(f"ENTRY: {symbol}")

        self.current_holdings = top_stocks_set

    def on_end_of_algorithm(self):
        """Log summary at end of backtest"""
        self.log("=" * 60)
        self.log("CLENOW MOMENTUM RANKING - SUMMARY")
        self.log("=" * 60)
        self.log(f"Total Rebalances: {len(self.rebalance_log)}")

        # Count stock appearances
        stock_counts = {}
        for rotation in self.rebalance_log:
            for s in rotation['entering']:
                ticker = s.split()[0]
                stock_counts[ticker] = stock_counts.get(ticker, 0) + 1

        self.log("Top 10 Most Selected Stocks:")
        for ticker, count in sorted(stock_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
            self.log(f"  {ticker}: {count}")

        self.log("=" * 60)

    def on_data(self, data):
        """Required method - rebalancing done via scheduled event"""
        pass
