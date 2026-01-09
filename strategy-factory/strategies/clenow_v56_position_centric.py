"""
Clenow v56: Position-Centric Daily Monitoring

Key difference from v39:
- NO fixed rebalance schedule
- Each position managed independently
- Entry signals checked DAILY for all stocks
- Exit signals checked DAILY for all holdings
- Portfolio is just a collection of independent positions

Entry: When a stock meets momentum criteria, BUY
Exit: When a stock's momentum breaks down, SELL
"""

from AlgorithmImports import *
from datetime import timedelta
import numpy as np


class ClenowPositionCentric(QCAlgorithm):

    # Entry thresholds
    MOMENTUM_LOOKBACK = 50
    MIN_MOMENTUM = 50  # Higher bar for entry
    MIN_REL_STRENGTH = 15
    MIN_R_SQUARED = 0.55

    # Exit thresholds (looser than entry)
    EXIT_MOMENTUM = 20  # Exit when momentum drops below this
    EXIT_REL_STRENGTH = 0  # Exit when no longer beating SPY

    # Position management
    MAX_POSITIONS = 5
    POSITION_SIZE = 0.19  # ~19% each, leaves cash buffer
    MAX_PER_SECTOR = 2

    # Risk management
    ATR_PERIOD = 20
    ATR_TRAILING_MULT = 2.5
    HARD_STOP_PCT = 0.08  # 8% hard stop from entry

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

        # Position tracking
        self.positions = {}  # symbol -> {entry_price, peak_price, entry_date}
        self.set_warmup(timedelta(days=120))

        # Run DAILY - check all positions and candidates every day
        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.after_market_open(self.spy, 30),
            self.daily_scan
        )

    def get_sector(self, symbol):
        return self.SECTOR_MAP.get(symbol.value, "Other")

    def count_sector_positions(self):
        """Count current positions per sector."""
        counts = {}
        for symbol in self.positions:
            sector = self.get_sector(symbol)
            counts[sector] = counts.get(sector, 0) + 1
        return counts

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
        """Check if a stock qualifies for a new position."""
        # Must be in uptrend
        if not self.is_uptrending(symbol):
            return False

        # Check momentum
        mom, rsq = self.calculate_momentum(symbol)
        if mom is None or rsq is None:
            return False
        if rsq < self.MIN_R_SQUARED:
            return False
        if mom < self.MIN_MOMENTUM:
            return False

        # Check relative strength
        rel_str = self.calculate_relative_strength(symbol)
        if rel_str is None or rel_str < self.MIN_REL_STRENGTH:
            return False

        return True

    def check_exit_signal(self, symbol) -> str:
        """Check if a position should be closed. Returns reason or None."""
        price = self.securities[symbol].price
        pos_info = self.positions.get(symbol, {})
        entry_price = pos_info.get('entry_price', price)
        peak_price = pos_info.get('peak_price', price)

        # Hard stop loss
        if price < entry_price * (1 - self.HARD_STOP_PCT):
            return "hard_stop"

        # ATR trailing stop
        if symbol in self.stock_atr:
            atr = self.stock_atr[symbol]
            if atr.is_ready:
                stop = peak_price - (self.ATR_TRAILING_MULT * atr.current.value)
                if price < stop:
                    return "atr_stop"

        # Momentum breakdown
        mom, rsq = self.calculate_momentum(symbol)
        if mom is not None and mom < self.EXIT_MOMENTUM:
            return "momentum_exit"

        # Relative strength breakdown
        rel_str = self.calculate_relative_strength(symbol)
        if rel_str is not None and rel_str < self.EXIT_REL_STRENGTH:
            return "rel_strength_exit"

        # Trend breakdown (price below 20 SMA)
        if not self.is_uptrending(symbol):
            return "trend_exit"

        return None

    def daily_scan(self):
        """Run every day - check exits first, then entries."""
        if self.is_warming_up:
            return

        # STEP 1: Check market regime
        if not self.is_bull_market():
            # Bear market - close all positions
            for symbol in list(self.positions.keys()):
                self.liquidate(symbol)
                self.log(f"EXIT {symbol.value}: bear_market")
            self.positions = {}
            return

        # STEP 2: Update peak prices for trailing stops
        for symbol in list(self.positions.keys()):
            if self.portfolio[symbol].invested:
                price = self.securities[symbol].price
                if price > self.positions[symbol]['peak_price']:
                    self.positions[symbol]['peak_price'] = price

        # STEP 3: Check EXIT signals for current positions
        for symbol in list(self.positions.keys()):
            exit_reason = self.check_exit_signal(symbol)
            if exit_reason:
                self.liquidate(symbol)
                self.log(f"EXIT {symbol.value}: {exit_reason}")
                del self.positions[symbol]

        # STEP 4: Check ENTRY signals for new positions
        if len(self.positions) >= self.MAX_POSITIONS:
            return  # Portfolio full

        sector_counts = self.count_sector_positions()

        # Find all stocks with entry signals
        candidates = []
        for symbol in self.stocks:
            if symbol in self.positions:
                continue  # Already holding

            sector = self.get_sector(symbol)
            if sector_counts.get(sector, 0) >= self.MAX_PER_SECTOR:
                continue  # Sector full

            if self.check_entry_signal(symbol):
                mom, _ = self.calculate_momentum(symbol)
                rel_str = self.calculate_relative_strength(symbol)
                score = mom * (1 + (rel_str or 0) / 100)
                candidates.append((symbol, score, sector))

        # Sort by score and open positions up to max
        candidates.sort(key=lambda x: x[1], reverse=True)

        for symbol, score, sector in candidates:
            if len(self.positions) >= self.MAX_POSITIONS:
                break

            # Re-check sector limit (may have changed)
            sector_counts = self.count_sector_positions()
            if sector_counts.get(sector, 0) >= self.MAX_PER_SECTOR:
                continue

            # Open position
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
