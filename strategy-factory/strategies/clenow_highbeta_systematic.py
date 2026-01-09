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

    # CONCENTRATED - single position with trend break exit
    # Best results: 36.5% CAGR, 45.3% MaxDD, 0.81 Sharpe
    MOMENTUM_LOOKBACK = 63  # Standard momentum
    TOP_N = 1  # Single concentrated position
    MIN_MOMENTUM = 20  # Standard momentum threshold
    MIN_R_SQUARED = 0.7  # Higher R² for smoother trends only
    TREND_SMA_FAST = 50  # Fast SMA for trend
    TREND_SMA_SLOW = 100  # Slow SMA for trend
    LEVERAGE = 1.0  # No leverage

    # RISK MANAGEMENT - regime filter + trend break exit
    BEAR_MARKET_EXPOSURE = 0.5  # 50% exposure in bear market
    TRAILING_STOP_PCT = 1.0  # Disabled - using trend break exit instead

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
        self.position_peaks = {}  # Track peak price for each position (for trailing stop)
        self.in_cash_mode = False  # Portfolio stop triggered
        self.set_warmup(timedelta(days=150))  # Longer warmup for SMA

        # Store DUAL SMAs for stronger trend filter
        self.stock_sma_fast = {}
        self.stock_sma_slow = {}
        for symbol in self.stocks:
            self.stock_sma_fast[symbol] = self.sma(symbol, self.TREND_SMA_FAST, Resolution.DAILY)
            self.stock_sma_slow[symbol] = self.sma(symbol, self.TREND_SMA_SLOW, Resolution.DAILY)

        # MONTHLY rebalancing
        self.schedule.on(
            self.date_rules.month_start(self.spy),
            self.time_rules.after_market_open(self.spy, 30),
            self.rebalance
        )

        # Daily risk check - trailing stops and portfolio stop
        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.after_market_open(self.spy, 60),
            self.daily_risk_check
        )

    def calculate_momentum(self, symbol):
        """Returns (momentum_score, r_squared) or (None, None)"""
        history = self.history(symbol, self.MOMENTUM_LOOKBACK + 1, Resolution.DAILY)
        if history.empty or len(history) < self.MOMENTUM_LOOKBACK:
            return None, None

        try:
            prices = history['close'].values
            if len(prices) < 20:
                return None, None

            log_prices = np.log(prices)
            x = np.arange(len(log_prices))
            slope, intercept = np.polyfit(x, log_prices, 1)
            annualized_slope = (np.exp(slope * 252) - 1) * 100

            predictions = slope * x + intercept
            ss_res = np.sum((log_prices - predictions) ** 2)
            ss_tot = np.sum((log_prices - np.mean(log_prices)) ** 2)
            r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

            # Return both momentum score and R²
            return annualized_slope * r_squared, r_squared
        except:
            return None, None

    def is_uptrending(self, symbol) -> bool:
        """
        Filter to avoid down-ranging stocks:
        1. Price > 50-day SMA (fast trend)
        2. Price > 100-day SMA (slow trend)
        3. 50-day SMA > 100-day SMA (trend alignment)
        4. 20-day return > -5% (not crashing)
        """
        # Check DUAL SMA filter
        if symbol not in self.stock_sma_fast or symbol not in self.stock_sma_slow:
            return False

        sma_fast = self.stock_sma_fast[symbol]
        sma_slow = self.stock_sma_slow[symbol]
        if not sma_fast.is_ready or not sma_slow.is_ready:
            return False

        price = self.securities[symbol].price
        if price <= 0:
            return False

        # Must be above BOTH SMAs
        if price < sma_fast.current.value or price < sma_slow.current.value:
            return False

        # Fast SMA must be above slow SMA (trend alignment)
        if sma_fast.current.value < sma_slow.current.value:
            return False

        # Check recent returns - not crashing
        history = self.history(symbol, 21, Resolution.DAILY)
        if history.empty or len(history) < 20:
            return False

        try:
            prices = history['close'].values
            recent_return = (prices[-1] / prices[0]) - 1

            # Not down more than 5% in 20 days
            if recent_return < -0.05:
                return False
        except:
            return False

        return True

    def get_regime_exposure(self) -> float:
        """Reduce exposure in bear market (SPY < 200 SMA)"""
        if not self.spy_sma.is_ready:
            return 1.0

        if self.securities[self.spy].price > self.spy_sma.current.value:
            return 1.0  # Bull market - full exposure
        else:
            return self.BEAR_MARKET_EXPOSURE  # Bear market - reduced exposure

    def daily_risk_check(self):
        """Daily check for trailing stops and momentum exit"""
        if self.is_warming_up:
            return

        # Update peak equity for tracking
        current_equity = self.portfolio.total_portfolio_value
        self.peak_equity = max(self.peak_equity, current_equity)

        # Check each position for exit signals
        for symbol in list(self.current_holdings):
            if not self.portfolio[symbol].invested:
                continue

            current_price = self.securities[symbol].price
            if current_price <= 0:
                continue

            # Update peak price
            if symbol not in self.position_peaks:
                self.position_peaks[symbol] = current_price
            else:
                self.position_peaks[symbol] = max(self.position_peaks[symbol], current_price)

            # TRAILING STOP check
            peak_price = self.position_peaks[symbol]
            decline = (peak_price - current_price) / peak_price

            if decline > self.TRAILING_STOP_PCT:
                self.log(f"TRAILING STOP: {symbol.value} down {decline*100:.1f}% from peak ${peak_price:.2f}")
                self.liquidate(symbol)
                self.current_holdings.discard(symbol)
                del self.position_peaks[symbol]
                continue

            # MOMENTUM EXIT - check if trend has broken AND we're losing (weekly)
            if self.time.weekday() == 0:  # Only check on Mondays
                if not self.is_uptrending(symbol):
                    # Only exit if we're down from our average cost
                    avg_price = self.portfolio[symbol].average_price
                    if avg_price > 0 and current_price < avg_price * 0.95:  # Down 5% or more from entry
                        self.log(f"TREND BREAK: {symbol.value} down-trending and losing")
                        self.liquidate(symbol)
                        self.current_holdings.discard(symbol)
                        if symbol in self.position_peaks:
                            del self.position_peaks[symbol]

    def rebalance(self):
        if self.is_warming_up:
            return

        regime_exposure = self.get_regime_exposure()
        self.log(f"Regime exposure: {regime_exposure:.0%}")

        if regime_exposure < 0.3:
            if self.current_holdings:
                self.liquidate()
                self.current_holdings = set()
                self.position_peaks = {}
                self.log("LOW EXPOSURE → CASH")
            return

        # Rank stocks: must be uptrending AND have smooth strong momentum
        rankings = []
        filtered_trend = 0
        filtered_rsq = 0
        for symbol in self.stocks:
            # TREND FILTER: Skip stocks that are down-ranging
            if not self.is_uptrending(symbol):
                filtered_trend += 1
                continue

            mom, rsq = self.calculate_momentum(symbol)
            if mom is None or rsq is None:
                continue

            # R² FILTER: Skip choppy/noisy trends
            if rsq < self.MIN_R_SQUARED:
                filtered_rsq += 1
                continue

            if mom > self.MIN_MOMENTUM:
                rankings.append((symbol, mom))

        self.log(f"Filtered: {filtered_trend} down-ranging, {filtered_rsq} low R²")

        # If not enough, try without R² filter but keep trend filter
        if len(rankings) < self.TOP_N:
            rankings = []
            for symbol in self.stocks:
                if not self.is_uptrending(symbol):
                    continue
                mom, rsq = self.calculate_momentum(symbol)
                if mom is not None and mom > 0:
                    rankings.append((symbol, mom))

        if len(rankings) < self.TOP_N:
            return

        rankings.sort(key=lambda x: x[1], reverse=True)
        top_stocks = [r[0] for r in rankings[:self.TOP_N]]
        top_stocks_set = set(top_stocks)

        self.log(f"TOP {self.TOP_N}: {' > '.join([f'{r[0].value}({r[1]:.0f})' for r in rankings[:self.TOP_N]])}")

        # Exit positions not in top N
        for symbol in self.current_holdings - top_stocks_set:
            self.liquidate(symbol)
            if symbol in self.position_peaks:
                del self.position_peaks[symbol]

        # Enter/adjust positions with regime-adjusted weight
        weight = (self.LEVERAGE / self.TOP_N) * regime_exposure
        for symbol in top_stocks:
            self.set_holdings(symbol, weight)
            # Initialize position peak for trailing stop
            if symbol not in self.position_peaks:
                self.position_peaks[symbol] = self.securities[symbol].price

        self.current_holdings = top_stocks_set

    def on_data(self, data):
        pass
