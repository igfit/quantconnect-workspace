"""
Clenow v30: Sector Rotation Momentum

Hypothesis: Rotate into the strongest sector and take the top stocks within.
- Identify which sector has the strongest momentum
- Concentrate in that sector's top performers
- Monthly rotation between sectors

This allows more concentration when one sector is dominating.
"""

from AlgorithmImports import *
from datetime import timedelta
import numpy as np


class ClenowSectorRotation(QCAlgorithm):

    MOMENTUM_LOOKBACK = 63
    TOP_N = 4
    MIN_MOMENTUM = 30
    MIN_R_SQUARED = 0.55

    LEVERAGE = 1.0
    ATR_TRAILING_MULT = 2.5
    BEAR_EXPOSURE = 0.0

    ATR_PERIOD = 20
    USE_ATR_TRAILING = True
    MAX_POSITION_SIZE = 0.35

    SECTORS = {
        "Semi": ["NVDA", "AMD", "AVGO", "MU", "AMAT", "LRCX", "QCOM", "KLAC"],
        "Tech": ["AAPL", "MSFT", "GOOGL", "CRM", "ADBE"],
        "Internet": ["META", "NFLX", "AMZN"],
        "Auto": ["TSLA"],
        "Energy": ["OXY", "DVN", "EOG", "COP"],
        "Finance": ["GS", "MS", "JPM"],
    }

    def initialize(self):
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Flatten all sector symbols
        all_symbols = []
        for sector, tickers in self.SECTORS.items():
            all_symbols.extend(tickers)

        self.stocks = []
        self.symbol_sector = {}
        for ticker in all_symbols:
            try:
                equity = self.add_equity(ticker, Resolution.DAILY)
                equity.set_slippage_model(ConstantSlippageModel(0.001))
                equity.set_fee_model(InteractiveBrokersFeeModel())
                self.stocks.append(equity.symbol)
                # Map symbol to sector
                for sector, tickers in self.SECTORS.items():
                    if ticker in tickers:
                        self.symbol_sector[equity.symbol] = sector
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

    def calculate_sector_momentum(self):
        """Calculate average momentum for each sector"""
        sector_scores = {}
        for sector in self.SECTORS.keys():
            momenta = []
            for symbol in self.stocks:
                if self.symbol_sector.get(symbol) != sector:
                    continue
                mom, rsq = self.calculate_momentum(symbol)
                if mom is not None and rsq is not None and rsq > 0.3:
                    momenta.append(mom)
            if momenta:
                sector_scores[sector] = np.mean(momenta)
        return sector_scores

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

        # Find strongest sector
        sector_scores = self.calculate_sector_momentum()
        if not sector_scores:
            return

        sorted_sectors = sorted(sector_scores.items(), key=lambda x: x[1], reverse=True)
        top_sector = sorted_sectors[0][0]
        second_sector = sorted_sectors[1][0] if len(sorted_sectors) > 1 else None

        self.log(f"SECTORS: {', '.join([f'{s}({m:.0f})' for s, m in sorted_sectors[:3]])}")

        # Get candidates from top 2 sectors
        candidates = []
        for symbol in self.stocks:
            sector = self.symbol_sector.get(symbol)
            if sector not in [top_sector, second_sector]:
                continue
            if not self.is_uptrending(symbol):
                continue

            mom, rsq = self.calculate_momentum(symbol)
            if mom is None or rsq is None:
                continue
            if rsq < self.MIN_R_SQUARED:
                continue
            if mom > self.MIN_MOMENTUM:
                # Boost score for top sector
                boost = 1.2 if sector == top_sector else 1.0
                candidates.append((symbol, mom * rsq * boost))

        # Fallback
        if len(candidates) < self.TOP_N:
            for symbol in self.stocks:
                if not self.is_uptrending(symbol):
                    continue
                mom, rsq = self.calculate_momentum(symbol)
                if mom is not None and mom > 20:
                    if not any(s == symbol for s, _ in candidates):
                        candidates.append((symbol, mom * (rsq or 0.5)))

        if len(candidates) < self.TOP_N:
            return

        candidates.sort(key=lambda x: x[1], reverse=True)
        top = candidates[:self.TOP_N]
        top_set = set(s for s, _ in top)

        self.log(f"SECTOR ROT: {', '.join([f'{s.value}' for s, _ in top])}")

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
