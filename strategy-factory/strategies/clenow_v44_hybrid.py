"""
Clenow v44 Hybrid: Best of v42 + v43 adaptive features

Strategy:
- Use v42 base parameters (proven historical performance)
- Add dynamic volatility adjustment (from v43 learnings)
- When VIX/volatility is high: tighter filters, smaller positions
- When VIX/volatility is low: normal aggressive positioning
- Exclude only the worst 2024-2025 losers: ILMN, SBUX

Key insight from v43: 2024 went from +2.5% to +41.3% with adaptive params
But early years suffered. Solution: adapt based on market regime.
"""

from AlgorithmImports import *
from datetime import timedelta
import numpy as np


class ClenowHybridV44(QCAlgorithm):

    # Base parameters (from v42)
    MOMENTUM_LOOKBACK = 50
    TOP_N = 3
    MIN_MOMENTUM = 55
    MIN_REL_STRENGTH = 15
    MIN_R_SQUARED = 0.55

    # Leverage
    BASE_LEVERAGE = 1.4
    REDUCED_LEVERAGE = 1.1  # When volatile

    ATR_TRAILING_MULT = 2.6
    BEAR_EXPOSURE = 0.0
    MAX_PER_SECTOR = 1

    ATR_PERIOD = 20
    USE_ATR_TRAILING = True
    MAX_POSITION_SIZE = 0.50

    # Adaptive thresholds
    BASE_ATR_PERCENT = 0.05  # Normal volatility filter
    TIGHT_ATR_PERCENT = 0.035  # When market is volatile

    COOLDOWN_WEEKS = 4

    # Market volatility threshold (SPY 20-day ATR%)
    HIGH_VOL_THRESHOLD = 0.015  # 1.5% daily ATR on SPY = high vol

    # Exclude worst performers
    EXCLUDE_TICKERS = {"ILMN", "SBUX"}

    SECTOR_MAP = {
        "AAPL": "Tech", "MSFT": "Tech", "GOOGL": "Tech", "META": "Tech",
        "CRM": "Tech", "ADBE": "Tech", "NOW": "Tech", "ORCL": "Tech", "IBM": "Tech",
        "NVDA": "Semi", "AMD": "Semi", "INTC": "Semi", "AVGO": "Semi",
        "MU": "Semi", "AMAT": "Semi", "LRCX": "Semi", "QCOM": "Semi",
        "TXN": "Semi", "KLAC": "Semi",
        "AMGN": "Biotech", "GILD": "Biotech", "BIIB": "Biotech", "REGN": "Biotech",
        "VRTX": "Biotech", "MRNA": "Biotech",
        "AMZN": "Consumer", "TSLA": "Consumer", "HD": "Consumer", "NKE": "Consumer",
        "MCD": "Consumer", "TGT": "Consumer", "LULU": "Consumer",
        "JPM": "Finance", "BAC": "Finance", "GS": "Finance", "MS": "Finance",
        "C": "Finance", "WFC": "Finance", "AXP": "Finance", "BLK": "Finance",
        "XOM": "Energy", "CVX": "Energy", "COP": "Energy", "EOG": "Energy",
        "OXY": "Energy", "DVN": "Energy", "SLB": "Energy", "HAL": "Energy",
    }

    def initialize(self):
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2026, 1, 9)
        self.set_cash(100000)

        self.universe_symbols = [t for t in self.SECTOR_MAP.keys()
                                  if t not in self.EXCLUDE_TICKERS]
        self.stocks = []

        for ticker in self.universe_symbols:
            try:
                equity = self.add_equity(ticker, Resolution.DAILY)
                equity.set_slippage_model(ConstantSlippageModel(0.001))
                equity.set_fee_model(InteractiveBrokersFeeModel())
                self.stocks.append(equity.symbol)
            except Exception as e:
                self.debug(f"Could not add {ticker}: {e}")

        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.set_benchmark(self.spy)
        self.spy_sma = self.sma(self.spy, 200, Resolution.DAILY)

        # SPY ATR for market volatility detection
        self.spy_atr = AverageTrueRange(20)
        self.register_indicator(self.spy, self.spy_atr, Resolution.DAILY)

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
        self.cooldown_until = {}

        self.set_warmup(timedelta(days=210))

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

    def is_high_volatility_market(self) -> bool:
        """Check if market is in high volatility regime"""
        if not self.spy_atr.is_ready:
            return False
        spy_price = self.securities[self.spy].price
        if spy_price <= 0:
            return False
        spy_atr_pct = self.spy_atr.current.value / spy_price
        return spy_atr_pct > self.HIGH_VOL_THRESHOLD

    def get_current_atr_threshold(self) -> float:
        """Return tighter or looser ATR threshold based on market vol"""
        if self.is_high_volatility_market():
            return self.TIGHT_ATR_PERCENT
        return self.BASE_ATR_PERCENT

    def get_current_leverage(self) -> float:
        """Return lower leverage in high vol markets"""
        if self.is_high_volatility_market():
            return self.REDUCED_LEVERAGE
        return self.BASE_LEVERAGE

    def get_sector(self, symbol):
        return self.SECTOR_MAP.get(symbol.value, "Other")

    def has_sufficient_data(self, symbol) -> bool:
        if symbol not in self.stock_sma:
            return False
        if not self.stock_sma[symbol].is_ready:
            return False
        if symbol not in self.stock_atr:
            return False
        if not self.stock_atr[symbol].is_ready:
            return False
        return True

    def is_too_volatile(self, symbol) -> bool:
        if symbol not in self.stock_atr:
            return True
        atr = self.stock_atr[symbol]
        if not atr.is_ready:
            return True
        price = self.securities[symbol].price
        if price <= 0:
            return True
        atr_percent = atr.current.value / price
        return atr_percent > self.get_current_atr_threshold()

    def is_in_cooldown(self, symbol) -> bool:
        if symbol not in self.cooldown_until:
            return False
        return self.rebalance_week < self.cooldown_until[symbol]

    def calculate_momentum(self, symbol):
        history = self.history(symbol, self.MOMENTUM_LOOKBACK + 1, Resolution.DAILY)
        if history.empty or len(history) < self.MOMENTUM_LOOKBACK:
            return None, None
        try:
            prices = history['close'].values
            if len(prices) < self.MOMENTUM_LOOKBACK:
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

    def calculate_relative_strength(self, symbol):
        stock_hist = self.history(symbol, self.MOMENTUM_LOOKBACK + 1, Resolution.DAILY)
        spy_hist = self.history(self.spy, self.MOMENTUM_LOOKBACK + 1, Resolution.DAILY)
        if stock_hist.empty or spy_hist.empty:
            return None
        try:
            if len(stock_hist) < self.MOMENTUM_LOOKBACK or len(spy_hist) < self.MOMENTUM_LOOKBACK:
                return None
            stock_ret = (stock_hist['close'].values[-1] / stock_hist['close'].values[0]) - 1
            spy_ret = (spy_hist['close'].values[-1] / spy_hist['close'].values[0]) - 1
            return (stock_ret - spy_ret) * (252 / self.MOMENTUM_LOOKBACK) * 100
        except:
            return None

    def is_uptrending(self, symbol) -> bool:
        if symbol not in self.stock_sma:
            return False
        sma = self.stock_sma[symbol]
        if not sma.is_ready:
            return False
        price = self.securities[symbol].price
        if price <= 0:
            return False
        return price > sma.current.value

    def get_regime_exposure(self) -> float:
        if not self.spy_sma.is_ready:
            return 0.0
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
                        if symbol in self.position_peaks:
                            del self.position_peaks[symbol]
                        self.cooldown_until[symbol] = self.rebalance_week + self.COOLDOWN_WEEKS
                        continue

            if not self.is_uptrending(symbol):
                avg = self.portfolio[symbol].average_price
                if avg > 0 and price < avg * 0.93:
                    self.liquidate(symbol)
                    self.current_holdings.discard(symbol)
                    if symbol in self.position_peaks:
                        del self.position_peaks[symbol]
                    self.cooldown_until[symbol] = self.rebalance_week + self.COOLDOWN_WEEKS

    def rebalance(self):
        if self.is_warming_up:
            return

        regime = self.get_regime_exposure()
        if regime < 0.1:
            self.liquidate()
            self.current_holdings = set()
            self.position_peaks = {}
            return

        candidates = []
        for symbol in self.stocks:
            if not self.has_sufficient_data(symbol):
                continue
            if not self.is_uptrending(symbol):
                continue
            if self.is_in_cooldown(symbol):
                continue
            if self.is_too_volatile(symbol):
                continue

            mom, rsq = self.calculate_momentum(symbol)
            if mom is None or rsq is None:
                continue
            if rsq < self.MIN_R_SQUARED:
                continue

            rel_str = self.calculate_relative_strength(symbol)
            if rel_str is None or rel_str < self.MIN_REL_STRENGTH:
                continue

            if mom > self.MIN_MOMENTUM:
                score = mom * (1 + rel_str / 100)
                candidates.append((symbol, score))

        # Fallback
        if len(candidates) < self.TOP_N:
            for symbol in self.stocks:
                if not self.has_sufficient_data(symbol):
                    continue
                if not self.is_uptrending(symbol):
                    continue
                if self.is_in_cooldown(symbol):
                    continue
                mom, rsq = self.calculate_momentum(symbol)
                if mom is not None and mom > 30 and rsq is not None and rsq > 0.45:
                    rel_str = self.calculate_relative_strength(symbol)
                    if rel_str is not None and rel_str > 5:
                        if not any(s == symbol for s, _ in candidates):
                            candidates.append((symbol, mom * rsq))

        if len(candidates) < self.TOP_N:
            return

        candidates.sort(key=lambda x: x[1], reverse=True)

        sector_counts = {}
        top = []
        for symbol, score in candidates:
            sector = self.get_sector(symbol)
            if sector_counts.get(sector, 0) < self.MAX_PER_SECTOR:
                top.append((symbol, score))
                sector_counts[sector] = sector_counts.get(sector, 0) + 1
                if len(top) >= self.TOP_N:
                    break

        if len(top) < self.TOP_N:
            top = candidates[:self.TOP_N]

        top_set = set(s for s, _ in top)

        for symbol in self.current_holdings - top_set:
            self.liquidate(symbol)
            if symbol in self.position_peaks:
                del self.position_peaks[symbol]

        leverage = self.get_current_leverage()
        weight = (leverage * regime) / self.TOP_N
        weight = min(weight, self.MAX_POSITION_SIZE)

        for symbol, _ in top:
            self.set_holdings(symbol, weight)
            if symbol not in self.position_peaks:
                self.position_peaks[symbol] = self.securities[symbol].price

        self.current_holdings = top_set

    def on_data(self, data):
        pass
