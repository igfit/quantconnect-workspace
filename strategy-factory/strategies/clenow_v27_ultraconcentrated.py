"""
Clenow v27: Ultra-Concentrated High-Beta

Hypothesis: Maximum returns with 1.0x leverage requires:
1. VERY concentrated portfolio (3 positions max)
2. Focus ONLY on highest-beta stocks (semi + growth tech)
3. Aggressive momentum thresholds
4. Quick exits on trend breaks

Key innovations:
- Only 3 positions for maximum impact
- Narrower, higher-beta universe
- Monthly rebalancing with daily risk check
- Aggressive sector allocation (can have 2 semis)
"""

from AlgorithmImports import *
from datetime import timedelta
import numpy as np


class ClenowUltraConcentrated(QCAlgorithm):

    MOMENTUM_LOOKBACK = 42  # Faster signals
    TOP_N = 3  # Ultra concentrated
    MIN_MOMENTUM = 50  # High threshold
    MIN_R_SQUARED = 0.55

    LEVERAGE = 1.0  # CAPPED AT 1.0x
    MAX_PER_SECTOR = 2  # Allow concentration
    ATR_TRAILING_MULT = 2.0  # Tighter stops
    BEAR_EXPOSURE = 0.0  # Full cash in bear

    ATR_PERIOD = 20
    USE_ATR_TRAILING = True
    MAX_POSITION_SIZE = 0.45  # ~45% per position max

    # High-beta focused universe ONLY
    SECTOR_MAP = {
        "NVDA": "Semi", "AMD": "Semi", "AVGO": "Semi", "MU": "Semi",
        "AMAT": "Semi", "LRCX": "Semi", "KLAC": "Semi", "QCOM": "Semi",
        "TSLA": "Auto", "META": "Internet", "NFLX": "Internet",
        "GOOGL": "Tech", "AMZN": "Consumer", "CRM": "Tech",
        "AAPL": "Tech", "MSFT": "Tech",
    }

    def initialize(self):
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # NARROWER high-beta universe
        self.universe_symbols = [
            "NVDA", "AMD", "AVGO", "MU", "AMAT", "LRCX", "KLAC", "QCOM",
            "TSLA", "META", "NFLX", "GOOGL", "AMZN", "CRM",
            "AAPL", "MSFT",
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

    def calculate_relative_strength(self, symbol):
        """Stock return vs SPY return"""
        stock_hist = self.history(symbol, self.MOMENTUM_LOOKBACK + 1, Resolution.DAILY)
        spy_hist = self.history(self.spy, self.MOMENTUM_LOOKBACK + 1, Resolution.DAILY)
        if stock_hist.empty or spy_hist.empty:
            return None
        if len(stock_hist) < self.MOMENTUM_LOOKBACK:
            return None
        try:
            stock_ret = (stock_hist['close'].values[-1] / stock_hist['close'].values[0]) - 1
            spy_ret = (spy_hist['close'].values[-1] / spy_hist['close'].values[0]) - 1
            return (stock_ret - spy_ret) * (252 / self.MOMENTUM_LOOKBACK) * 100
        except:
            return None

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

            # Trend break with loss
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
        if regime < 0.1:  # Full cash in bear
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

            rel_str = self.calculate_relative_strength(symbol)
            if rel_str is None or rel_str < 0:  # Must beat SPY
                continue

            if mom > self.MIN_MOMENTUM:
                # Score: momentum * relative strength * quality
                score = mom * (1 + rel_str / 100) * rsq
                candidates.append((symbol, score, mom))

        # Fallback
        if len(candidates) < self.TOP_N:
            for symbol in self.stocks:
                if not self.is_uptrending(symbol):
                    continue
                mom, rsq = self.calculate_momentum(symbol)
                if mom is not None and mom > 20:
                    if not any(s == symbol for s, _, _ in candidates):
                        candidates.append((symbol, mom * (rsq or 0.5), mom))

        if len(candidates) < self.TOP_N:
            return

        candidates.sort(key=lambda x: x[1], reverse=True)

        # Apply sector limits
        sector_counts = {}
        top = []
        for symbol, score, mom in candidates:
            sector = self.get_sector(symbol)
            if sector_counts.get(sector, 0) < self.MAX_PER_SECTOR:
                top.append((symbol, score, mom))
                sector_counts[sector] = sector_counts.get(sector, 0) + 1
                if len(top) >= self.TOP_N:
                    break

        if len(top) < self.TOP_N:
            top = candidates[:self.TOP_N]

        top_set = set(s for s, _, _ in top)

        self.log(f"ULTRA TOP: {', '.join([f'{s.value}({m:.0f})' for s, _, m in top])}")

        for symbol in self.current_holdings - top_set:
            self.liquidate(symbol)
            if symbol in self.position_peaks:
                del self.position_peaks[symbol]

        # Equal weight with 3 positions
        weight = (self.LEVERAGE * regime) / self.TOP_N
        weight = min(weight, self.MAX_POSITION_SIZE)

        for symbol, _, _ in top:
            self.set_holdings(symbol, weight)
            if symbol not in self.position_peaks:
                self.position_peaks[symbol] = self.securities[symbol].price

        self.current_holdings = top_set

    def on_data(self, data):
        pass
