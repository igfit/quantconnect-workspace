from AlgorithmImports import *

class IndicatorSupertrend(QCAlgorithm):
    """
    Supertrend Indicator Strategy

    SOURCE: Taiwan backtest showed 25.88% annualized return, Sharpe 1.84
    NOTE: Research says weekly timeframe works best for stocks

    CONCEPT:
    - Supertrend = ATR-based trend following indicator
    - Upper band = (High + Low)/2 + Multiplier * ATR
    - Lower band = (High + Low)/2 - Multiplier * ATR
    - When price > upper band, trend is UP
    - When price < lower band, trend is DOWN

    SIGNAL:
    - Buy when price crosses above Supertrend line
    - Sell when price crosses below Supertrend line
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100000)

        # 25-stock basket
        self.basket = [
            "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA",
            "AVGO", "AMD", "NFLX", "CRM", "NOW", "ADBE", "ORCL",
            "V", "MA", "JPM", "GS",
            "LLY", "UNH", "ABBV",
            "COST", "HD", "CAT", "GE", "HON"
        ]

        self.weight_per_stock = 0.04

        self.symbols = {}
        self.atr_ind = {}
        self.in_position = {}
        self.supertrend = {}
        self.trend_direction = {}  # 1 = up, -1 = down

        # Supertrend parameters
        self.atr_period = 10
        self.multiplier = 3.0

        for ticker in self.basket:
            symbol = self.add_equity(ticker, Resolution.DAILY).symbol
            self.symbols[ticker] = symbol
            self.atr_ind[ticker] = self.atr(symbol, self.atr_period, MovingAverageType.SIMPLE, Resolution.DAILY)
            self.in_position[ticker] = False
            self.supertrend[ticker] = 0
            self.trend_direction[ticker] = 1

        self.set_benchmark("SPY")
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)
        self.set_warm_up(30, Resolution.DAILY)

        # Store previous values for crossover detection
        self.prev_close = {}
        self.prev_supertrend = {}

    def on_data(self, data):
        if self.is_warming_up:
            return

        for ticker in self.basket:
            symbol = self.symbols[ticker]

            if symbol not in data.bars:
                continue

            if not self.atr_ind[ticker].is_ready:
                continue

            bar = data.bars[symbol]
            close = bar.close
            high = bar.high
            low = bar.low
            atr = self.atr_ind[ticker].current.value

            # Calculate Supertrend
            hl2 = (high + low) / 2
            upper_band = hl2 + (self.multiplier * atr)
            lower_band = hl2 - (self.multiplier * atr)

            # Supertrend logic
            prev_st = self.supertrend[ticker]
            prev_dir = self.trend_direction[ticker]

            if prev_st == 0:
                # Initialize
                self.supertrend[ticker] = lower_band if close > hl2 else upper_band
                self.trend_direction[ticker] = 1 if close > hl2 else -1
                self.prev_close[ticker] = close
                continue

            # Update Supertrend
            if prev_dir == 1:  # Was in uptrend
                new_lower = max(lower_band, prev_st) if close > prev_st else lower_band
                if close < prev_st:
                    # Trend flipped to down
                    self.supertrend[ticker] = upper_band
                    self.trend_direction[ticker] = -1
                else:
                    self.supertrend[ticker] = new_lower
                    self.trend_direction[ticker] = 1
            else:  # Was in downtrend
                new_upper = min(upper_band, prev_st) if close < prev_st else upper_band
                if close > prev_st:
                    # Trend flipped to up
                    self.supertrend[ticker] = lower_band
                    self.trend_direction[ticker] = 1
                else:
                    self.supertrend[ticker] = new_upper
                    self.trend_direction[ticker] = -1

            curr_dir = self.trend_direction[ticker]

            # Trading signals based on trend direction change
            if curr_dir == 1 and prev_dir == -1 and not self.in_position[ticker]:
                # Trend flipped UP - BUY
                self.set_holdings(symbol, self.weight_per_stock)
                self.in_position[ticker] = True
                self.debug(f"BUY {ticker}: Supertrend flipped UP at {close:.2f}")

            elif curr_dir == -1 and prev_dir == 1 and self.in_position[ticker]:
                # Trend flipped DOWN - SELL
                self.liquidate(symbol)
                self.in_position[ticker] = False
                self.debug(f"SELL {ticker}: Supertrend flipped DOWN at {close:.2f}")

            self.prev_close[ticker] = close
