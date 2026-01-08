from AlgorithmImports import *

class AdaptiveLookbackMomentum(QCAlgorithm):
    """
    Adaptive Lookback Momentum Strategy

    Thesis: Fixed lookback periods are suboptimal. Market conditions vary:
    - High volatility: Trends change quickly, need shorter lookback to react
    - Low volatility: Trends persist, longer lookback reduces noise

    The VIX is a proxy for market regime:
    - VIX > 25: High volatility -> use 3-month momentum (63 days)
    - VIX < 25: Low volatility -> use 6-month momentum (126 days)

    Why this should work:
    - In calm markets (low VIX), 6-month momentum captures sustained trends
    - In volatile markets (high VIX), 3-month reacts faster to regime changes
    - Adapts signal to market conditions rather than fixed parameters

    Rules:
    - Universe: Mega-cap stocks (including NVDA)
    - Lookback: Adaptive based on VIX
    - Selection: Top 5 by momentum
    - Filter: Price > 50 SMA
    - Rebalance: Monthly

    Edge: Parameter adaptation reduces whipsaw in volatile periods,
    captures full moves in trending periods.
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Universe - mega-caps including NVDA
        self.tickers = [
            "AAPL", "MSFT", "GOOGL", "AMZN", "META",
            "NVDA", "TSLA", "AMD", "AVGO", "CRM",
            "ORCL", "ADBE", "NFLX", "CSCO", "INTC",
            "QCOM", "TXN", "NOW", "UBER", "SHOP"
        ]

        # Add equities
        self.symbols = {}
        for ticker in self.tickers:
            self.symbols[ticker] = self.add_equity(ticker, Resolution.DAILY).symbol

        # VIX for regime detection
        self.vix = self.add_data(CBOE, "VIX", Resolution.DAILY).symbol

        # Two momentum indicators per stock (short and long lookback)
        self.momentum_short = {}  # 3-month (63 days)
        self.momentum_long = {}   # 6-month (126 days)
        for ticker, symbol in self.symbols.items():
            self.momentum_short[ticker] = self.momp(symbol, 63, Resolution.DAILY)
            self.momentum_long[ticker] = self.momp(symbol, 126, Resolution.DAILY)

        # 50-day SMA for stock trend filter
        self.sma50_ind = {}
        for ticker, symbol in self.symbols.items():
            self.sma50_ind[ticker] = self.sma(symbol, 50, Resolution.DAILY)

        # VIX threshold for regime switch
        self.vix_threshold = 25

        # Number of stocks to hold
        self.top_n = 5

        # Set benchmark
        self.set_benchmark("SPY")
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol

        # Monthly rebalance
        self.schedule.on(
            self.date_rules.month_start(1),
            self.time_rules.after_market_open(self.spy, 30),
            self.rebalance
        )

        # Warmup
        self.set_warm_up(140, Resolution.DAILY)

    def rebalance(self):
        if self.is_warming_up:
            return

        # Get VIX value to determine lookback
        vix_value = self.securities[self.vix].price if self.securities[self.vix].price > 0 else 20

        # Adaptive lookback selection
        use_short_lookback = vix_value > self.vix_threshold
        lookback_name = "3-month" if use_short_lookback else "6-month"

        self.debug(f"{self.time.date()}: VIX={vix_value:.1f}, using {lookback_name} momentum")

        # Select appropriate momentum indicator
        momentum_dict = self.momentum_short if use_short_lookback else self.momentum_long

        candidates = []
        for ticker, symbol in self.symbols.items():
            if not momentum_dict[ticker].is_ready or not self.sma50_ind[ticker].is_ready:
                continue

            price = self.securities[symbol].price
            sma50 = self.sma50_ind[ticker].current.value
            momentum = momentum_dict[ticker].current.value

            # Filter: price above 50 SMA (uptrend)
            if price > sma50:
                candidates.append({
                    'ticker': ticker,
                    'symbol': symbol,
                    'momentum': momentum
                })

        if len(candidates) < self.top_n:
            self.debug(f"{self.time.date()}: Only {len(candidates)} candidates")
            return

        # Sort by momentum, take top N
        sorted_candidates = sorted(candidates, key=lambda x: x['momentum'], reverse=True)
        top_stocks = sorted_candidates[:self.top_n]

        # Log selection
        self.debug(f"{self.time.date()}: Top {self.top_n} ({lookback_name}):")
        for stock in top_stocks:
            self.debug(f"  {stock['ticker']}: {stock['momentum']:.1f}%")

        # Liquidate positions not in top stocks
        top_tickers = [s['ticker'] for s in top_stocks]
        for ticker, symbol in self.symbols.items():
            if ticker not in top_tickers and self.portfolio[symbol].invested:
                self.liquidate(symbol)

        # Equal weight
        weight = 0.95 / self.top_n
        for stock in top_stocks:
            self.set_holdings(stock['symbol'], weight)

    def on_data(self, data):
        pass
