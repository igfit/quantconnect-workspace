from AlgorithmImports import *

class DualFilterMomentum(QCAlgorithm):
    """
    Dual Filter Momentum - Double Protection for Lower DD

    THESIS:
    Single regime filter (SPY > 200 SMA) catches major bears but not all.
    Adding VIX filter catches volatility spikes BEFORE they become drawdowns.
    Double filter = lower DD with concentrated positions.

    FILTER LOGIC:
    - SPY > 200 SMA AND VIX < 25: 100% invested (8 positions)
    - SPY > 200 SMA AND VIX >= 25: 50% invested (4 positions)
    - SPY < 200 SMA: 100% cash

    WHY IT SHOULD WORK:
    - March 2020: VIX spiked to 80 BEFORE SPY broke 200 SMA
    - Having both filters catches more danger signals
    - When both green: concentrate for returns
    - When one yellow: reduce for safety

    TARGET: 28-32% CAGR, <25% DD, Sharpe > 0.95
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Quality universe (NO NVDA)
        self.tickers = [
            "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA",
            "AVGO", "CRM", "ORCL", "ADBE", "NFLX", "AMD",
            "JPM", "V", "MA", "UNH", "LLY", "COST",
            "CAT", "DE", "TXN", "QCOM", "GS", "HD"
        ]

        self.symbols = {}
        for ticker in self.tickers:
            try:
                self.symbols[ticker] = self.add_equity(ticker, Resolution.DAILY).symbol
            except:
                pass

        # VIX for volatility filter
        self.vix = self.add_data(CBOE, "VIX", Resolution.DAILY).symbol

        # Market regime filter
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.spy_sma200 = self.sma(self.spy, 200, Resolution.DAILY)

        # Momentum indicators
        self.momentum_ind = {}
        for ticker, symbol in self.symbols.items():
            self.momentum_ind[ticker] = self.momp(symbol, 126, Resolution.DAILY)

        self.sma50_ind = {}
        for ticker, symbol in self.symbols.items():
            self.sma50_ind[ticker] = self.sma(symbol, 50, Resolution.DAILY)

        self.vix_threshold = 25
        self.full_positions = 8
        self.reduced_positions = 4

        self.set_benchmark("SPY")

        self.schedule.on(
            self.date_rules.month_start(1),
            self.time_rules.after_market_open(self.spy, 30),
            self.rebalance
        )

        self.set_warm_up(210, Resolution.DAILY)

    def rebalance(self):
        if self.is_warming_up:
            return

        if not self.spy_sma200.is_ready:
            return

        # Get signals
        spy_price = self.securities[self.spy].price
        bull_market = spy_price > self.spy_sma200.current.value
        vix_value = self.securities[self.vix].price if self.securities[self.vix].price > 0 else 20
        low_vol = vix_value < self.vix_threshold

        # Determine position count based on filters
        if not bull_market:
            self.liquidate()
            self.debug(f"{self.time.date()}: BEAR - 100% Cash")
            return
        elif bull_market and low_vol:
            num_positions = self.full_positions
            self.debug(f"{self.time.date()}: BULL + LOW VOL - Full {num_positions} positions")
        else:  # bull but high vol
            num_positions = self.reduced_positions
            self.debug(f"{self.time.date()}: BULL + HIGH VOL - Reduced to {num_positions} positions")

        # Select candidates
        candidates = []
        for ticker, symbol in self.symbols.items():
            if ticker not in self.momentum_ind or ticker not in self.sma50_ind:
                continue
            if not self.momentum_ind[ticker].is_ready or not self.sma50_ind[ticker].is_ready:
                continue

            price = self.securities[symbol].price
            sma50 = self.sma50_ind[ticker].current.value
            momentum = self.momentum_ind[ticker].current.value

            if momentum > 0 and price > sma50:
                candidates.append({
                    'ticker': ticker,
                    'symbol': symbol,
                    'momentum': momentum
                })

        if len(candidates) < 3:
            self.liquidate()
            return

        sorted_candidates = sorted(candidates, key=lambda x: x['momentum'], reverse=True)
        top_stocks = sorted_candidates[:min(num_positions, len(sorted_candidates))]

        # Rebalance
        top_tickers = [s['ticker'] for s in top_stocks]
        for ticker, symbol in self.symbols.items():
            if ticker not in top_tickers and self.portfolio[symbol].invested:
                self.liquidate(symbol)

        weight = 0.95 / len(top_stocks)
        for stock in top_stocks:
            self.set_holdings(stock['symbol'], weight)

    def on_data(self, data):
        pass
