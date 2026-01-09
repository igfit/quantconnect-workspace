"""
Clenow v36: Hybrid - Dual Momentum on Hyper-Beta Universe

Combining:
- v22's dual momentum (absolute + relative) for better entry quality
- v29's hyper-beta universe for higher returns

Goal: Get close to 30% CAGR with better DD control than v29
"""

from AlgorithmImports import *
from datetime import timedelta
import numpy as np


class ClenowHybrid(QCAlgorithm):

    MOMENTUM_LOOKBACK = 63
    TOP_N = 3  # Slightly more diversified
    MIN_MOMENTUM = 45  # High threshold
    MIN_REL_STRENGTH = 12  # Must beat SPY
    MIN_R_SQUARED = 0.55

    LEVERAGE = 1.0
    ATR_TRAILING_MULT = 2.3  # Moderate tightness
    BEAR_EXPOSURE = 0.0

    ATR_PERIOD = 20
    USE_ATR_TRAILING = True
    MAX_POSITION_SIZE = 0.40

    def initialize(self):
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Hyper-beta universe from v29
        self.universe_symbols = [
            "NVDA", "TSLA", "AMD", "META", "NFLX",
            "MU", "AVGO", "AMAT", "LRCX",
            "CRM", "ADBE", "NOW",
            "COIN", "SQ", "SHOP",
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
        self.rebalance_week = 0
        self.set_warmup(timedelta(days=150))

        # Bi-weekly rebalancing (from v22)
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

    def calculate_absolute_momentum(self, symbol):
        """Clenow momentum: annualized slope * R²"""
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

    def calculate_relative_strength(self, symbol):
        """Relative strength vs SPY (from v22)"""
        stock_hist = self.history(symbol, self.MOMENTUM_LOOKBACK + 1, Resolution.DAILY)
        spy_hist = self.history(self.spy, self.MOMENTUM_LOOKBACK + 1, Resolution.DAILY)

        if stock_hist.empty or spy_hist.empty:
            return None
        if len(stock_hist) < self.MOMENTUM_LOOKBACK:
            return None

        try:
            stock_return = (stock_hist['close'].values[-1] / stock_hist['close'].values[0]) - 1
            spy_return = (spy_hist['close'].values[-1] / spy_hist['close'].values[0]) - 1
            rel_strength = (stock_return - spy_return) * (252 / self.MOMENTUM_LOOKBACK) * 100
            return rel_strength
        except:
            return None

    def is_uptrending(self, symbol) -> bool:
        """Double SMA filter (from v22)"""
        if symbol not in self.stock_sma_fast or symbol not in self.stock_sma_slow:
            return False
        sma_fast = self.stock_sma_fast[symbol]
        sma_slow = self.stock_sma_slow[symbol]
        if not sma_fast.is_ready or not sma_slow.is_ready:
            return False
        price = self.securities[symbol].price
        if price <= 0:
            return False
        # Price > fast SMA, fast > slow
        if price < sma_fast.current.value:
            return False
        if sma_fast.current.value < sma_slow.current.value:
            return False
        return True

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
        if regime < 0.1:
            self.liquidate()
            self.current_holdings = set()
            self.position_peaks = {}
            return

        # DUAL MOMENTUM FILTER (from v22)
        candidates = []
        for symbol in self.stocks:
            if not self.is_uptrending(symbol):
                continue

            # Absolute momentum
            abs_mom, rsq = self.calculate_absolute_momentum(symbol)
            if abs_mom is None or rsq is None:
                continue
            if abs_mom < self.MIN_MOMENTUM or rsq < self.MIN_R_SQUARED:
                continue

            # Relative momentum
            rel_str = self.calculate_relative_strength(symbol)
            if rel_str is None or rel_str < self.MIN_REL_STRENGTH:
                continue

            # Combined score: absolute * relative * R²
            score = abs_mom * (1 + rel_str / 100) * rsq
            candidates.append((symbol, score))

        # Fallback
        if len(candidates) < self.TOP_N:
            for symbol in self.stocks:
                if not self.is_uptrending(symbol):
                    continue
                abs_mom, rsq = self.calculate_absolute_momentum(symbol)
                if abs_mom is not None and abs_mom > 25:
                    if not any(s == symbol for s, _ in candidates):
                        candidates.append((symbol, abs_mom * (rsq or 0.5)))

        if len(candidates) < self.TOP_N:
            return

        candidates.sort(key=lambda x: x[1], reverse=True)
        top = candidates[:self.TOP_N]
        top_set = set(s for s, _ in top)

        self.log(f"HYBRID: {', '.join([f'{s.value}' for s, _ in top])}")

        for symbol in self.current_holdings - top_set:
            self.liquidate(symbol)
            if symbol in self.position_peaks:
                del self.position_peaks[symbol]

        # Squared score weighting (from v22)
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
