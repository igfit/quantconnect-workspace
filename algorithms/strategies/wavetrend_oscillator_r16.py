# region imports
from AlgorithmImports import *
# endregion

class WaveTrendOscillatorR16(QCAlgorithm):
    """
    Round 16 Strategy 1: WaveTrend Oscillator

    Based on LazyBear's TradingView indicator - combines EMA smoothing
    with channel normalization for cleaner momentum signals.

    Signal: Buy when WT1 crosses above WT2 in oversold zone (<-53)
    Exit: When WT1 crosses below WT2 in overbought zone (>53)

    Research source: TradingView community scripts
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # WaveTrend parameters
        self.channel_length = 10  # n1
        self.average_length = 21  # n2
        self.ob_level = 53        # overbought
        self.os_level = -53       # oversold

        self.tickers = [
            "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN", "TSLA",
            "AMD", "NFLX", "CRM", "ADBE", "AVGO",
            "JPM", "GS", "V", "MA",
            "UNH", "LLY", "JNJ",
            "CAT", "GE", "HON",
        ]

        self.symbols = {}
        self.hlc3 = {}  # (H+L+C)/3
        self.ema_hlc3 = {}  # EMA of HLC3
        self.ema_diff = {}  # EMA of |HLC3 - EMA_HLC3|
        self.wt1 = {}  # WaveTrend line 1
        self.wt2 = {}  # WaveTrend line 2 (SMA of WT1)
        self.prev_wt1 = {}
        self.prev_wt2 = {}

        # For manual calculation
        self.price_history = {}
        self.wt1_history = {}

        for ticker in self.tickers:
            equity = self.add_equity(ticker, Resolution.DAILY)
            equity.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
            sym = equity.symbol
            self.symbols[ticker] = sym
            self.price_history[ticker] = []
            self.wt1_history[ticker] = []
            self.prev_wt1[ticker] = None
            self.prev_wt2[ticker] = None

        # Market regime filter
        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)

        # Position tracking
        self.entry_prices = {}
        self.max_positions = 6

        self.schedule.on(
            self.date_rules.every_day("SPY"),
            self.time_rules.after_market_open("SPY", 30),
            self.trade
        )

        self.set_benchmark("SPY")
        self.set_warm_up(100, Resolution.DAILY)

    def calculate_wavetrend(self, ticker):
        """Calculate WaveTrend values manually"""
        if len(self.price_history[ticker]) < self.channel_length + self.average_length:
            return None, None

        prices = self.price_history[ticker]

        # EMA of HLC3 (channel_length)
        ema_hlc3 = self._ema(prices, self.channel_length)
        if ema_hlc3 is None:
            return None, None

        # Calculate differences |HLC3 - EMA_HLC3|
        diffs = []
        ema_vals = self._ema_series(prices, self.channel_length)
        if ema_vals is None:
            return None, None

        for i in range(len(prices)):
            if i < self.channel_length - 1:
                continue
            diff = abs(prices[i] - ema_vals[i - self.channel_length + 1])
            diffs.append(diff)

        if len(diffs) < self.channel_length:
            return None, None

        # EMA of differences
        ema_diff = self._ema(diffs, self.channel_length)
        if ema_diff is None or ema_diff == 0:
            return None, None

        # CI (Channel Index)
        ci = (prices[-1] - ema_hlc3) / (0.015 * ema_diff)

        # WT1 = EMA of CI (average_length)
        # For simplicity, we'll use a rolling approach
        self.wt1_history[ticker].append(ci)
        if len(self.wt1_history[ticker]) > 100:
            self.wt1_history[ticker] = self.wt1_history[ticker][-100:]

        if len(self.wt1_history[ticker]) < self.average_length:
            return None, None

        wt1 = self._ema(self.wt1_history[ticker], self.average_length)

        # WT2 = SMA of WT1 (4 periods)
        if len(self.wt1_history[ticker]) >= 4:
            wt2 = sum(self.wt1_history[ticker][-4:]) / 4
        else:
            wt2 = wt1

        return wt1, wt2

    def _ema(self, data, period):
        """Calculate EMA of data"""
        if len(data) < period:
            return None
        k = 2 / (period + 1)
        ema = sum(data[:period]) / period
        for val in data[period:]:
            ema = val * k + ema * (1 - k)
        return ema

    def _ema_series(self, data, period):
        """Calculate EMA series"""
        if len(data) < period:
            return None
        k = 2 / (period + 1)
        ema = sum(data[:period]) / period
        result = [ema]
        for val in data[period:]:
            ema = val * k + ema * (1 - k)
            result.append(ema)
        return result

    def trade(self):
        if self.is_warming_up:
            return

        # Market regime filter
        spy_price = self.securities[self.spy].price
        if not self.spy_sma_200.is_ready or spy_price < self.spy_sma_200.current.value:
            return

        # Update price history and calculate signals
        signals = []

        for ticker in self.tickers:
            symbol = self.symbols[ticker]
            if symbol not in self.securities or self.securities[symbol].price <= 0:
                continue

            bar = self.securities[symbol]
            hlc3 = (bar.high + bar.low + bar.close) / 3
            self.price_history[ticker].append(hlc3)

            if len(self.price_history[ticker]) > 100:
                self.price_history[ticker] = self.price_history[ticker][-100:]

            wt1, wt2 = self.calculate_wavetrend(ticker)
            if wt1 is None:
                continue

            prev_wt1 = self.prev_wt1[ticker]
            prev_wt2 = self.prev_wt2[ticker]

            # Check for crossover signals
            if prev_wt1 is not None and prev_wt2 is not None:
                # Buy signal: WT1 crosses above WT2 in oversold zone
                if prev_wt1 <= prev_wt2 and wt1 > wt2 and wt1 < self.os_level:
                    if ticker not in self.entry_prices:
                        signals.append({
                            "ticker": ticker,
                            "symbol": symbol,
                            "action": "buy",
                            "wt1": wt1,
                            "score": abs(wt1)  # More oversold = higher score
                        })

                # Sell signal: WT1 crosses below WT2 in overbought zone
                if prev_wt1 >= prev_wt2 and wt1 < wt2 and wt1 > self.ob_level:
                    if ticker in self.entry_prices:
                        self.liquidate(symbol)
                        self.debug(f"{self.time.date()}: EXIT {ticker} WT_OB (wt1={wt1:.1f})")
                        del self.entry_prices[ticker]

            # Also exit on stop loss
            if ticker in self.entry_prices:
                pnl = (bar.close - self.entry_prices[ticker]) / self.entry_prices[ticker]
                if pnl <= -0.07:
                    self.liquidate(symbol)
                    self.debug(f"{self.time.date()}: EXIT {ticker} STOP ({pnl:.1%})")
                    del self.entry_prices[ticker]

            self.prev_wt1[ticker] = wt1
            self.prev_wt2[ticker] = wt2

        # Execute buy signals
        signals.sort(key=lambda x: x["score"], reverse=True)
        current_positions = len(self.entry_prices)
        slots = self.max_positions - current_positions

        for s in signals[:slots]:
            if s["action"] == "buy":
                ticker = s["ticker"]
                symbol = s["symbol"]
                price = self.securities[symbol].price
                weight = 1.0 / self.max_positions
                self.set_holdings(symbol, weight)
                self.entry_prices[ticker] = price
                self.debug(f"{self.time.date()}: ENTER {ticker} @ ${price:.2f} (wt1={s['wt1']:.1f})")
