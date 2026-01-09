"""
Clenow v26: Trend + Pullback Entry

Hypothesis: Better entry timing by waiting for pullbacks in uptrends
- Identify strong momentum stocks (trend following)
- Enter on RSI pullbacks (mean reversion timing)
- This gives better average entry prices

Key innovation:
- Maintain a "watchlist" of top momentum stocks
- Only enter when RSI < 40 (oversold in uptrend)
- Exit on trend break OR RSI > 80 (profit taking)
"""

from AlgorithmImports import *
from datetime import timedelta
import numpy as np


class ClenowPullbackEntry(QCAlgorithm):

    MOMENTUM_LOOKBACK = 63
    TOP_N = 5  # Watchlist size
    MAX_POSITIONS = 5  # Max concurrent positions
    MIN_MOMENTUM = 30
    RSI_ENTRY = 40  # Enter when RSI drops below
    RSI_EXIT = 80   # Exit when RSI rises above
    RSI_PERIOD = 14

    LEVERAGE = 1.0
    MAX_PER_SECTOR = 2
    ATR_TRAILING_MULT = 2.5
    BEAR_EXPOSURE = 0.3

    ATR_PERIOD = 20
    USE_ATR_TRAILING = True
    MAX_POSITION_SIZE = 0.30

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
        self.stock_rsi = {}
        self.stock_atr = {}

        for symbol in self.stocks:
            self.stock_sma[symbol] = self.sma(symbol, 50, Resolution.DAILY)
            # Create RSI indicator manually (same pattern as ATR)
            rsi = RelativeStrengthIndex(self.RSI_PERIOD)
            self.register_indicator(symbol, rsi, Resolution.DAILY)
            self.stock_rsi[symbol] = rsi
            # ATR for trailing stops
            atr = AverageTrueRange(self.ATR_PERIOD)
            self.register_indicator(symbol, atr, Resolution.DAILY)
            self.stock_atr[symbol] = atr

        self.watchlist = []  # Top momentum stocks to watch
        self.current_holdings = set()
        self.position_peaks = {}
        self.set_warmup(timedelta(days=150))

        # Update watchlist monthly
        self.schedule.on(
            self.date_rules.month_start(self.spy),
            self.time_rules.after_market_open(self.spy, 30),
            self.update_watchlist
        )

        # Check for entries/exits daily
        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.after_market_open(self.spy, 60),
            self.check_signals
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

    def update_watchlist(self):
        """Monthly: Update watchlist with top momentum stocks"""
        if self.is_warming_up:
            return

        candidates = []
        for symbol in self.stocks:
            if not self.is_uptrending(symbol):
                continue
            mom, rsq = self.calculate_momentum(symbol)
            if mom is None or rsq is None:
                continue
            if mom > self.MIN_MOMENTUM and rsq > 0.5:
                candidates.append((symbol, mom * rsq))

        candidates.sort(key=lambda x: x[1], reverse=True)

        # Apply sector limits to watchlist
        sector_counts = {}
        filtered = []
        for symbol, score in candidates:
            sector = self.get_sector(symbol)
            if sector_counts.get(sector, 0) < self.MAX_PER_SECTOR:
                filtered.append(symbol)
                sector_counts[sector] = sector_counts.get(sector, 0) + 1
                if len(filtered) >= self.TOP_N:
                    break

        self.watchlist = filtered
        self.log(f"WATCHLIST: {', '.join([s.value for s in self.watchlist])}")

    def check_signals(self):
        """Daily: Check for entry/exit signals"""
        if self.is_warming_up:
            return

        regime = self.get_regime_exposure()
        if regime < 0.2:
            self.liquidate()
            self.current_holdings = set()
            self.position_peaks = {}
            return

        # Check exits first
        for symbol in list(self.current_holdings):
            if not self.portfolio[symbol].invested:
                continue

            price = self.securities[symbol].price
            if price <= 0:
                continue

            # Update peak
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
                        self.log(f"ATR EXIT: {symbol.value}")
                        self.liquidate(symbol)
                        self.current_holdings.discard(symbol)
                        del self.position_peaks[symbol]
                        continue

            # RSI profit taking
            if symbol in self.stock_rsi:
                rsi = self.stock_rsi[symbol]
                if rsi.is_ready and rsi.current.value > self.RSI_EXIT:
                    self.log(f"RSI EXIT: {symbol.value} RSI={rsi.current.value:.0f}")
                    self.liquidate(symbol)
                    self.current_holdings.discard(symbol)
                    if symbol in self.position_peaks:
                        del self.position_peaks[symbol]
                    continue

            # Trend break
            if not self.is_uptrending(symbol):
                avg = self.portfolio[symbol].average_price
                if avg > 0 and price < avg * 0.95:
                    self.liquidate(symbol)
                    self.current_holdings.discard(symbol)
                    if symbol in self.position_peaks:
                        del self.position_peaks[symbol]

        # Check entries for watchlist stocks
        if len(self.current_holdings) >= self.MAX_POSITIONS:
            return

        for symbol in self.watchlist:
            if symbol in self.current_holdings:
                continue
            if len(self.current_holdings) >= self.MAX_POSITIONS:
                break

            # Must still be uptrending
            if not self.is_uptrending(symbol):
                continue

            # Check RSI for pullback entry
            if symbol not in self.stock_rsi:
                continue
            rsi = self.stock_rsi[symbol]
            if not rsi.is_ready:
                continue

            if rsi.current.value < self.RSI_ENTRY:
                # PULLBACK ENTRY
                weight = (self.LEVERAGE * regime) / self.MAX_POSITIONS
                weight = min(weight, self.MAX_POSITION_SIZE)
                self.set_holdings(symbol, weight)
                self.current_holdings.add(symbol)
                self.position_peaks[symbol] = self.securities[symbol].price
                self.log(f"PULLBACK ENTRY: {symbol.value} RSI={rsi.current.value:.0f}")

    def on_data(self, data):
        pass
