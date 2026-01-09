"""
Clenow v23: Momentum Burst

Hypothesis: Capture short-term momentum bursts with faster signals
- Short lookback (21 days) for quick reaction
- Strong 1-month returns > 10%
- Higher concentration (3 positions)
- Bi-weekly rebalancing
- Very high R² requirement (0.75) for clean trends
"""

from AlgorithmImports import *
from datetime import timedelta
import numpy as np


class ClenowMomentumBurst(QCAlgorithm):

    SHORT_LOOKBACK = 21  # 1 month for burst detection
    MED_LOOKBACK = 42    # 2 months for trend confirmation
    TOP_N = 3  # Very concentrated
    MIN_SHORT_MOM = 50  # 50%+ annualized short-term momentum
    MIN_MED_MOM = 30    # 30%+ medium-term
    MIN_R_SQUARED = 0.70

    LEVERAGE = 1.0
    MAX_PER_SECTOR = 2
    ATR_TRAILING_MULT = 2.0  # Tighter stop for faster exit
    BEAR_EXPOSURE = 0.2

    ATR_PERIOD = 14
    USE_ATR_TRAILING = True
    MAX_POSITION_SIZE = 0.45

    SECTOR_MAP = {
        "AAPL": "Tech", "MSFT": "Tech", "GOOGL": "Tech", "NVDA": "Semi",
        "META": "Internet", "NFLX": "Internet", "AMZN": "Consumer",
        "TSLA": "Auto", "AMD": "Semi", "AVGO": "Semi", "MU": "Semi",
        "CRM": "Tech", "ADBE": "Tech",
        "REGN": "Biotech", "VRTX": "Biotech", "ISRG": "Biotech",
        "HD": "Retail", "LOW": "Retail",
        "GS": "Finance", "MS": "Finance",
        "OXY": "Energy", "DVN": "Energy", "EOG": "Energy",
    }

    def initialize(self):
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Focused on highest-beta names
        self.universe_symbols = [
            "AAPL", "MSFT", "GOOGL", "NVDA", "META", "NFLX", "AMZN", "TSLA",
            "AMD", "AVGO", "MU", "CRM", "ADBE", "QCOM", "AMAT", "LRCX",
            "REGN", "VRTX", "ISRG",
            "HD", "LOW", "TJX",
            "GS", "MS",
            "OXY", "DVN", "EOG", "COP",
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
        self.spy_sma_50 = self.sma(self.spy, 50, Resolution.DAILY)

        self.stock_sma = {}
        self.stock_atr = {}

        for symbol in self.stocks:
            self.stock_sma[symbol] = self.sma(symbol, 20, Resolution.DAILY)
            atr = AverageTrueRange(self.ATR_PERIOD)
            self.register_indicator(symbol, atr, Resolution.DAILY)
            self.stock_atr[symbol] = atr

        self.current_holdings = set()
        self.position_peaks = {}
        self.rebalance_week = 0
        self.set_warmup(timedelta(days=100))

        # Bi-weekly
        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.after_market_open(self.spy, 30),
            self.check_rebalance
        )

        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.after_market_open(self.spy, 60),
            self.daily_risk_check
        )

    def check_rebalance(self):
        self.rebalance_week += 1
        if self.rebalance_week % 2 == 0:
            self.rebalance()

    def get_sector(self, symbol):
        return self.SECTOR_MAP.get(symbol.value, "Other")

    def calculate_momentum(self, symbol, lookback):
        """Calculate momentum over specified lookback"""
        history = self.history(symbol, lookback + 1, Resolution.DAILY)
        if history.empty or len(history) < lookback:
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
        spy_price = self.securities[self.spy].price
        # More aggressive regime filter
        if spy_price > self.spy_sma.current.value:
            if self.spy_sma_50.is_ready and spy_price > self.spy_sma_50.current.value:
                return 1.0  # Strong bull
            return 0.8  # Moderate bull
        return self.BEAR_EXPOSURE

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

            # Tight ATR stop
            if self.USE_ATR_TRAILING and symbol in self.stock_atr:
                atr = self.stock_atr[symbol]
                if atr.is_ready:
                    stop = self.position_peaks[symbol] - (self.ATR_TRAILING_MULT * atr.current.value)
                    if price < stop:
                        self.liquidate(symbol)
                        self.current_holdings.discard(symbol)
                        del self.position_peaks[symbol]
                        continue

            # Quick trend break exit
            if not self.is_uptrending(symbol):
                avg = self.portfolio[symbol].average_price
                if avg > 0 and price < avg * 0.97:
                    self.liquidate(symbol)
                    self.current_holdings.discard(symbol)
                    if symbol in self.position_peaks:
                        del self.position_peaks[symbol]

    def rebalance(self):
        if self.is_warming_up:
            return

        regime = self.get_regime_exposure()
        if regime < 0.15:
            self.liquidate()
            self.current_holdings = set()
            self.position_peaks = {}
            return

        # MOMENTUM BURST FILTER
        candidates = []
        for symbol in self.stocks:
            if not self.is_uptrending(symbol):
                continue

            # Short-term momentum (burst detection)
            short_mom, short_rsq = self.calculate_momentum(symbol, self.SHORT_LOOKBACK)
            if short_mom is None or short_rsq is None:
                continue
            if short_mom < self.MIN_SHORT_MOM or short_rsq < self.MIN_R_SQUARED:
                continue

            # Medium-term confirmation
            med_mom, med_rsq = self.calculate_momentum(symbol, self.MED_LOOKBACK)
            if med_mom is None or med_mom < self.MIN_MED_MOM:
                continue

            # Score: Short momentum * medium confirmation
            score = short_mom * (1 + med_mom / 100) * short_rsq
            candidates.append((symbol, score))

        # Fallback
        if len(candidates) < self.TOP_N:
            for symbol in self.stocks:
                if not self.is_uptrending(symbol):
                    continue
                short_mom, rsq = self.calculate_momentum(symbol, self.SHORT_LOOKBACK)
                if short_mom is not None and short_mom > 30:
                    if not any(s == symbol for s, _ in candidates):
                        candidates.append((symbol, short_mom * (rsq or 0.5)))

        if len(candidates) < self.TOP_N:
            return

        candidates.sort(key=lambda x: x[1], reverse=True)
        top = self.apply_sector_limits(candidates)
        if len(top) < self.TOP_N:
            top = candidates[:self.TOP_N]

        top_set = set(s for s, _ in top)

        self.log(f"BURST TOP: {', '.join([f'{s.value}' for s, _ in top])}")

        for symbol in self.current_holdings - top_set:
            self.liquidate(symbol)
            if symbol in self.position_peaks:
                del self.position_peaks[symbol]

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
