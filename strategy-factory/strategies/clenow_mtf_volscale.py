"""
Clenow Momentum v8: Multi-Timeframe with Volatility Scaling

FIRST PRINCIPLES APPROACH:
- DD comes from correlated selloffs + slow exits
- Returns limited by equal sizing across volatility levels

INNOVATIONS:
1. ATR-Based Position Sizing: Less capital in high-volatility names
2. Multi-Timeframe: Weekly trend confirms daily trend
3. Momentum Acceleration: Momentum must be IMPROVING
4. ATR Trailing Stop: Dynamic stop based on stock's own volatility
5. Sector Limits: Max 2 positions per sector
"""

from AlgorithmImports import *
from datetime import timedelta
import numpy as np


class ClenowMTFVolScale(QCAlgorithm):
    """
    v8: Multi-Timeframe Momentum with Volatility Scaling

    Target: 30% CAGR, <30% MaxDD
    """

    # CORE PARAMETERS
    MOMENTUM_LOOKBACK = 63  # ~3 months
    TOP_N = 5
    MIN_MOMENTUM = 20
    MIN_R_SQUARED = 0.60

    # VOLATILITY SCALING
    USE_VOL_SCALING = True  # Inverse ATR weighting
    ATR_PERIOD = 20

    # MULTI-TIMEFRAME
    WEEKLY_TREND_CONFIRM = True
    WEEKLY_EMA_PERIOD = 10  # 10-week EMA

    # MOMENTUM ACCELERATION
    USE_ACCELERATION = True
    ACCEL_LOOKBACK = 20  # Compare current mom to 20 days ago

    # EXIT RULES
    ATR_TRAILING_MULT = 3.0  # Exit if price drops 3x ATR from peak
    USE_ATR_TRAILING = True

    # SECTOR LIMITS
    MAX_PER_SECTOR = 2

    # LEVERAGE
    LEVERAGE = 1.0
    MAX_POSITION_SIZE = 0.40  # Tighter cap with vol scaling

    # Sector mapping for diversification
    SECTOR_MAP = {
        # Technology
        "AAPL": "Tech", "MSFT": "Tech", "GOOGL": "Tech", "INTC": "Tech",
        "CSCO": "Tech", "ORCL": "Tech", "IBM": "Tech", "QCOM": "Tech",
        "TXN": "Tech", "ADBE": "Tech", "CRM": "Tech", "VMW": "Tech",
        "AMAT": "Semi", "LRCX": "Semi", "KLAC": "Semi", "ADI": "Semi",
        "MCHP": "Semi", "XLNX": "Semi", "NVDA": "Semi", "MU": "Semi",
        "AVGO": "Semi", "NXPI": "Semi", "SWKS": "Semi", "QRVO": "Semi",
        # Internet
        "META": "Internet", "NFLX": "Internet", "EBAY": "Internet",
        "YHOO": "Internet", "TWTR": "Internet", "LNKD": "Internet",
        "YELP": "Internet", "GRPN": "Internet", "P": "Internet",
        # Biotech
        "GILD": "Biotech", "BIIB": "Biotech", "CELG": "Biotech",
        "AMGN": "Biotech", "REGN": "Biotech", "VRTX": "Biotech",
        "ALXN": "Biotech", "ILMN": "Biotech", "ISRG": "Biotech",
        # Consumer
        "AMZN": "Consumer", "PCLN": "Consumer", "EXPE": "Consumer",
        "TRIP": "Consumer", "NTES": "Consumer", "BIDU": "Consumer", "JD": "Consumer",
        # Retail
        "HD": "Retail", "LOW": "Retail", "TJX": "Retail", "ROST": "Retail",
        "ULTA": "Retail", "DG": "Retail", "DLTR": "Retail", "KSS": "Retail",
        "M": "Retail", "JWN": "Retail", "GPS": "Retail",
        # Financials
        "GS": "Finance", "MS": "Finance", "JPM": "Finance", "C": "Finance",
        "BAC": "Finance", "WFC": "Finance", "SCHW": "Finance", "ETFC": "Finance",
        "CME": "Finance", "ICE": "Finance", "NDAQ": "Finance",
        # Energy
        "OXY": "Energy", "APA": "Energy", "DVN": "Energy", "EOG": "Energy",
        "PXD": "Energy", "CLR": "Energy", "COP": "Energy", "HES": "Energy", "MRO": "Energy",
        # Autos
        "F": "Auto", "GM": "Auto", "TSLA": "Auto",
        # Gaming
        "WYNN": "Gaming", "LVS": "Gaming", "MGM": "Gaming",
        "EA": "Gaming", "ATVI": "Gaming", "TTWO": "Gaming",
    }

    def initialize(self):
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.universe_symbols = [
            # Technology
            "AAPL", "MSFT", "GOOGL", "INTC", "CSCO", "ORCL", "IBM", "QCOM",
            "TXN", "ADBE", "CRM", "VMW", "AMAT", "LRCX", "KLAC", "ADI",
            "MCHP", "XLNX", "NVDA", "MU",
            # Semiconductors
            "AVGO", "NXPI", "SWKS", "QRVO",
            # Internet
            "META", "NFLX", "EBAY", "YHOO", "TWTR", "LNKD", "YELP", "GRPN", "P",
            # Biotech
            "GILD", "BIIB", "CELG", "AMGN", "REGN", "VRTX", "ALXN", "ILMN", "ISRG",
            # Consumer
            "AMZN", "PCLN", "EXPE", "TRIP", "NTES", "BIDU", "JD",
            # Retail
            "HD", "LOW", "TJX", "ROST", "ULTA", "DG", "DLTR", "KSS", "M", "JWN", "GPS",
            # Financials
            "GS", "MS", "JPM", "C", "BAC", "WFC", "SCHW", "ETFC", "CME", "ICE", "NDAQ",
            # Energy
            "OXY", "APA", "DVN", "EOG", "PXD", "CLR", "COP", "HES", "MRO",
            # Autos
            "F", "GM", "TSLA",
            # Gaming
            "WYNN", "LVS", "MGM", "EA", "ATVI", "TTWO",
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

        # Daily trend indicators
        self.stock_sma_fast = {}
        self.stock_sma_slow = {}
        self.stock_atr = {}

        for symbol in self.stocks:
            self.stock_sma_fast[symbol] = self.sma(symbol, 50, Resolution.DAILY)
            self.stock_sma_slow[symbol] = self.sma(symbol, 100, Resolution.DAILY)
            # ATR indicator - create and register manually
            atr_indicator = AverageTrueRange(self.ATR_PERIOD)
            self.register_indicator(symbol, atr_indicator, Resolution.DAILY)
            self.stock_atr[symbol] = atr_indicator

        # Weekly consolidators for multi-timeframe
        self.weekly_ema = {}
        self.weekly_closes = {}

        for symbol in self.stocks:
            self.weekly_closes[symbol] = []
            # Manual weekly EMA calculation (simpler than consolidators)

        self.current_holdings = set()
        self.position_peaks = {}
        self.momentum_history = {}  # For acceleration calculation

        self.set_warmup(timedelta(days=150))

        # MONTHLY rebalancing
        self.schedule.on(
            self.date_rules.month_start(self.spy),
            self.time_rules.after_market_open(self.spy, 30),
            self.rebalance
        )

        # Daily risk check
        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.after_market_open(self.spy, 60),
            self.daily_risk_check
        )

    def get_sector(self, symbol):
        """Get sector for a symbol"""
        ticker = symbol.value
        return self.SECTOR_MAP.get(ticker, "Other")

    def calculate_momentum(self, symbol):
        """Calculate Clenow momentum (annualized slope * R²)"""
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

            return annualized_slope * r_squared, r_squared
        except:
            return None, None

    def get_momentum_acceleration(self, symbol):
        """
        Check if momentum is accelerating (improving)
        Returns True if current momentum > momentum from ACCEL_LOOKBACK days ago
        """
        if not self.USE_ACCELERATION:
            return True

        current_mom, _ = self.calculate_momentum(symbol)
        if current_mom is None:
            return False

        # Get historical momentum (from ACCEL_LOOKBACK days ago)
        # We approximate by using shorter lookback
        history = self.history(symbol, self.MOMENTUM_LOOKBACK + self.ACCEL_LOOKBACK + 1, Resolution.DAILY)
        if history.empty or len(history) < self.MOMENTUM_LOOKBACK + self.ACCEL_LOOKBACK:
            return True  # Not enough data, allow entry

        try:
            # Calculate momentum as of ACCEL_LOOKBACK days ago
            old_prices = history['close'].values[:-self.ACCEL_LOOKBACK]
            if len(old_prices) < self.MOMENTUM_LOOKBACK:
                return True

            old_prices = old_prices[-self.MOMENTUM_LOOKBACK:]
            log_prices = np.log(old_prices)
            x = np.arange(len(log_prices))
            slope, intercept = np.polyfit(x, log_prices, 1)
            old_mom = (np.exp(slope * 252) - 1) * 100

            predictions = slope * x + intercept
            ss_res = np.sum((log_prices - predictions) ** 2)
            ss_tot = np.sum((log_prices - np.mean(log_prices)) ** 2)
            old_rsq = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
            old_mom_adj = old_mom * old_rsq

            # Momentum is accelerating if current > old
            return current_mom > old_mom_adj
        except:
            return True

    def is_weekly_uptrend(self, symbol) -> bool:
        """
        Multi-timeframe: Check weekly trend
        Price must be above 10-week EMA approximation
        """
        if not self.WEEKLY_TREND_CONFIRM:
            return True

        # Get last 50 days (approx 10 weeks) to calculate weekly-like EMA
        history = self.history(symbol, 50, Resolution.DAILY)
        if history.empty or len(history) < 50:
            return True  # Not enough data, allow

        try:
            prices = history['close'].values
            # Simple approximation: 50-day EMA ≈ 10-week EMA
            ema = self.calculate_ema(prices, 50)
            current_price = self.securities[symbol].price
            return current_price > ema
        except:
            return True

    def calculate_ema(self, prices, period):
        """Calculate EMA of price array"""
        multiplier = 2 / (period + 1)
        ema = prices[0]
        for price in prices[1:]:
            ema = (price - ema) * multiplier + ema
        return ema

    def is_uptrending(self, symbol) -> bool:
        """Daily trend filter"""
        if symbol not in self.stock_sma_fast or symbol not in self.stock_sma_slow:
            return False

        sma_fast = self.stock_sma_fast[symbol]
        sma_slow = self.stock_sma_slow[symbol]
        if not sma_fast.is_ready or not sma_slow.is_ready:
            return False

        price = self.securities[symbol].price
        if price <= 0:
            return False

        # Price above both SMAs
        if price < sma_fast.current.value or price < sma_slow.current.value:
            return False

        # Fast SMA above slow SMA
        if sma_fast.current.value < sma_slow.current.value:
            return False

        # Check recent returns
        history = self.history(symbol, 21, Resolution.DAILY)
        if history.empty or len(history) < 20:
            return False

        try:
            prices = history['close'].values
            recent_return = (prices[-1] / prices[0]) - 1
            if recent_return < -0.05:
                return False
        except:
            return False

        return True

    def get_volatility_weight(self, symbol):
        """
        Calculate inverse volatility weight
        Lower ATR% = higher weight (safer stocks get more capital)
        """
        if not self.USE_VOL_SCALING:
            return 1.0

        if symbol not in self.stock_atr:
            return 1.0

        atr = self.stock_atr[symbol]
        if not atr.is_ready:
            return 1.0

        price = self.securities[symbol].price
        if price <= 0:
            return 1.0

        # ATR as percentage of price
        atr_pct = atr.current.value / price

        # Inverse weighting: lower volatility = higher weight
        # Normalize around 2% ATR (typical)
        # If ATR% = 2%, weight = 1.0
        # If ATR% = 4%, weight = 0.5
        # If ATR% = 1%, weight = 2.0 (but capped)
        vol_weight = 0.02 / max(atr_pct, 0.005)

        # Cap between 0.5 and 2.0
        return max(0.5, min(2.0, vol_weight))

    def apply_sector_limits(self, rankings):
        """
        Apply sector diversification limits
        Returns filtered list with max MAX_PER_SECTOR per sector
        """
        sector_counts = {}
        filtered = []

        for symbol, mom in rankings:
            sector = self.get_sector(symbol)
            current_count = sector_counts.get(sector, 0)

            if current_count < self.MAX_PER_SECTOR:
                filtered.append((symbol, mom))
                sector_counts[sector] = current_count + 1

                if len(filtered) >= self.TOP_N:
                    break

        return filtered

    def get_regime_exposure(self) -> float:
        """Market regime filter"""
        if not self.spy_sma.is_ready:
            return 1.0

        if self.securities[self.spy].price > self.spy_sma.current.value:
            return 1.0
        else:
            return 0.5  # Reduce exposure in bear market

    def daily_risk_check(self):
        """Daily check for ATR trailing stop"""
        if self.is_warming_up:
            return

        for symbol in list(self.current_holdings):
            if not self.portfolio[symbol].invested:
                continue

            current_price = self.securities[symbol].price
            if current_price <= 0:
                continue

            # Update peak
            if symbol not in self.position_peaks:
                self.position_peaks[symbol] = current_price
            else:
                self.position_peaks[symbol] = max(self.position_peaks[symbol], current_price)

            # ATR TRAILING STOP
            if self.USE_ATR_TRAILING and symbol in self.stock_atr:
                atr = self.stock_atr[symbol]
                if atr.is_ready:
                    peak_price = self.position_peaks[symbol]
                    atr_stop = peak_price - (self.ATR_TRAILING_MULT * atr.current.value)

                    if current_price < atr_stop:
                        pct_drop = (peak_price - current_price) / peak_price * 100
                        self.log(f"ATR STOP: {symbol.value} dropped {pct_drop:.1f}% from ${peak_price:.2f}")
                        self.liquidate(symbol)
                        self.current_holdings.discard(symbol)
                        del self.position_peaks[symbol]
                        continue

            # TREND BREAK + LOSS EXIT
            if not self.is_uptrending(symbol):
                avg_price = self.portfolio[symbol].average_price
                if avg_price > 0 and current_price < avg_price * 0.97:
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
            return

        # Build candidate list with all filters
        candidates = []
        stats = {"trend": 0, "weekly": 0, "accel": 0, "rsq": 0}

        for symbol in self.stocks:
            # Daily trend filter
            if not self.is_uptrending(symbol):
                stats["trend"] += 1
                continue

            # Weekly trend filter (multi-timeframe)
            if not self.is_weekly_uptrend(symbol):
                stats["weekly"] += 1
                continue

            # Momentum acceleration filter
            if not self.get_momentum_acceleration(symbol):
                stats["accel"] += 1
                continue

            mom, rsq = self.calculate_momentum(symbol)
            if mom is None or rsq is None:
                continue

            # R² filter
            if rsq < self.MIN_R_SQUARED:
                stats["rsq"] += 1
                continue

            if mom > self.MIN_MOMENTUM:
                candidates.append((symbol, mom))

        self.log(f"Filtered: {stats['trend']} trend, {stats['weekly']} weekly, {stats['accel']} accel, {stats['rsq']} R²")

        # Fallback: relax filters if not enough candidates
        if len(candidates) < self.TOP_N:
            candidates = []
            for symbol in self.stocks:
                if not self.is_uptrending(symbol):
                    continue
                mom, rsq = self.calculate_momentum(symbol)
                if mom is not None and mom > 0:
                    candidates.append((symbol, mom))

        if len(candidates) < self.TOP_N:
            self.log(f"Only {len(candidates)} candidates, need {self.TOP_N}")
            return

        # Sort by momentum
        candidates.sort(key=lambda x: x[1], reverse=True)

        # Apply sector limits
        top_stocks_with_mom = self.apply_sector_limits(candidates)

        if len(top_stocks_with_mom) < self.TOP_N:
            # Fallback to no sector limits
            top_stocks_with_mom = candidates[:self.TOP_N]

        top_stocks = [s for s, m in top_stocks_with_mom]
        top_stocks_set = set(top_stocks)

        sectors = [self.get_sector(s) for s in top_stocks]
        self.log(f"TOP {self.TOP_N}: {', '.join([f'{s.value}({self.get_sector(s)})' for s in top_stocks])}")

        # Exit positions not in top N
        for symbol in self.current_holdings - top_stocks_set:
            self.liquidate(symbol)
            if symbol in self.position_peaks:
                del self.position_peaks[symbol]

        # Calculate weights with volatility scaling
        weights = []
        for symbol, mom in top_stocks_with_mom:
            vol_weight = self.get_volatility_weight(symbol)
            # Combined weight: momentum² × volatility adjustment
            combined = (mom ** 2) * vol_weight
            weights.append((symbol, combined))

        total_weight = sum(w for _, w in weights)

        # Allocate positions
        for symbol, raw_weight in weights:
            weight = (raw_weight / total_weight) * self.LEVERAGE * regime_exposure
            weight = min(weight, self.MAX_POSITION_SIZE)
            self.set_holdings(symbol, weight)
            if symbol not in self.position_peaks:
                self.position_peaks[symbol] = self.securities[symbol].price

        self.current_holdings = top_stocks_set

    def on_data(self, data):
        pass
