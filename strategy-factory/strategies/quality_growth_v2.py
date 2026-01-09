"""
Quality Growth Portfolio v2 - Improved Risk Management

Changes from v1:
1. Full cash in bear markets (SPY < 200 SMA) - no partial exposure
2. Individual stock filter: Only hold stocks above their 50 SMA
3. Updated stock list with 2024-2025 winners
4. Monthly rebalancing for faster response
5. Wider stop: Exit stock if drops 15% from recent high
"""

from AlgorithmImports import *
from datetime import timedelta
import numpy as np


class QualityGrowthV2(QCAlgorithm):

    # Quality growth stocks - updated for recent performance
    QUALITY_STOCKS = [
        "AAPL",   # Tech
        "MSFT",   # Tech - Cloud
        "GOOGL",  # Tech - AI
        "AMZN",   # Consumer/Cloud
        "NVDA",   # Semi - AI leader
        "META",   # Tech - AI/Social
        "AVGO",   # Semi - diversified
        "LLY",    # Healthcare - GLP-1
        "V",      # Finance - payments
        "COST",   # Consumer - stable
    ]

    LEVERAGE = 1.3
    BEAR_EXPOSURE = 0.0  # Full cash in bear market
    STOCK_STOP_LOSS = 0.15  # Exit if stock drops 15% from peak

    def initialize(self):
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2026, 1, 9)
        self.set_cash(100000)

        self.stocks = []
        self.stock_sma = {}
        self.stock_peaks = {}

        for ticker in self.QUALITY_STOCKS:
            try:
                equity = self.add_equity(ticker, Resolution.DAILY)
                equity.set_slippage_model(ConstantSlippageModel(0.001))
                self.stocks.append(equity.symbol)
                # 50-day SMA for trend filter
                self.stock_sma[equity.symbol] = self.sma(equity.symbol, 50, Resolution.DAILY)
            except Exception as e:
                self.debug(f"Could not add {ticker}: {e}")

        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.set_benchmark(self.spy)
        self.spy_sma = self.sma(self.spy, 200, Resolution.DAILY)

        self.set_warmup(timedelta(days=210))

        # Monthly rebalancing
        self.schedule.on(
            self.date_rules.month_start(0),
            self.time_rules.after_market_open(self.spy, 30),
            self.rebalance
        )

        # Daily risk check
        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.after_market_open(self.spy, 60),
            self.daily_risk_check
        )

    def is_bull_market(self) -> bool:
        if not self.spy_sma.is_ready:
            return False
        return self.securities[self.spy].price > self.spy_sma.current.value

    def is_stock_uptrending(self, symbol) -> bool:
        """Check if stock is above its 50 SMA"""
        if symbol not in self.stock_sma:
            return True
        sma = self.stock_sma[symbol]
        if not sma.is_ready:
            return True
        return self.securities[symbol].price > sma.current.value

    def daily_risk_check(self):
        """Exit stocks that drop too much from peak"""
        if self.is_warming_up:
            return

        for symbol in self.stocks:
            if not self.portfolio[symbol].invested:
                continue

            price = self.securities[symbol].price
            if price <= 0:
                continue

            # Track peak
            if symbol not in self.stock_peaks:
                self.stock_peaks[symbol] = price
            else:
                self.stock_peaks[symbol] = max(self.stock_peaks[symbol], price)

            # Check stop loss
            peak = self.stock_peaks[symbol]
            if price < peak * (1 - self.STOCK_STOP_LOSS):
                self.liquidate(symbol)
                self.log(f"STOP: {symbol.value} dropped {((peak-price)/peak)*100:.1f}% from peak")

    def rebalance(self):
        if self.is_warming_up:
            return

        # Bear market = go to cash
        if not self.is_bull_market():
            self.liquidate()
            self.stock_peaks = {}
            self.log("BEAR MARKET - Going to cash")
            return

        # Filter stocks that are uptrending
        uptrending = [s for s in self.stocks if self.is_stock_uptrending(s)]

        if len(uptrending) == 0:
            self.liquidate()
            return

        # Equal weight among uptrending stocks
        weight = self.LEVERAGE / len(uptrending)

        # Liquidate stocks no longer uptrending
        for symbol in self.stocks:
            if symbol not in uptrending and self.portfolio[symbol].invested:
                self.liquidate(symbol)
                if symbol in self.stock_peaks:
                    del self.stock_peaks[symbol]

        # Set holdings for uptrending stocks
        for symbol in uptrending:
            if self.securities[symbol].price > 0:
                self.set_holdings(symbol, weight)
                if symbol not in self.stock_peaks:
                    self.stock_peaks[symbol] = self.securities[symbol].price

        self.log(f"REBAL: {len(uptrending)} stocks uptrending")

    def on_data(self, data):
        pass
