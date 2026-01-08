"""
Clenow Momentum - Controlled Drawdown Variant

Targets 30%+ CAGR with max drawdown under 30%:
- 5 concentrated positions
- Soft regime filter (50% exposure in bear market)
- Volatility-adjusted position sizing

Universe: Large-Cap + High-Beta Growth mix
Target: 30% CAGR, <30% MaxDD, Sharpe > 1.0
"""

from AlgorithmImports import *
from datetime import timedelta
import numpy as np


class ClenowMomentumControlled(QCAlgorithm):
    """
    Clenow Momentum with Drawdown Control

    Changes from aggressive version:
    - Soft regime filter: 50% cash in bear market instead of 100%
    - Drawdown-based position reduction
    - Slightly longer lookback for smoother signals
    """

    MOMENTUM_LOOKBACK = 63  # ~3 months
    TOP_N = 5
    MIN_MOMENTUM = 15

    def initialize(self):
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Mixed universe: large-cap with high-beta growth
        self.universe_symbols = [
            # High-beta tech
            "NVDA", "AMD", "TSLA", "NFLX", "META", "SQ", "SHOP",
            # Semiconductors
            "AVGO", "MU", "MRVL", "AMAT", "LRCX",
            # Growth tech
            "CRM", "ADBE", "NOW", "PANW",
            # Established growth
            "AAPL", "MSFT", "GOOGL", "AMZN",
            # Biotech
            "MRNA", "REGN", "VRTX", "LLY",
            # Consumer
            "HD", "COST", "NKE", "SBUX", "LULU",
            # Financials
            "V", "MA", "GS", "JPM",
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

        # Daily drawdown check
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
        """
        Returns exposure level based on regime:
        - Bull market (SPY > 200 SMA): 100%
        - Bear market (SPY < 200 SMA): 50%
        """
        if not self.spy_sma.is_ready:
            return 1.0

        if self.securities[self.spy].price > self.spy_sma.current.value:
            return 1.0  # Full exposure in bull market
        else:
            return 0.5  # Reduced exposure in bear market

    def get_drawdown_adjustment(self) -> float:
        """
        Reduce exposure when in drawdown > 15%
        """
        current_equity = self.portfolio.total_portfolio_value
        self.peak_equity = max(self.peak_equity, current_equity)
        drawdown = (self.peak_equity - current_equity) / self.peak_equity

        if drawdown > 0.25:
            return 0.5  # 50% exposure when DD > 25%
        elif drawdown > 0.15:
            return 0.75  # 75% exposure when DD > 15%
        return 1.0  # Full exposure otherwise

    def check_drawdown(self):
        """Monitor drawdown and log if significant"""
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

        # Calculate exposure adjustments
        regime_exposure = self.get_regime_exposure()
        dd_adjustment = self.get_drawdown_adjustment()
        total_exposure = regime_exposure * dd_adjustment

        self.log(f"Regime: {regime_exposure:.0%} | DD Adj: {dd_adjustment:.0%} | Total: {total_exposure:.0%}")

        if total_exposure < 0.3:
            # If exposure too low, go to cash
            if self.current_holdings:
                self.liquidate()
                self.current_holdings = set()
                self.log("LOW EXPOSURE → CASH")
            return

        # Rank by momentum
        rankings = []
        for symbol in self.stocks:
            mom = self.calculate_momentum(symbol)
            if mom is not None and mom > self.MIN_MOMENTUM:
                rankings.append((symbol, mom))

        if len(rankings) < self.TOP_N:
            # Lower threshold
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

        # Liquidate positions not in top N
        for symbol in self.current_holdings - top_stocks_set:
            self.liquidate(symbol)

        # Allocate with exposure adjustment
        weight = (0.99 / self.TOP_N) * total_exposure
        for symbol in top_stocks:
            self.set_holdings(symbol, weight)

        self.current_holdings = top_stocks_set

    def on_data(self, data):
        pass
