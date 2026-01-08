from AlgorithmImports import *

class VixFilteredMomentum(QCAlgorithm):
    """
    VIX-Filtered Momentum Strategy

    Thesis: High VIX = market stress = momentum reversals and whipsaws.
    Low VIX = complacency = trends persist and momentum works.
    Only trade momentum when conditions favor it.

    Historical context:
    - March 2020: VIX spiked to 80+, momentum collapsed
    - 2022 bear: VIX elevated (25-35), momentum strategies suffered
    - Bull markets: VIX typically 12-20, momentum thrives

    Rules:
    - Universe: Mega-cap stocks (including NVDA)
    - VIX Filter: Only invest when VIX < 25
    - Selection: Top 5 stocks by 6-month momentum
    - Exit: Go to cash when VIX > 25
    - Rebalance: Monthly when invested

    Edge: Avoids momentum crashes during volatility spikes.
    Momentum strategies fail when correlations spike (high VIX).
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

        # VIX for volatility filter
        self.vix = self.add_data(CBOE, "VIX", Resolution.DAILY).symbol

        # Momentum indicators (126 days = 6 months)
        self.momentum_ind = {}
        for ticker, symbol in self.symbols.items():
            self.momentum_ind[ticker] = self.momp(symbol, 126, Resolution.DAILY)

        # 50-day SMA for stock trend filter
        self.sma50_ind = {}
        for ticker, symbol in self.symbols.items():
            self.sma50_ind[ticker] = self.sma(symbol, 50, Resolution.DAILY)

        # VIX threshold
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

        # Get VIX value
        vix_value = self.securities[self.vix].price if self.securities[self.vix].price > 0 else 20

        # Check VIX filter
        low_volatility = vix_value < self.vix_threshold

        if not low_volatility:
            # High VIX - go to cash
            self.liquidate()
            self.debug(f"{self.time.date()}: HIGH VIX ({vix_value:.1f} > {self.vix_threshold}) - Going to cash")
            return

        # Low VIX - trade momentum
        candidates = []
        for ticker, symbol in self.symbols.items():
            if not self.momentum_ind[ticker].is_ready or not self.sma50_ind[ticker].is_ready:
                continue

            price = self.securities[symbol].price
            sma50 = self.sma50_ind[ticker].current.value
            momentum = self.momentum_ind[ticker].current.value

            # Filter: price above 50 SMA (uptrend)
            if price > sma50:
                candidates.append({
                    'ticker': ticker,
                    'symbol': symbol,
                    'momentum': momentum
                })

        if len(candidates) < self.top_n:
            return

        # Sort by momentum, take top N
        sorted_candidates = sorted(candidates, key=lambda x: x['momentum'], reverse=True)
        top_stocks = sorted_candidates[:self.top_n]

        # Log selection
        self.debug(f"{self.time.date()}: LOW VIX ({vix_value:.1f}) - Top {self.top_n}:")
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
