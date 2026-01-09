"""
Clenow v25: Momentum Acceleration

Hypothesis: Buy stocks where momentum is ACCELERATING the most
- Instead of absolute momentum level, focus on momentum CHANGE
- Compare current momentum to 21-day ago momentum
- Only buy when acceleration is positive and strong
- 4 positions, monthly rebalancing
"""

from AlgorithmImports import *
from datetime import timedelta
import numpy as np


class ClenowMomentumAccel(QCAlgorithm):

    MOMENTUM_LOOKBACK = 42
    ACCEL_LOOKBACK = 21  # Compare to 21 days ago
    TOP_N = 4
    MIN_MOMENTUM = 30  # Must have positive base momentum
    MIN_ACCELERATION = 20  # Momentum must have increased by 20%+

    LEVERAGE = 1.0
    MAX_PER_SECTOR = 2
    ATR_TRAILING_MULT = 2.5
    BEAR_EXPOSURE = 0.3

    ATR_PERIOD = 20
    USE_ATR_TRAILING = True
    MAX_POSITION_SIZE = 0.40

    SECTOR_MAP = {
        "AAPL": "Tech", "MSFT": "Tech", "GOOGL": "Tech", "NVDA": "Semi",
        "META": "Internet", "NFLX": "Internet", "AMZN": "Consumer",
        "TSLA": "Auto", "AMD": "Semi", "AVGO": "Semi", "MU": "Semi",
        "CRM": "Tech", "ADBE": "Tech", "INTC": "Semi",
        "QCOM": "Semi", "AMAT": "Semi", "LRCX": "Semi",
        "REGN": "Biotech", "VRTX": "Biotech", "ISRG": "Biotech",
        "HD": "Retail", "LOW": "Retail",
        "GS": "Finance", "MS": "Finance", "JPM": "Finance",
        "OXY": "Energy", "DVN": "Energy", "EOG": "Energy", "COP": "Energy",
    }

    def initialize(self):
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.universe_symbols = [
            "AAPL", "MSFT", "GOOGL", "NVDA", "META", "NFLX", "AMZN", "TSLA",
            "AMD", "AVGO", "MU", "CRM", "ADBE", "INTC", "CSCO", "QCOM",
            "TXN", "AMAT", "LRCX", "KLAC", "MCHP", "NXPI",
            "GILD", "BIIB", "AMGN", "REGN", "VRTX", "ISRG",
            "HD", "LOW", "TJX", "ROST",
            "GS", "MS", "JPM", "SCHW",
            "OXY", "DVN", "EOG", "COP", "PXD",
            "EA", "ATVI",
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

        for symbol in self.stocks:
            self.stock_sma[symbol] = self.sma(symbol, 50, Resolution.DAILY)
            atr = AverageTrueRange(self.ATR_PERIOD)
            self.register_indicator(symbol, atr, Resolution.DAILY)
            self.stock_atr[symbol] = atr

        self.current_holdings = set()
        self.position_peaks = {}
        self.set_warmup(timedelta(days=120))

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

    def calculate_momentum(self, symbol, lookback):
        history = self.history(symbol, lookback + 1, Resolution.DAILY)
        if history.empty or len(history) < lookback:
            return None
        try:
            prices = history['close'].values
            log_prices = np.log(prices)
            x = np.arange(len(log_prices))
            slope, _ = np.polyfit(x, log_prices, 1)
            return (np.exp(slope * 252) - 1) * 100
        except:
            return None

    def calculate_acceleration(self, symbol):
        """Calculate momentum acceleration: current mom - past mom"""
        # Current momentum
        current_mom = self.calculate_momentum(symbol, self.MOMENTUM_LOOKBACK)
        if current_mom is None:
            return None, None

        # Historical momentum (ACCEL_LOOKBACK days ago)
        history = self.history(symbol, self.MOMENTUM_LOOKBACK + self.ACCEL_LOOKBACK + 1, Resolution.DAILY)
        if history.empty or len(history) < self.MOMENTUM_LOOKBACK + self.ACCEL_LOOKBACK:
            return current_mom, 0

        try:
            old_prices = history['close'].values[:-self.ACCEL_LOOKBACK][-self.MOMENTUM_LOOKBACK:]
            log_prices = np.log(old_prices)
            x = np.arange(len(log_prices))
            slope, _ = np.polyfit(x, log_prices, 1)
            past_mom = (np.exp(slope * 252) - 1) * 100

            acceleration = current_mom - past_mom
            return current_mom, acceleration
        except:
            return current_mom, 0

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

        # MOMENTUM ACCELERATION FILTER
        candidates = []
        for symbol in self.stocks:
            if not self.is_uptrending(symbol):
                continue

            mom, accel = self.calculate_acceleration(symbol)
            if mom is None:
                continue

            # Must have base momentum
            if mom < self.MIN_MOMENTUM:
                continue

            # Must be accelerating
            if accel < self.MIN_ACCELERATION:
                continue

            # Score: momentum * acceleration
            score = mom * (1 + accel / 100)
            candidates.append((symbol, score))

        # Fallback
        if len(candidates) < self.TOP_N:
            for symbol in self.stocks:
                if not self.is_uptrending(symbol):
                    continue
                mom = self.calculate_momentum(symbol, self.MOMENTUM_LOOKBACK)
                if mom is not None and mom > 20:
                    if not any(s == symbol for s, _ in candidates):
                        candidates.append((symbol, mom))

        if len(candidates) < self.TOP_N:
            return

        candidates.sort(key=lambda x: x[1], reverse=True)
        top = self.apply_sector_limits(candidates)
        if len(top) < self.TOP_N:
            top = candidates[:self.TOP_N]

        top_set = set(s for s, _ in top)

        self.log(f"ACCEL TOP: {', '.join([f'{s.value}' for s, _ in top])}")

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
