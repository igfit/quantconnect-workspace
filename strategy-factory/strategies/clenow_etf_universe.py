"""
Clenow Momentum - Systematic ETF Universe

Same strategy logic as clenow_controlled, but with a SURVIVORSHIP-BIAS-FREE universe:
- Sector SPDRs (existed since 1998)
- Broad market ETFs
- Industry ETFs
- Factor ETFs

All ETFs selected existed BEFORE 2015-01-01 start date.
No hindsight stock picking.

Target: 15-25% CAGR, <25% MaxDD, Sharpe > 0.8
"""

from AlgorithmImports import *
from datetime import timedelta
import numpy as np


class ClenowMomentumETF(QCAlgorithm):
    """
    Clenow Momentum with Systematic ETF Universe

    Universe selection criteria (all existed before 2015):
    - Sector SPDRs: Rotate into strongest sectors
    - Industry ETFs: More granular sector exposure
    - Leverage ETFs excluded (decay issues)
    """

    MOMENTUM_LOOKBACK = 63  # ~3 months
    TOP_N = 5
    MIN_MOMENTUM = 5  # Lower threshold for ETFs (less volatile)

    def initialize(self):
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # SYSTEMATIC UNIVERSE: ETFs that existed before 2015
        # Selection criteria: Liquid, sector/industry exposure, no leverage
        self.universe_symbols = [
            # === SECTOR SPDRs (all since 1998) ===
            "XLK",  # Technology
            "XLF",  # Financials
            "XLV",  # Healthcare
            "XLE",  # Energy
            "XLY",  # Consumer Discretionary
            "XLP",  # Consumer Staples
            "XLI",  # Industrials
            "XLB",  # Materials
            "XLU",  # Utilities

            # === INDUSTRY ETFs (all pre-2015) ===
            "IBB",  # Biotech (2001)
            "XBI",  # Biotech Equal Weight (2006)
            "SMH",  # Semiconductors (2000)
            "XHB",  # Homebuilders (2006)
            "XRT",  # Retail (2006)
            "KRE",  # Regional Banks (2006)
            "XOP",  # Oil & Gas Exploration (2006)
            "XME",  # Metals & Mining (2006)
            "ITB",  # Home Construction (2006)

            # === BROAD MARKET (pre-2015) ===
            "QQQ",  # Nasdaq 100 (1999)
            "IWM",  # Russell 2000 Small Cap (2000)
            "IWF",  # Russell 1000 Growth (2000)
            "IWD",  # Russell 1000 Value (2000)
            "MDY",  # S&P MidCap 400 (1995)
            "IJR",  # S&P SmallCap 600 (2000)

            # === INTERNATIONAL (pre-2015) ===
            "EFA",  # EAFE Developed Markets (2001)
            "EEM",  # Emerging Markets (2003)
            "FXI",  # China Large Cap (2004)
            "EWJ",  # Japan (1996)
            "EWZ",  # Brazil (2000)

            # === FACTOR ETFs (pre-2015) ===
            "MTUM", # Momentum Factor (2013)
            "VTV",  # Value (2004)
            "VUG",  # Growth (2004)
        ]

        self.stocks = []
        for ticker in self.universe_symbols:
            try:
                equity = self.add_equity(ticker, Resolution.DAILY)
                equity.set_slippage_model(ConstantSlippageModel(0.0005))  # Tighter for ETFs
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
        """
        Returns exposure level based on regime:
        - Bull market (SPY > 200 SMA): 100%
        - Bear market (SPY < 200 SMA): 50%
        """
        if not self.spy_sma.is_ready:
            return 1.0

        if self.securities[self.spy].price > self.spy_sma.current.value:
            return 1.0
        else:
            return 0.5

    def get_drawdown_adjustment(self) -> float:
        """
        Reduce exposure when in drawdown > 15%
        """
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

        # Rank by momentum
        rankings = []
        for symbol in self.stocks:
            mom = self.calculate_momentum(symbol)
            if mom is not None and mom > self.MIN_MOMENTUM:
                rankings.append((symbol, mom))

        if len(rankings) < self.TOP_N:
            # Lower threshold for ETFs
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
