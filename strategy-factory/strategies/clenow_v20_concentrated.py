"""
Clenow v20: Concentrated Weekly - 3 positions, weekly rebalancing

Hypothesis: More concentration + faster reaction = higher returns
- TOP_N = 3 (vs 5)
- Weekly rebalancing (vs monthly)
- Shorter momentum lookback (42 days vs 63)
- Tighter ATR stop (2.0x vs 2.5x)
"""

from AlgorithmImports import *
from datetime import timedelta
import numpy as np


class ClenowConcentratedWeekly(QCAlgorithm):

    MOMENTUM_LOOKBACK = 42  # Shorter for faster signals
    TOP_N = 3  # More concentrated
    MIN_MOMENTUM = 30  # Higher threshold
    MIN_R_SQUARED = 0.65

    LEVERAGE = 1.0  # No leverage
    MAX_PER_SECTOR = 2
    ATR_TRAILING_MULT = 2.0  # Tighter stop
    BEAR_EXPOSURE = 0.25

    USE_VOL_SCALING = True
    ATR_PERIOD = 14
    WEEKLY_TREND_CONFIRM = True
    USE_ACCELERATION = True
    ACCEL_LOOKBACK = 15
    USE_ATR_TRAILING = True
    MAX_POSITION_SIZE = 0.50

    SECTOR_MAP = {
        "AAPL": "Tech", "MSFT": "Tech", "GOOGL": "Tech", "NVDA": "Semi",
        "META": "Internet", "NFLX": "Internet", "AMZN": "Consumer",
        "TSLA": "Auto", "AMD": "Semi", "AVGO": "Semi", "MU": "Semi",
        "CRM": "Tech", "ADBE": "Tech", "NOW": "Tech", "SHOP": "Tech",
        "SQ": "Finance", "PYPL": "Finance", "COIN": "Finance",
        "MSTR": "Finance", "SMCI": "Tech",
    }

    def initialize(self):
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Focused high-momentum universe
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

        self.stock_sma_fast = {}
        self.stock_sma_slow = {}
        self.stock_atr = {}

        for symbol in self.stocks:
            self.stock_sma_fast[symbol] = self.sma(symbol, 20, Resolution.DAILY)
            self.stock_sma_slow[symbol] = self.sma(symbol, 50, Resolution.DAILY)
            atr = AverageTrueRange(self.ATR_PERIOD)
            self.register_indicator(symbol, atr, Resolution.DAILY)
            self.stock_atr[symbol] = atr

        self.current_holdings = set()
        self.position_peaks = {}
        self.set_warmup(timedelta(days=100))

        # WEEKLY rebalancing
        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
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

    def calculate_momentum(self, symbol):
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

    def get_momentum_acceleration(self, symbol):
        if not self.USE_ACCELERATION:
            return True
        current_mom, _ = self.calculate_momentum(symbol)
        if current_mom is None:
            return False
        history = self.history(symbol, self.MOMENTUM_LOOKBACK + self.ACCEL_LOOKBACK + 1, Resolution.DAILY)
        if history.empty or len(history) < self.MOMENTUM_LOOKBACK + self.ACCEL_LOOKBACK:
            return True
        try:
            old_prices = history['close'].values[:-self.ACCEL_LOOKBACK][-self.MOMENTUM_LOOKBACK:]
            log_prices = np.log(old_prices)
            x = np.arange(len(log_prices))
            slope, _ = np.polyfit(x, log_prices, 1)
            old_mom = (np.exp(slope * 252) - 1) * 100
            return current_mom > old_mom * 0.8  # Allow some slack
        except:
            return True

    def is_uptrending(self, symbol) -> bool:
        if symbol not in self.stock_sma_fast or symbol not in self.stock_sma_slow:
            return False
        sma_fast = self.stock_sma_fast[symbol]
        sma_slow = self.stock_sma_slow[symbol]
        if not sma_fast.is_ready or not sma_slow.is_ready:
            return False
        price = self.securities[symbol].price
        if price <= 0:
            return False
        if price < sma_fast.current.value:
            return False
        if sma_fast.current.value < sma_slow.current.value * 0.98:
            return False
        return True

    def get_volatility_weight(self, symbol):
        if not self.USE_VOL_SCALING or symbol not in self.stock_atr:
            return 1.0
        atr = self.stock_atr[symbol]
        if not atr.is_ready:
            return 1.0
        price = self.securities[symbol].price
        if price <= 0:
            return 1.0
        atr_pct = atr.current.value / price
        base_weight = 0.025 / max(atr_pct, 0.005)
        return max(0.6, min(1.5, base_weight))

    def apply_sector_limits(self, rankings):
        sector_counts = {}
        filtered = []
        for symbol, mom in rankings:
            sector = self.get_sector(symbol)
            if sector_counts.get(sector, 0) < self.MAX_PER_SECTOR:
                filtered.append((symbol, mom))
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
            if self.USE_ATR_TRAILING and symbol in self.stock_atr:
                atr = self.stock_atr[symbol]
                if atr.is_ready:
                    stop = self.position_peaks[symbol] - (self.ATR_TRAILING_MULT * atr.current.value)
                    if price < stop:
                        self.liquidate(symbol)
                        self.current_holdings.discard(symbol)
                        del self.position_peaks[symbol]
                        continue
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

        candidates = []
        for symbol in self.stocks:
            if not self.is_uptrending(symbol):
                continue
            if not self.get_momentum_acceleration(symbol):
                continue
            mom, rsq = self.calculate_momentum(symbol)
            if mom is None or rsq is None or rsq < self.MIN_R_SQUARED:
                continue
            if mom > self.MIN_MOMENTUM:
                candidates.append((symbol, mom))

        if len(candidates) < self.TOP_N:
            for symbol in self.stocks:
                if not self.is_uptrending(symbol):
                    continue
                mom, _ = self.calculate_momentum(symbol)
                if mom is not None and mom > 0 and (symbol, mom) not in candidates:
                    candidates.append((symbol, mom))

        if len(candidates) < self.TOP_N:
            return

        candidates.sort(key=lambda x: x[1], reverse=True)
        top = self.apply_sector_limits(candidates)
        if len(top) < self.TOP_N:
            top = candidates[:self.TOP_N]

        top_set = set(s for s, _ in top)
        for symbol in self.current_holdings - top_set:
            self.liquidate(symbol)
            if symbol in self.position_peaks:
                del self.position_peaks[symbol]

        weights = [(s, (m ** 2) * self.get_volatility_weight(s)) for s, m in top]
        total = sum(w for _, w in weights)
        for symbol, w in weights:
            alloc = (w / total) * self.LEVERAGE * regime
            alloc = min(alloc, self.MAX_POSITION_SIZE)
            self.set_holdings(symbol, alloc)
            if symbol not in self.position_peaks:
                self.position_peaks[symbol] = self.securities[symbol].price

        self.current_holdings = top_set

    def on_data(self, data):
        pass
