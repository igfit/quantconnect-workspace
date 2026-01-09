"""
Clenow v24: Aggressive Momentum - No Sector Limits

Hypothesis: Remove sector limits, let best sectors dominate
- Very high momentum threshold (60%+)
- 4 concentrated positions
- NO sector limits (can have 4 tech if best)
- Shorter lookback (42 days)
- Monthly rebalancing
"""

from AlgorithmImports import *
from datetime import timedelta
import numpy as np


class ClenowAggressiveMomentum(QCAlgorithm):

    MOMENTUM_LOOKBACK = 42  # Shorter for faster signals
    TOP_N = 4  # Concentrated
    MIN_MOMENTUM = 60  # Very high threshold
    MIN_R_SQUARED = 0.55  # Relaxed R² to catch more

    LEVERAGE = 1.0
    # NO SECTOR LIMITS
    ATR_TRAILING_MULT = 2.5
    BEAR_EXPOSURE = 0.25

    ATR_PERIOD = 20
    USE_ATR_TRAILING = True
    MAX_POSITION_SIZE = 0.40

    def initialize(self):
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # High-beta universe
        self.universe_symbols = [
            "AAPL", "MSFT", "GOOGL", "NVDA", "META", "NFLX", "AMZN", "TSLA",
            "AMD", "AVGO", "MU", "CRM", "ADBE", "INTC", "CSCO", "QCOM",
            "TXN", "AMAT", "LRCX", "KLAC", "MCHP", "NXPI", "SWKS",
            "GILD", "BIIB", "AMGN", "REGN", "VRTX", "ISRG",
            "HD", "LOW", "TJX", "ROST", "ULTA",
            "GS", "MS", "JPM", "SCHW",
            "OXY", "DVN", "EOG", "COP", "PXD",
            "EA", "ATVI", "TTWO",
            "WYNN", "LVS", "MGM",
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
        # Must be above fast SMA, fast > slow
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
            mom, rsq = self.calculate_momentum(symbol)
            if mom is None or rsq is None:
                continue
            if rsq < self.MIN_R_SQUARED:
                continue
            if mom > self.MIN_MOMENTUM:
                candidates.append((symbol, mom))

        # Fallback with lower threshold
        if len(candidates) < self.TOP_N:
            for symbol in self.stocks:
                if not self.is_uptrending(symbol):
                    continue
                mom, rsq = self.calculate_momentum(symbol)
                if mom is not None and mom > 30:
                    if not any(s == symbol for s, _ in candidates):
                        candidates.append((symbol, mom * (rsq or 0.5)))

        if len(candidates) < self.TOP_N:
            return

        candidates.sort(key=lambda x: x[1], reverse=True)
        # NO SECTOR LIMITS - just take top N
        top = candidates[:self.TOP_N]
        top_set = set(s for s, _ in top)

        self.log(f"AGGRESSIVE TOP: {', '.join([f'{s.value}({m:.0f})' for s, m in top])}")

        for symbol in self.current_holdings - top_set:
            self.liquidate(symbol)
            if symbol in self.position_peaks:
                del self.position_peaks[symbol]

        # Squared momentum weighting
        weights = [(s, mom ** 2) for s, mom in top]
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
