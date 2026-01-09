"""
Clenow v21: Relative Strength + Breakout

Hypothesis: Combine relative strength (vs SPY) with breakout for higher quality entries
- Stock must be outperforming SPY (relative strength > 0)
- Stock must be near 52-week high (breakout confirmation)
- Monthly rebalancing (less churn)
- 5 positions
"""

from AlgorithmImports import *
from datetime import timedelta
import numpy as np


class ClenowRelStrengthBreakout(QCAlgorithm):

    MOMENTUM_LOOKBACK = 63
    TOP_N = 5
    MIN_REL_STRENGTH = 10  # Must outperform SPY by 10%+ annualized
    HIGH_THRESHOLD = 0.95  # Within 5% of 52-week high

    LEVERAGE = 1.0
    MAX_PER_SECTOR = 2
    ATR_TRAILING_MULT = 2.5
    BEAR_EXPOSURE = 0.3

    ATR_PERIOD = 20
    USE_ATR_TRAILING = True
    MAX_POSITION_SIZE = 0.35

    SECTOR_MAP = {
        "AAPL": "Tech", "MSFT": "Tech", "GOOGL": "Tech", "NVDA": "Semi",
        "META": "Internet", "NFLX": "Internet", "AMZN": "Consumer",
        "TSLA": "Auto", "AMD": "Semi", "AVGO": "Semi", "MU": "Semi",
        "CRM": "Tech", "ADBE": "Tech", "INTC": "Semi", "CSCO": "Tech",
        "QCOM": "Semi", "TXN": "Semi", "AMAT": "Semi", "LRCX": "Semi",
        "GILD": "Biotech", "BIIB": "Biotech", "AMGN": "Biotech",
        "REGN": "Biotech", "VRTX": "Biotech", "ISRG": "Biotech",
        "HD": "Retail", "LOW": "Retail", "TJX": "Retail",
        "GS": "Finance", "MS": "Finance", "JPM": "Finance",
        "OXY": "Energy", "DVN": "Energy", "EOG": "Energy", "COP": "Energy",
        "EA": "Gaming", "ATVI": "Gaming",
    }

    def initialize(self):
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.universe_symbols = [
            "AAPL", "MSFT", "GOOGL", "NVDA", "META", "NFLX", "AMZN", "TSLA",
            "AMD", "AVGO", "MU", "CRM", "ADBE", "INTC", "CSCO", "QCOM",
            "TXN", "AMAT", "LRCX", "KLAC", "MCHP", "NXPI", "SWKS",
            "GILD", "BIIB", "AMGN", "REGN", "VRTX", "ISRG",
            "HD", "LOW", "TJX", "ROST", "ULTA",
            "GS", "MS", "JPM", "SCHW",
            "OXY", "DVN", "EOG", "COP",
            "EA", "ATVI", "TTWO",
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

        self.stock_sma = {}
        self.stock_atr = {}
        self.stock_max = {}  # Rolling max for breakout

        for symbol in self.stocks:
            self.stock_sma[symbol] = self.sma(symbol, 50, Resolution.DAILY)
            atr = AverageTrueRange(self.ATR_PERIOD)
            self.register_indicator(symbol, atr, Resolution.DAILY)
            self.stock_atr[symbol] = atr
            self.stock_max[symbol] = self.max(symbol, 252, Resolution.DAILY)

        self.current_holdings = set()
        self.position_peaks = {}
        self.set_warmup(timedelta(days=260))

        # Monthly rebalancing
        self.schedule.on(
            self.date_rules.month_start(self.spy),
            self.time_rules.after_market_open(self.spy, 30),
            self.rebalance
        )

        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.after_market_open(self.spy, 60),
            self.daily_risk_check
        )

    def get_sector(self, symbol):
        return self.SECTOR_MAP.get(symbol.value, "Other")

    def calculate_relative_strength(self, symbol):
        """Calculate relative strength vs SPY (outperformance)"""
        stock_hist = self.history(symbol, self.MOMENTUM_LOOKBACK + 1, Resolution.DAILY)
        spy_hist = self.history(self.spy, self.MOMENTUM_LOOKBACK + 1, Resolution.DAILY)

        if stock_hist.empty or spy_hist.empty:
            return None
        if len(stock_hist) < self.MOMENTUM_LOOKBACK or len(spy_hist) < self.MOMENTUM_LOOKBACK:
            return None

        try:
            stock_prices = stock_hist['close'].values
            spy_prices = spy_hist['close'].values

            # Calculate returns
            stock_return = (stock_prices[-1] / stock_prices[0]) - 1
            spy_return = (spy_prices[-1] / spy_prices[0]) - 1

            # Relative strength = stock return - SPY return, annualized
            rel_strength = (stock_return - spy_return) * (252 / self.MOMENTUM_LOOKBACK) * 100
            return rel_strength
        except:
            return None

    def calculate_momentum(self, symbol):
        """Calculate Clenow momentum for ranking"""
        history = self.history(symbol, self.MOMENTUM_LOOKBACK + 1, Resolution.DAILY)
        if history.empty or len(history) < self.MOMENTUM_LOOKBACK:
            return None, None
        try:
            prices = history['close'].values
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

    def is_near_high(self, symbol) -> bool:
        """Check if stock is within HIGH_THRESHOLD of 52-week high"""
        if symbol not in self.stock_max:
            return False
        max_ind = self.stock_max[symbol]
        if not max_ind.is_ready:
            return False
        price = self.securities[symbol].price
        high_52 = max_ind.current.value
        if high_52 <= 0:
            return False
        return price >= high_52 * self.HIGH_THRESHOLD

    def is_uptrending(self, symbol) -> bool:
        if symbol not in self.stock_sma:
            return False
        sma = self.stock_sma[symbol]
        if not sma.is_ready:
            return False
        price = self.securities[symbol].price
        return price > sma.current.value

    def apply_sector_limits(self, rankings):
        sector_counts = {}
        filtered = []
        for symbol, score in rankings:
            sector = self.get_sector(symbol)
            if sector_counts.get(sector, 0) < self.MAX_PER_SECTOR:
                filtered.append((symbol, score))
                sector_counts[sector] = sector_counts.get(sector, 0) + 1
                if len(filtered) >= self.TOP_N:
                    break
        return filtered

    def get_regime_exposure(self) -> float:
        if not self.spy_sma.is_ready:
            return 1.0
        return 1.0 if self.securities[self.spy].price > self.spy_sma.current.value else self.BEAR_EXPOSURE

    def daily_risk_check(self):
        if self.is_warming_up:
            return
        for symbol in list(self.current_holdings):
            if not self.portfolio[symbol].invested:
                continue
            price = self.securities[symbol].price
            if price <= 0:
                continue
            if symbol not in self.position_peaks:
                self.position_peaks[symbol] = price
            else:
                self.position_peaks[symbol] = max(self.position_peaks[symbol], price)

            # ATR trailing stop
            if self.USE_ATR_TRAILING and symbol in self.stock_atr:
                atr = self.stock_atr[symbol]
                if atr.is_ready:
                    stop = self.position_peaks[symbol] - (self.ATR_TRAILING_MULT * atr.current.value)
                    if price < stop:
                        self.liquidate(symbol)
                        self.current_holdings.discard(symbol)
                        del self.position_peaks[symbol]
                        continue

            # Trend break exit
            if not self.is_uptrending(symbol):
                avg = self.portfolio[symbol].average_price
                if avg > 0 and price < avg * 0.95:
                    self.liquidate(symbol)
                    self.current_holdings.discard(symbol)
                    if symbol in self.position_peaks:
                        del self.position_peaks[symbol]

    def rebalance(self):
        if self.is_warming_up:
            return

        regime = self.get_regime_exposure()
        if regime < 0.2:
            self.liquidate()
            self.current_holdings = set()
            self.position_peaks = {}
            return

        # Build candidates with relative strength + breakout filter
        candidates = []
        for symbol in self.stocks:
            # Must be uptrending
            if not self.is_uptrending(symbol):
                continue

            # Must be near 52-week high (breakout)
            if not self.is_near_high(symbol):
                continue

            # Calculate relative strength
            rel_str = self.calculate_relative_strength(symbol)
            if rel_str is None or rel_str < self.MIN_REL_STRENGTH:
                continue

            # Get momentum for ranking
            mom, rsq = self.calculate_momentum(symbol)
            if mom is None or rsq is None:
                continue

            # Score = relative strength * momentum * R²
            score = rel_str * mom * rsq / 100
            candidates.append((symbol, score))

        # Fallback if not enough
        if len(candidates) < self.TOP_N:
            for symbol in self.stocks:
                if not self.is_uptrending(symbol):
                    continue
                mom, rsq = self.calculate_momentum(symbol)
                if mom is not None and mom > 0:
                    if not any(s == symbol for s, _ in candidates):
                        candidates.append((symbol, mom * (rsq or 0.5)))

        if len(candidates) < self.TOP_N:
            return

        candidates.sort(key=lambda x: x[1], reverse=True)
        top = self.apply_sector_limits(candidates)
        if len(top) < self.TOP_N:
            top = candidates[:self.TOP_N]

        top_set = set(s for s, _ in top)

        # Log selections
        self.log(f"TOP: {', '.join([f'{s.value}' for s, _ in top])}")

        # Exit positions not in top
        for symbol in self.current_holdings - top_set:
            self.liquidate(symbol)
            if symbol in self.position_peaks:
                del self.position_peaks[symbol]

        # Calculate weights
        weights = [(s, score ** 2) for s, score in top]
        total = sum(w for _, w in weights) or 1

        for symbol, w in weights:
            alloc = (w / total) * self.LEVERAGE * regime
            alloc = min(alloc, self.MAX_POSITION_SIZE)
            self.set_holdings(symbol, alloc)
            if symbol not in self.position_peaks:
                self.position_peaks[symbol] = self.securities[symbol].price

        self.current_holdings = top_set

    def on_data(self, data):
        pass
