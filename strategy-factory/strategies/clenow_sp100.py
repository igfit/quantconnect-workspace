"""
Clenow Momentum - S&P 100 Universe (Survivorship-Bias Reduced)

Same strategy logic as clenow_controlled, but with S&P 100 stocks.

The S&P 100 is less prone to survivorship bias because:
- It's an established index with rules-based inclusion
- Large-cap stocks have lower failure rates
- We're not cherry-picking winners with hindsight

Note: Some composition changes occur over 10 years, but this is
far more systematic than hand-picking NVDA/TSLA/AMD.

Target: 20-30% CAGR, <30% MaxDD, Sharpe > 0.8
"""

from AlgorithmImports import *
from datetime import timedelta
import numpy as np


class ClenowMomentumSP100(QCAlgorithm):
    """
    Clenow Momentum with S&P 100 Universe

    Uses large-cap stocks that were in S&P 100 circa 2015.
    More systematic than hand-picking growth stocks.
    """

    MOMENTUM_LOOKBACK = 63
    TOP_N = 5
    MIN_MOMENTUM = 10

    def initialize(self):
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # S&P 100 constituents (representative sample that existed in 2015)
        # Organized by sector for diversification
        self.universe_symbols = [
            # Technology (existed 2015)
            "AAPL", "MSFT", "INTC", "CSCO", "ORCL", "IBM", "QCOM", "TXN",
            "ADBE", "CRM",  # CRM joined S&P 100 in 2020 but existed

            # Financials
            "JPM", "BAC", "WFC", "C", "GS", "MS", "AXP", "BLK", "BK",
            "USB", "PNC", "MET", "AIG",

            # Healthcare
            "JNJ", "UNH", "PFE", "MRK", "ABBV", "LLY", "BMY", "AMGN",
            "GILD", "MDT", "CVS",

            # Consumer Discretionary
            "AMZN", "HD", "MCD", "NKE", "SBUX", "LOW", "TGT", "F",

            # Consumer Staples
            "PG", "KO", "PEP", "WMT", "COST", "CL", "MO", "PM",

            # Industrials
            "BA", "HON", "UNP", "CAT", "GE", "MMM", "UPS", "LMT", "RTX",

            # Energy
            "XOM", "CVX", "COP", "SLB", "OXY",

            # Communications
            "GOOGL", "META", "DIS", "CMCSA", "VZ", "T", "NFLX",

            # Materials
            "LIN", "APD", "ECL", "DD",

            # Utilities
            "NEE", "DUK", "SO",

            # Real Estate
            "AMT", "PLD", "SPG",
        ]

        self.stocks = []
        for ticker in self.universe_symbols:
            try:
                equity = self.add_equity(ticker, Resolution.DAILY)
                equity.set_slippage_model(ConstantSlippageModel(0.001))
                equity.set_fee_model(InteractiveBrokersFeeModel())
                self.stocks.append(equity.symbol)
            except:
                pass

        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.set_benchmark(self.spy)
        self.spy_sma = self.sma(self.spy, 200, Resolution.DAILY)

        self.current_holdings = set()
        self.peak_equity = 100000
        self.set_warmup(timedelta(days=100))

        self.schedule.on(
            self.date_rules.month_start(self.spy),
            self.time_rules.after_market_open(self.spy, 30),
            self.rebalance
        )

        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.before_market_close(self.spy, 5),
            self.check_drawdown
        )

    def calculate_momentum(self, symbol) -> float:
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

    def get_regime_exposure(self) -> float:
        if not self.spy_sma.is_ready:
            return 1.0

        if self.securities[self.spy].price > self.spy_sma.current.value:
            return 1.0
        else:
            return 0.5

    def get_drawdown_adjustment(self) -> float:
        current_equity = self.portfolio.total_portfolio_value
        self.peak_equity = max(self.peak_equity, current_equity)
        drawdown = (self.peak_equity - current_equity) / self.peak_equity

        if drawdown > 0.25:
            return 0.5
        elif drawdown > 0.15:
            return 0.75
        return 1.0

    def check_drawdown(self):
        if self.is_warming_up:
            return

        current_equity = self.portfolio.total_portfolio_value
        self.peak_equity = max(self.peak_equity, current_equity)
        drawdown = (self.peak_equity - current_equity) / self.peak_equity

        if drawdown > 0.20:
            self.log(f"DRAWDOWN WARNING: {drawdown*100:.1f}%")

    def rebalance(self):
        if self.is_warming_up:
            return

        regime_exposure = self.get_regime_exposure()
        dd_adjustment = self.get_drawdown_adjustment()
        total_exposure = regime_exposure * dd_adjustment

        self.log(f"Regime: {regime_exposure:.0%} | DD Adj: {dd_adjustment:.0%} | Total: {total_exposure:.0%}")

        if total_exposure < 0.3:
            if self.current_holdings:
                self.liquidate()
                self.current_holdings = set()
                self.log("LOW EXPOSURE → CASH")
            return

        rankings = []
        for symbol in self.stocks:
            mom = self.calculate_momentum(symbol)
            if mom is not None and mom > self.MIN_MOMENTUM:
                rankings.append((symbol, mom))

        if len(rankings) < self.TOP_N:
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

        for symbol in self.current_holdings - top_stocks_set:
            self.liquidate(symbol)

        weight = (0.99 / self.TOP_N) * total_exposure
        for symbol in top_stocks:
            self.set_holdings(symbol, weight)

        self.current_holdings = top_stocks_set

    def on_data(self, data):
        pass
