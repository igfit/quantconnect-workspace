from AlgorithmImports import *

class IndicatorSqueezeMomentum(QCAlgorithm):
    """
    Squeeze Momentum Strategy (LazyBear / John Carter TTM Squeeze)

    SOURCE: John Carter's "Mastering the Trade" Chapter 11, popularized by LazyBear on TradingView

    CONCEPT:
    - "Squeeze" = Bollinger Bands are INSIDE Keltner Channel (low volatility)
    - After squeeze releases, price tends to make explosive move
    - Trade in direction of momentum when squeeze releases

    SIGNAL:
    - Enter when squeeze releases (BB expands outside KC)
    - Direction based on momentum (price vs 20-period mean)
    - Exit when momentum reverses OR new squeeze forms
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
        self.bb_ind = {}
        self.kc_ind = {}
        self.mom_ind = {}
        self.in_squeeze = {}
        self.in_position = {}
        self.position_direction = {}

        for ticker in self.basket:
            symbol = self.add_equity(ticker, Resolution.DAILY).symbol
            self.symbols[ticker] = symbol
            # Bollinger Bands (20, 2)
            self.bb_ind[ticker] = self.BB(symbol, 20, 2, MovingAverageType.SIMPLE, Resolution.DAILY)
            # Keltner Channel (20, 1.5) - using ATR
            self.kc_ind[ticker] = self.KCH(symbol, 20, 1.5, MovingAverageType.SIMPLE, Resolution.DAILY)
            # Momentum - simple: price vs 20 SMA
            self.mom_ind[ticker] = self.sma(symbol, 20)
            self.in_squeeze[ticker] = False
            self.in_position[ticker] = False
            self.position_direction[ticker] = 0

        self.set_benchmark("SPY")
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)
        self.set_warm_up(30, Resolution.DAILY)

    def on_data(self, data):
        if self.is_warming_up:
            return

        for ticker in self.basket:
            symbol = self.symbols[ticker]

            if symbol not in data.bars:
                continue

            if not all([self.bb_ind[ticker].is_ready,
                       self.kc_ind[ticker].is_ready,
                       self.mom_ind[ticker].is_ready]):
                continue

            price = data.bars[symbol].close

            # Bollinger Bands
            bb_upper = self.bb_ind[ticker].upper_band.current.value
            bb_lower = self.bb_ind[ticker].lower_band.current.value

            # Keltner Channel
            kc_upper = self.kc_ind[ticker].upper_band.current.value
            kc_lower = self.kc_ind[ticker].lower_band.current.value

            # Momentum direction
            sma20 = self.mom_ind[ticker].current.value
            momentum_up = price > sma20

            # Squeeze detection: BB inside KC
            currently_in_squeeze = (bb_lower > kc_lower) and (bb_upper < kc_upper)

            # Squeeze release: was in squeeze, now BB expanded outside KC
            squeeze_released = self.in_squeeze[ticker] and not currently_in_squeeze

            if squeeze_released and not self.in_position[ticker]:
                # Enter in direction of momentum
                if momentum_up:
                    self.set_holdings(symbol, self.weight_per_stock)
                    self.position_direction[ticker] = 1
                    self.in_position[ticker] = True
                    self.debug(f"BUY {ticker}: Squeeze released, momentum UP")
                else:
                    # For long-only, skip bearish signals
                    pass

            # Exit conditions
            elif self.in_position[ticker]:
                # Exit if momentum reverses OR new squeeze forms
                momentum_reversed = (self.position_direction[ticker] == 1 and not momentum_up)

                if momentum_reversed or currently_in_squeeze:
                    self.liquidate(symbol)
                    self.in_position[ticker] = False
                    self.position_direction[ticker] = 0
                    self.debug(f"SELL {ticker}: Momentum reversed or new squeeze")

            # Update squeeze state
            self.in_squeeze[ticker] = currently_in_squeeze
