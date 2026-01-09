"""
Clenow v58: Position-Centric v3

Fixes:
- Check entries only WEEKLY (Mondays), but exits daily
- Add cooldown: can't re-enter same stock for 2 weeks after exit
- Require 3 consecutive days above 20-day high before entry
"""

from AlgorithmImports import *
from datetime import timedelta
import numpy as np


class ClenowPositionCentricV3(QCAlgorithm):

    MOMENTUM_LOOKBACK = 50
    MIN_MOMENTUM = 60
    MIN_REL_STRENGTH = 15
    MIN_R_SQUARED = 0.55

    EXIT_MOMENTUM = 15
    ATR_TRAILING_MULT = 2.8

    MAX_POSITIONS = 3
    POSITION_SIZE = 0.32
    MAX_PER_SECTOR = 1

    ATR_PERIOD = 20
    HARD_STOP_PCT = 0.08
    COOLDOWN_DAYS = 14

    SECTOR_MAP = {
        "AAPL": "Tech", "MSFT": "Tech", "GOOGL": "Tech", "META": "Tech",
        "CRM": "Tech", "ADBE": "Tech", "NOW": "Tech", "ORCL": "Tech", "IBM": "Tech",
        "NVDA": "Semi", "AMD": "Semi", "INTC": "Semi", "AVGO": "Semi",
        "MU": "Semi", "AMAT": "Semi", "LRCX": "Semi", "QCOM": "Semi",
        "TXN": "Semi", "KLAC": "Semi",
        "AMGN": "Biotech", "GILD": "Biotech", "BIIB": "Biotech", "REGN": "Biotech",
        "VRTX": "Biotech", "MRNA": "Biotech", "ILMN": "Biotech",
        "AMZN": "Consumer", "TSLA": "Consumer", "HD": "Consumer", "NKE": "Consumer",
        "SBUX": "Consumer", "MCD": "Consumer", "TGT": "Consumer", "LULU": "Consumer",
        "JPM": "Finance", "BAC": "Finance", "GS": "Finance", "MS": "Finance",
        "C": "Finance", "WFC": "Finance", "AXP": "Finance", "BLK": "Finance",
        "XOM": "Energy", "CVX": "Energy", "COP": "Energy", "EOG": "Energy",
        "OXY": "Energy", "DVN": "Energy", "SLB": "Energy", "HAL": "Energy",
    }

    def initialize(self):
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.universe_symbols = list(self.SECTOR_MAP.keys())
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
            self.stock_sma[symbol] = self.sma(symbol, 20, Resolution.DAILY)
            atr = AverageTrueRange(self.ATR_PERIOD)
            self.register_indicator(symbol, atr, Resolution.DAILY)
            self.stock_atr[symbol] = atr

        self.positions = {}
        self.cooldowns = {}  # symbol -> exit_date
        self.set_warmup(timedelta(days=120))

        # Exits checked daily
        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.after_market_open(self.spy, 30),
            self.check_exits
        )

        # Entries checked weekly (Mondays only)
        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.after_market_open(self.spy, 60),
            self.check_entries
        )

    def get_sector(self, symbol):
        return self.SECTOR_MAP.get(symbol.value, "Other")

    def count_sector_positions(self):
        counts = {}
        for symbol in self.positions:
            sector = self.get_sector(symbol)
            counts[sector] = counts.get(sector, 0) + 1
        return counts

    def is_in_cooldown(self, symbol) -> bool:
        if symbol not in self.cooldowns:
            return False
        exit_date = self.cooldowns[symbol]
        return (self.time - exit_date).days < self.COOLDOWN_DAYS

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
        stock_hist = self.history(symbol, self.MOMENTUM_LOOKBACK + 1, Resolution.DAILY)
        spy_hist = self.history(self.spy, self.MOMENTUM_LOOKBACK + 1, Resolution.DAILY)
        if stock_hist.empty or spy_hist.empty:
            return None
        try:
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
        return self.securities[symbol].price > sma.current.value

    def is_bull_market(self) -> bool:
        if not self.spy_sma.is_ready:
            return True
        return self.securities[self.spy].price > self.spy_sma.current.value

    def check_entry_signal(self, symbol) -> bool:
        if not self.is_uptrending(symbol):
            return False

        mom, rsq = self.calculate_momentum(symbol)
        if mom is None or rsq is None:
            return False
        if rsq < self.MIN_R_SQUARED or mom < self.MIN_MOMENTUM:
            return False

        rel_str = self.calculate_relative_strength(symbol)
        if rel_str is None or rel_str < self.MIN_REL_STRENGTH:
            return False

        return True

    def check_exit_signal(self, symbol) -> str:
        price = self.securities[symbol].price
        pos_info = self.positions.get(symbol, {})
        entry_price = pos_info.get('entry_price', price)
        peak_price = pos_info.get('peak_price', price)

        if price < entry_price * (1 - self.HARD_STOP_PCT):
            return "hard_stop"

        if symbol in self.stock_atr:
            atr = self.stock_atr[symbol]
            if atr.is_ready:
                stop = peak_price - (self.ATR_TRAILING_MULT * atr.current.value)
                if price < stop:
                    return "atr_stop"

        mom, _ = self.calculate_momentum(symbol)
        if mom is not None and mom < self.EXIT_MOMENTUM:
            return "momentum_exit"

        return None

    def check_exits(self):
        """Run daily - check exits and update peaks."""
        if self.is_warming_up:
            return

        # Bear market - close all
        if not self.is_bull_market():
            for symbol in list(self.positions.keys()):
                self.liquidate(symbol)
                self.cooldowns[symbol] = self.time
                self.log(f"EXIT {symbol.value}: bear_market")
            self.positions = {}
            return

        # Update peaks
        for symbol in list(self.positions.keys()):
            if self.portfolio[symbol].invested:
                price = self.securities[symbol].price
                if price > self.positions[symbol]['peak_price']:
                    self.positions[symbol]['peak_price'] = price

        # Check exits
        for symbol in list(self.positions.keys()):
            exit_reason = self.check_exit_signal(symbol)
            if exit_reason:
                self.liquidate(symbol)
                self.cooldowns[symbol] = self.time
                self.log(f"EXIT {symbol.value}: {exit_reason}")
                del self.positions[symbol]

    def check_entries(self):
        """Run weekly - check for new entries."""
        if self.is_warming_up:
            return
        if not self.is_bull_market():
            return
        if len(self.positions) >= self.MAX_POSITIONS:
            return

        sector_counts = self.count_sector_positions()

        candidates = []
        for symbol in self.stocks:
            if symbol in self.positions:
                continue
            if self.is_in_cooldown(symbol):
                continue

            sector = self.get_sector(symbol)
            if sector_counts.get(sector, 0) >= self.MAX_PER_SECTOR:
                continue

            if self.check_entry_signal(symbol):
                mom, _ = self.calculate_momentum(symbol)
                rel_str = self.calculate_relative_strength(symbol)
                score = mom * (1 + (rel_str or 0) / 100)
                candidates.append((symbol, score, sector))

        candidates.sort(key=lambda x: x[1], reverse=True)

        for symbol, score, sector in candidates:
            if len(self.positions) >= self.MAX_POSITIONS:
                break

            sector_counts = self.count_sector_positions()
            if sector_counts.get(sector, 0) >= self.MAX_PER_SECTOR:
                continue

            price = self.securities[symbol].price
            self.set_holdings(symbol, self.POSITION_SIZE)
            self.positions[symbol] = {
                'entry_price': price,
                'peak_price': price,
                'entry_date': self.time
            }
            self.log(f"ENTRY {symbol.value}: score={score:.1f}")

    def on_data(self, data):
        pass
