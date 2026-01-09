"""
Clenow v28: Volume Breakout Momentum

Hypothesis: Volume confirms momentum - high volume breakouts are more reliable.
Enter only when price breaks to new highs with above-average volume.

Key innovations:
- Volume confirmation filter (volume > 1.5x 20-day average)
- 52-week high proximity filter (within 5% of high)
- Tighter positions (3 stocks)
- Aggressive exits
"""

from AlgorithmImports import *
from datetime import timedelta
import numpy as np


class ClenowVolumeBreakout(QCAlgorithm):

    MOMENTUM_LOOKBACK = 63
    TOP_N = 3
    MIN_MOMENTUM = 40
    MIN_R_SQUARED = 0.55
    VOLUME_MULT = 1.5  # Volume must be 1.5x average
    HIGH_PROXIMITY = 0.95  # Must be within 5% of 52-week high

    LEVERAGE = 1.0
    MAX_PER_SECTOR = 2
    ATR_TRAILING_MULT = 2.5
    BEAR_EXPOSURE = 0.0

    ATR_PERIOD = 20
    USE_ATR_TRAILING = True
    MAX_POSITION_SIZE = 0.40

    SECTOR_MAP = {
        "NVDA": "Semi", "AMD": "Semi", "AVGO": "Semi", "MU": "Semi",
        "AMAT": "Semi", "LRCX": "Semi", "TSLA": "Auto",
        "META": "Internet", "NFLX": "Internet", "GOOGL": "Tech",
        "AMZN": "Consumer", "CRM": "Tech", "AAPL": "Tech", "MSFT": "Tech",
        "QCOM": "Semi", "ADBE": "Tech",
    }

    def initialize(self):
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.universe_symbols = [
            "NVDA", "AMD", "AVGO", "MU", "AMAT", "LRCX", "QCOM",
            "TSLA", "META", "NFLX", "GOOGL", "AMZN", "CRM", "ADBE",
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

        self.stock_sma = {}
        self.stock_atr = {}
        self.stock_vol_sma = {}

        for symbol in self.stocks:
            self.stock_sma[symbol] = self.sma(symbol, 50, Resolution.DAILY)
            atr = AverageTrueRange(self.ATR_PERIOD)
            self.register_indicator(symbol, atr, Resolution.DAILY)
            self.stock_atr[symbol] = atr

        self.current_holdings = set()
        self.position_peaks = {}
        self.set_warmup(timedelta(days=260))  # Need 52 weeks for high

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

    def check_volume_breakout(self, symbol) -> bool:
        """Check if current volume is above 1.5x 20-day average"""
        history = self.history(symbol, 21, Resolution.DAILY)
        if history.empty or len(history) < 20:
            return True  # Allow if no data

        try:
            volumes = history['volume'].values
            avg_vol = np.mean(volumes[:-1])  # Average of prior 20 days
            current_vol = volumes[-1]
            return current_vol > avg_vol * self.VOLUME_MULT
        except:
            return True

    def near_52_week_high(self, symbol) -> bool:
        """Check if price is within 5% of 52-week high"""
        history = self.history(symbol, 252, Resolution.DAILY)
        if history.empty or len(history) < 100:
            return True

        try:
            high_52w = history['high'].max()
            current = self.securities[symbol].price
            return current >= high_52w * self.HIGH_PROXIMITY
        except:
            return True

    def is_uptrending(self, symbol) -> bool:
        if symbol not in self.stock_sma:
            return False
        sma = self.stock_sma[symbol]
        if not sma.is_ready:
            return False
        price = self.securities[symbol].price
        return price > sma.current.value

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
        if regime < 0.1:
            self.liquidate()
            self.current_holdings = set()
            self.position_peaks = {}
            return

        candidates = []
        for symbol in self.stocks:
            if not self.is_uptrending(symbol):
                continue

            # Volume breakout confirmation
            if not self.check_volume_breakout(symbol):
                continue

            # Near 52-week high
            if not self.near_52_week_high(symbol):
                continue

            mom, rsq = self.calculate_momentum(symbol)
            if mom is None or rsq is None:
                continue
            if rsq < self.MIN_R_SQUARED:
                continue

            if mom > self.MIN_MOMENTUM:
                candidates.append((symbol, mom * rsq))

        # Fallback without volume filter
        if len(candidates) < self.TOP_N:
            for symbol in self.stocks:
                if not self.is_uptrending(symbol):
                    continue
                if not self.near_52_week_high(symbol):
                    continue
                mom, rsq = self.calculate_momentum(symbol)
                if mom is not None and mom > 20:
                    if not any(s == symbol for s, _ in candidates):
                        candidates.append((symbol, mom * (rsq or 0.5)))

        if len(candidates) < self.TOP_N:
            return

        candidates.sort(key=lambda x: x[1], reverse=True)

        # Sector limits
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

        self.log(f"VOL BREAKOUT: {', '.join([f'{s.value}' for s, _ in top])}")

        for symbol in self.current_holdings - top_set:
            self.liquidate(symbol)
            if symbol in self.position_peaks:
                del self.position_peaks[symbol]

        weight = (self.LEVERAGE * regime) / self.TOP_N
        weight = min(weight, self.MAX_POSITION_SIZE)

        for symbol, _ in top:
            self.set_holdings(symbol, weight)
            if symbol not in self.position_peaks:
                self.position_peaks[symbol] = self.securities[symbol].price

        self.current_holdings = top_set

    def on_data(self, data):
        pass
