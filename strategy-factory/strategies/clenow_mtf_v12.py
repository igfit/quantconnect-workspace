"""
Clenow Momentum v12: Maximum Leverage for Target

v11 achieved 24.6% CAGR with only 23.6% DD
v12: Push to 1.6x leverage for ~30% CAGR target
"""

from AlgorithmImports import *
from datetime import timedelta
import numpy as np


class ClenowMTFv12(QCAlgorithm):

    MOMENTUM_LOOKBACK = 63
    TOP_N = 5
    MIN_MOMENTUM = 20
    MIN_R_SQUARED = 0.60

    # v12: Maximum leverage
    LEVERAGE = 1.6  # Increased from 1.4
    MAX_PER_SECTOR = 3
    VOL_SCALE_FACTOR = 0.5
    ATR_TRAILING_MULT = 2.5
    BEAR_EXPOSURE = 0.3

    USE_VOL_SCALING = True
    ATR_PERIOD = 20
    WEEKLY_TREND_CONFIRM = True
    USE_ACCELERATION = True
    ACCEL_LOOKBACK = 20
    USE_ATR_TRAILING = True
    MAX_POSITION_SIZE = 0.55  # Slightly higher for leverage

    SECTOR_MAP = {
        "AAPL": "Tech", "MSFT": "Tech", "GOOGL": "Tech", "INTC": "Tech",
        "CSCO": "Tech", "ORCL": "Tech", "IBM": "Tech", "QCOM": "Tech",
        "TXN": "Tech", "ADBE": "Tech", "CRM": "Tech", "VMW": "Tech",
        "AMAT": "Semi", "LRCX": "Semi", "KLAC": "Semi", "ADI": "Semi",
        "MCHP": "Semi", "XLNX": "Semi", "NVDA": "Semi", "MU": "Semi",
        "AVGO": "Semi", "NXPI": "Semi", "SWKS": "Semi", "QRVO": "Semi",
        "META": "Internet", "NFLX": "Internet", "EBAY": "Internet",
        "YHOO": "Internet", "TWTR": "Internet", "LNKD": "Internet",
        "YELP": "Internet", "GRPN": "Internet", "P": "Internet",
        "GILD": "Biotech", "BIIB": "Biotech", "CELG": "Biotech",
        "AMGN": "Biotech", "REGN": "Biotech", "VRTX": "Biotech",
        "ALXN": "Biotech", "ILMN": "Biotech", "ISRG": "Biotech",
        "AMZN": "Consumer", "PCLN": "Consumer", "EXPE": "Consumer",
        "TRIP": "Consumer", "NTES": "Consumer", "BIDU": "Consumer", "JD": "Consumer",
        "HD": "Retail", "LOW": "Retail", "TJX": "Retail", "ROST": "Retail",
        "ULTA": "Retail", "DG": "Retail", "DLTR": "Retail", "KSS": "Retail",
        "M": "Retail", "JWN": "Retail", "GPS": "Retail",
        "GS": "Finance", "MS": "Finance", "JPM": "Finance", "C": "Finance",
        "BAC": "Finance", "WFC": "Finance", "SCHW": "Finance", "ETFC": "Finance",
        "CME": "Finance", "ICE": "Finance", "NDAQ": "Finance",
        "OXY": "Energy", "APA": "Energy", "DVN": "Energy", "EOG": "Energy",
        "PXD": "Energy", "CLR": "Energy", "COP": "Energy", "HES": "Energy", "MRO": "Energy",
        "F": "Auto", "GM": "Auto", "TSLA": "Auto",
        "WYNN": "Gaming", "LVS": "Gaming", "MGM": "Gaming",
        "EA": "Gaming", "ATVI": "Gaming", "TTWO": "Gaming",
    }

    def initialize(self):
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.universe_symbols = [
            "AAPL", "MSFT", "GOOGL", "INTC", "CSCO", "ORCL", "IBM", "QCOM",
            "TXN", "ADBE", "CRM", "VMW", "AMAT", "LRCX", "KLAC", "ADI",
            "MCHP", "XLNX", "NVDA", "MU",
            "AVGO", "NXPI", "SWKS", "QRVO",
            "META", "NFLX", "EBAY", "YHOO", "TWTR", "LNKD", "YELP", "GRPN", "P",
            "GILD", "BIIB", "CELG", "AMGN", "REGN", "VRTX", "ALXN", "ILMN", "ISRG",
            "AMZN", "PCLN", "EXPE", "TRIP", "NTES", "BIDU", "JD",
            "HD", "LOW", "TJX", "ROST", "ULTA", "DG", "DLTR", "KSS", "M", "JWN", "GPS",
            "GS", "MS", "JPM", "C", "BAC", "WFC", "SCHW", "ETFC", "CME", "ICE", "NDAQ",
            "OXY", "APA", "DVN", "EOG", "PXD", "CLR", "COP", "HES", "MRO",
            "F", "GM", "TSLA",
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

        self.stock_sma_fast = {}
        self.stock_sma_slow = {}
        self.stock_atr = {}

        for symbol in self.stocks:
            self.stock_sma_fast[symbol] = self.sma(symbol, 50, Resolution.DAILY)
            self.stock_sma_slow[symbol] = self.sma(symbol, 100, Resolution.DAILY)
            atr_indicator = AverageTrueRange(self.ATR_PERIOD)
            self.register_indicator(symbol, atr_indicator, Resolution.DAILY)
            self.stock_atr[symbol] = atr_indicator

        self.current_holdings = set()
        self.position_peaks = {}
        self.set_warmup(timedelta(days=150))

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
        if not self.USE_ACCELERATION:
            return True
        current_mom, _ = self.calculate_momentum(symbol)
        if current_mom is None:
            return False
        history = self.history(symbol, self.MOMENTUM_LOOKBACK + self.ACCEL_LOOKBACK + 1, Resolution.DAILY)
        if history.empty or len(history) < self.MOMENTUM_LOOKBACK + self.ACCEL_LOOKBACK:
            return True
        try:
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
            return current_mom > old_mom_adj
        except:
            return True

    def is_weekly_uptrend(self, symbol) -> bool:
        if not self.WEEKLY_TREND_CONFIRM:
            return True
        history = self.history(symbol, 50, Resolution.DAILY)
        if history.empty or len(history) < 50:
            return True
        try:
            prices = history['close'].values
            multiplier = 2 / 51
            ema = prices[0]
            for price in prices[1:]:
                ema = (price - ema) * multiplier + ema
            return self.securities[symbol].price > ema
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
        if price < sma_fast.current.value or price < sma_slow.current.value:
            return False
        if sma_fast.current.value < sma_slow.current.value:
            return False
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
        atr_pct = atr.current.value / price
        base_weight = 0.02 / max(atr_pct, 0.005)
        adjusted = 1.0 + (base_weight - 1.0) * self.VOL_SCALE_FACTOR
        return max(0.75, min(1.5, adjusted))

    def apply_sector_limits(self, rankings):
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
        if not self.spy_sma.is_ready:
            return 1.0
        if self.securities[self.spy].price > self.spy_sma.current.value:
            return 1.0
        else:
            return self.BEAR_EXPOSURE

    def daily_risk_check(self):
        if self.is_warming_up:
            return
        for symbol in list(self.current_holdings):
            if not self.portfolio[symbol].invested:
                continue
            current_price = self.securities[symbol].price
            if current_price <= 0:
                continue
            if symbol not in self.position_peaks:
                self.position_peaks[symbol] = current_price
            else:
                self.position_peaks[symbol] = max(self.position_peaks[symbol], current_price)
            if self.USE_ATR_TRAILING and symbol in self.stock_atr:
                atr = self.stock_atr[symbol]
                if atr.is_ready:
                    peak_price = self.position_peaks[symbol]
                    atr_stop = peak_price - (self.ATR_TRAILING_MULT * atr.current.value)
                    if current_price < atr_stop:
                        self.liquidate(symbol)
                        self.current_holdings.discard(symbol)
                        del self.position_peaks[symbol]
                        continue
            if not self.is_uptrending(symbol):
                avg_price = self.portfolio[symbol].average_price
                if avg_price > 0 and current_price < avg_price * 0.97:
                    self.liquidate(symbol)
                    self.current_holdings.discard(symbol)
                    if symbol in self.position_peaks:
                        del self.position_peaks[symbol]

    def rebalance(self):
        if self.is_warming_up:
            return
        regime_exposure = self.get_regime_exposure()
        if regime_exposure < 0.2:
            if self.current_holdings:
                self.liquidate()
                self.current_holdings = set()
                self.position_peaks = {}
            return
        candidates = []
        for symbol in self.stocks:
            if not self.is_uptrending(symbol):
                continue
            if not self.is_weekly_uptrend(symbol):
                continue
            if not self.get_momentum_acceleration(symbol):
                continue
            mom, rsq = self.calculate_momentum(symbol)
            if mom is None or rsq is None:
                continue
            if rsq < self.MIN_R_SQUARED:
                continue
            if mom > self.MIN_MOMENTUM:
                candidates.append((symbol, mom))
        if len(candidates) < self.TOP_N:
            candidates = []
            for symbol in self.stocks:
                if not self.is_uptrending(symbol):
                    continue
                mom, rsq = self.calculate_momentum(symbol)
                if mom is not None and mom > 0:
                    candidates.append((symbol, mom))
        if len(candidates) < self.TOP_N:
            return
        candidates.sort(key=lambda x: x[1], reverse=True)
        top_stocks_with_mom = self.apply_sector_limits(candidates)
        if len(top_stocks_with_mom) < self.TOP_N:
            top_stocks_with_mom = candidates[:self.TOP_N]
        top_stocks = [s for s, m in top_stocks_with_mom]
        top_stocks_set = set(top_stocks)
        for symbol in self.current_holdings - top_stocks_set:
            self.liquidate(symbol)
            if symbol in self.position_peaks:
                del self.position_peaks[symbol]
        weights = []
        for symbol, mom in top_stocks_with_mom:
            vol_weight = self.get_volatility_weight(symbol)
            combined = (mom ** 2) * vol_weight
            weights.append((symbol, combined))
        total_weight = sum(w for _, w in weights)
        for symbol, raw_weight in weights:
            weight = (raw_weight / total_weight) * self.LEVERAGE * regime_exposure
            weight = min(weight, self.MAX_POSITION_SIZE)
            self.set_holdings(symbol, weight)
            if symbol not in self.position_peaks:
                self.position_peaks[symbol] = self.securities[symbol].price
        self.current_holdings = top_stocks_set

    def on_data(self, data):
        pass
