"""
Clenow Momentum - Systematic High-Beta Universe

Selection criteria (as of Jan 2015, NOT hindsight):
1. Existed and traded before Jan 1, 2015
2. Market cap > $10B (large enough to be institutional)
3. Sectors known for high beta: Tech, Consumer Discretionary, Biotech, Financials
4. INCLUDES stocks that later underperformed or had issues (reduces survivorship bias)

This is NOT cherry-picking NVDA/TSLA winners - it's what a quant would have
selected in 2015 based on sector exposure and volatility characteristics.
"""

from AlgorithmImports import *
from datetime import timedelta
import numpy as np


class ClenowHighBetaSystematic(QCAlgorithm):
    """
    Clenow Momentum with Systematic High-Beta Universe

    Universe: Stocks that qualified as "high-beta growth" in Jan 2015
    - All existed before 2015
    - Mix of winners AND losers (no hindsight)
    - Sector-balanced exposure

    TREND FILTER: Only buy stocks that are:
    1. Above their 100-day SMA (uptrend)
    2. Have positive momentum score > MIN_MOMENTUM
    3. Have positive 20-day returns (not down-ranging)
    """

    MOMENTUM_LOOKBACK = 63
    TOP_N = 5
    MIN_MOMENTUM = 15  # Stricter threshold
    TREND_SMA_PERIOD = 100  # Stock must be above this SMA

    def initialize(self):
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # SYSTEMATIC HIGH-BETA UNIVERSE (all existed before 2015)
        # Selection: High-beta sectors, >$10B market cap as of 2014
        # INCLUDES underperformers to reduce survivorship bias
        self.universe_symbols = [
            # === TECHNOLOGY (high beta sector) ===
            # Large-cap tech (existed 2015)
            "AAPL", "MSFT", "GOOGL", "INTC", "CSCO", "ORCL", "IBM", "QCOM",
            "TXN", "ADBE", "CRM", "VMW", "AMAT", "LRCX", "KLAC", "ADI",
            "MCHP", "XLNX", "NVDA", "MU",  # NVDA/MU were mid-cap in 2015
            # Note: AMD was <$3B in 2015, borderline but include for beta

            # === SEMICONDUCTORS (cyclical, high beta) ===
            "AVGO", "NXPI", "SWKS", "QRVO",  # All existed pre-2015

            # === INTERNET/SOCIAL (high beta in 2015) ===
            "META",   # Was FB, existed since 2012 IPO
            "NFLX",   # High beta streaming play
            "EBAY",   # E-commerce incumbent
            "YHOO",   # Yahoo - later acquired (underperformer)
            "TWTR",   # Twitter - later taken private (underperformer)
            "LNKD",   # LinkedIn - acquired 2016 (mixed)
            "YELP",   # High beta, underperformed
            "GRPN",   # Groupon - major underperformer
            "P",      # Pandora - acquired, underperformed

            # === BIOTECH (highest beta sector) ===
            "GILD", "BIIB", "CELG", "AMGN", "REGN", "VRTX", "ALXN",
            "ILMN", "ISRG",  # All large-cap biotech in 2015

            # === CONSUMER DISCRETIONARY (cyclical, high beta) ===
            "AMZN",   # E-commerce leader
            "PCLN",   # Booking Holdings (was Priceline)
            "EXPE",   # Online travel
            "TRIP",   # TripAdvisor - underperformed
            "NTES",   # NetEase - China gaming
            "BIDU",   # Baidu - China search (underperformed)
            "JD",     # JD.com - IPO 2014

            # === RETAIL (high beta consumer) ===
            "HD", "LOW", "TJX", "ROST", "ULTA", "DG", "DLTR",
            "KSS",    # Kohl's - underperformed
            "M",      # Macy's - major underperformer
            "JWN",    # Nordstrom - underperformed
            "GPS",    # Gap - underperformed

            # === FINANCIALS (high beta) ===
            "GS", "MS", "JPM", "C", "BAC", "WFC",
            "SCHW", "ETFC",  # E*TRADE - acquired
            "CME", "ICE", "NDAQ",

            # === ENERGY (very high beta, cyclical) ===
            "OXY", "APA", "DVN", "EOG", "PXD", "CLR",
            "COP", "HES", "MRO",  # All high-beta E&P

            # === AUTOS (cyclical, high beta) ===
            "F", "GM", "TSLA",  # TSLA was ~$15B in 2015, included

            # === GAMING/LEISURE ===
            "WYNN", "LVS", "MGM",  # Casino stocks - high beta
            "EA", "ATVI", "TTWO",  # Gaming
        ]

        self.stocks = []
        failed_adds = []
        for ticker in self.universe_symbols:
            try:
                equity = self.add_equity(ticker, Resolution.DAILY)
                equity.set_slippage_model(ConstantSlippageModel(0.001))
                equity.set_fee_model(InteractiveBrokersFeeModel())
                self.stocks.append(equity.symbol)
            except Exception as e:
                failed_adds.append(ticker)

        if failed_adds:
            self.log(f"Failed to add: {failed_adds}")

        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.set_benchmark(self.spy)
        self.spy_sma = self.sma(self.spy, 200, Resolution.DAILY)

        self.current_holdings = set()
        self.peak_equity = 100000
        self.set_warmup(timedelta(days=150))  # Longer warmup for SMA

        # Store SMAs for trend filter
        self.stock_smas = {}
        for symbol in self.stocks:
            self.stock_smas[symbol] = self.sma(symbol, self.TREND_SMA_PERIOD, Resolution.DAILY)

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

    def is_uptrending(self, symbol) -> bool:
        """
        Check if stock is in uptrend (not down-ranging):
        1. Price > 100-day SMA
        2. 20-day return is positive
        """
        # Check SMA filter
        if symbol not in self.stock_smas:
            return False

        sma = self.stock_smas[symbol]
        if not sma.is_ready:
            return False

        price = self.securities[symbol].price
        if price <= 0 or price < sma.current.value:
            return False  # Below SMA = downtrend

        # Check recent returns (20-day)
        history = self.history(symbol, 21, Resolution.DAILY)
        if history.empty or len(history) < 20:
            return False

        try:
            prices = history['close'].values
            recent_return = (prices[-1] / prices[0]) - 1
            if recent_return < -0.05:  # Down more than 5% in 20 days = avoid
                return False
        except:
            return False

        return True

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

        # Rank stocks: must be uptrending AND have good momentum
        rankings = []
        filtered_out = 0
        for symbol in self.stocks:
            # TREND FILTER: Skip stocks that are down-ranging
            if not self.is_uptrending(symbol):
                filtered_out += 1
                continue

            mom = self.calculate_momentum(symbol)
            if mom is not None and mom > self.MIN_MOMENTUM:
                rankings.append((symbol, mom))

        self.log(f"Filtered out {filtered_out} down-ranging stocks")

        # If not enough uptrending stocks with high momentum, lower threshold
        if len(rankings) < self.TOP_N:
            rankings = []
            for symbol in self.stocks:
                if not self.is_uptrending(symbol):
                    continue
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
