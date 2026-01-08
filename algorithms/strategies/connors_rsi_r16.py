# region imports
from AlgorithmImports import *
# endregion

class ConnorsRSIR16(QCAlgorithm):
    """
    Round 16 Strategy 3: Connors RSI (CRSI)

    Composite indicator: RSI(3) + UpDown RSI(2) + ROC Percentile(100)
    Uses extreme levels (10/90) instead of traditional 30/70.

    Research: 2.15% average 5-day return when CRSI < 5
    Source: Larry Connors / QuantifiedStrategies

    Signal: Buy when CRSI < 10, Exit when CRSI > 70
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Connors RSI parameters
        self.rsi_period = 3
        self.streak_period = 2
        self.roc_period = 100
        self.oversold = 10
        self.exit_level = 70

        self.tickers = [
            "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN", "TSLA",
            "AMD", "NFLX", "CRM", "ADBE", "AVGO",
            "JPM", "GS", "V", "MA",
            "UNH", "LLY", "JNJ",
            "CAT", "GE", "HON",
        ]

        self.symbols = {}
        self.rsi_ind = {}
        self.price_history = {}
        self.streak_history = {}
        self.roc_history = {}
        self.entry_prices = {}

        for ticker in self.tickers:
            equity = self.add_equity(ticker, Resolution.DAILY)
            equity.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
            sym = equity.symbol
            self.symbols[ticker] = sym

            # RSI(3) - short term
            self.rsi_ind[ticker] = self.rsi(sym, self.rsi_period, MovingAverageType.WILDERS, Resolution.DAILY)

            self.price_history[ticker] = []
            self.streak_history[ticker] = []
            self.roc_history[ticker] = []

        # Market regime
        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)

        self.max_positions = 8

        self.schedule.on(
            self.date_rules.every_day("SPY"),
            self.time_rules.after_market_open("SPY", 30),
            self.trade
        )

        self.set_benchmark("SPY")
        self.set_warm_up(150, Resolution.DAILY)

    def calculate_streak(self, prices):
        """Calculate consecutive up/down streak"""
        if len(prices) < 2:
            return 0

        streak = 0
        for i in range(len(prices) - 1, 0, -1):
            if prices[i] > prices[i-1]:
                if streak >= 0:
                    streak += 1
                else:
                    break
            elif prices[i] < prices[i-1]:
                if streak <= 0:
                    streak -= 1
                else:
                    break
            else:
                break
        return streak

    def calculate_streak_rsi(self, streaks):
        """Calculate RSI of streak values"""
        if len(streaks) < self.streak_period + 1:
            return None

        gains = []
        losses = []
        for i in range(1, len(streaks)):
            change = streaks[i] - streaks[i-1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))

        if len(gains) < self.streak_period:
            return None

        avg_gain = sum(gains[-self.streak_period:]) / self.streak_period
        avg_loss = sum(losses[-self.streak_period:]) / self.streak_period

        if avg_loss == 0:
            return 100
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def calculate_roc_percentile(self, roc_values):
        """Calculate percentile rank of current ROC"""
        if len(roc_values) < self.roc_period:
            return None

        current_roc = roc_values[-1]
        lookback = roc_values[-self.roc_period:]
        count_below = sum(1 for r in lookback if r < current_roc)
        return (count_below / self.roc_period) * 100

    def calculate_connors_rsi(self, ticker):
        """Calculate Connors RSI composite"""
        if not self.rsi_ind[ticker].is_ready:
            return None

        rsi3 = self.rsi_ind[ticker].current.value

        # Calculate streak RSI
        prices = self.price_history[ticker]
        if len(prices) < 10:
            return None

        streak = self.calculate_streak(prices)
        self.streak_history[ticker].append(streak)
        if len(self.streak_history[ticker]) > 150:
            self.streak_history[ticker] = self.streak_history[ticker][-150:]

        streak_rsi = self.calculate_streak_rsi(self.streak_history[ticker])
        if streak_rsi is None:
            return None

        # Calculate ROC percentile
        if len(prices) >= 2:
            roc = (prices[-1] - prices[-2]) / prices[-2] * 100
            self.roc_history[ticker].append(roc)
            if len(self.roc_history[ticker]) > 150:
                self.roc_history[ticker] = self.roc_history[ticker][-150:]

        roc_pct = self.calculate_roc_percentile(self.roc_history[ticker])
        if roc_pct is None:
            return None

        # Connors RSI = average of 3 components
        crsi = (rsi3 + streak_rsi + roc_pct) / 3
        return crsi

    def trade(self):
        if self.is_warming_up:
            return

        # Market regime filter
        spy_price = self.securities[self.spy].price
        if not self.spy_sma_200.is_ready or spy_price < self.spy_sma_200.current.value:
            return

        signals = []

        for ticker in self.tickers:
            symbol = self.symbols[ticker]
            price = self.securities[symbol].price

            if price <= 0:
                continue

            # Update price history
            self.price_history[ticker].append(price)
            if len(self.price_history[ticker]) > 150:
                self.price_history[ticker] = self.price_history[ticker][-150:]

            crsi = self.calculate_connors_rsi(ticker)
            if crsi is None:
                continue

            if ticker not in self.entry_prices:
                # Buy when extremely oversold
                if crsi < self.oversold:
                    signals.append({
                        "ticker": ticker,
                        "symbol": symbol,
                        "crsi": crsi,
                        "score": -crsi  # Lower CRSI = higher priority
                    })
            else:
                # Exit conditions
                should_exit = False
                reason = ""

                # Exit when CRSI recovers
                if crsi > self.exit_level:
                    should_exit = True
                    reason = f"CRSI_EXIT({crsi:.1f})"

                # Stop loss
                pnl = (price - self.entry_prices[ticker]) / self.entry_prices[ticker]
                if pnl <= -0.05:
                    should_exit = True
                    reason = f"STOP({pnl:.1%})"

                # Time-based exit (5 days max hold as per research)
                # We'll use a trailing approach instead

                if should_exit:
                    self.liquidate(symbol)
                    self.debug(f"{self.time.date()}: EXIT {ticker} {reason}")
                    del self.entry_prices[ticker]

        # Execute entries - prioritize most oversold
        signals.sort(key=lambda x: x["score"], reverse=True)
        current_positions = len(self.entry_prices)
        slots = self.max_positions - current_positions

        for s in signals[:slots]:
            ticker = s["ticker"]
            symbol = s["symbol"]
            price = self.securities[symbol].price
            weight = 1.0 / self.max_positions
            self.set_holdings(symbol, weight)
            self.entry_prices[ticker] = price
            self.debug(f"{self.time.date()}: ENTER {ticker} @ ${price:.2f} CRSI={s['crsi']:.1f}")
