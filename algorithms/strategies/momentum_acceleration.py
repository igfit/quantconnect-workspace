from AlgorithmImports import *

class MomentumAcceleration(QCAlgorithm):
    """
    Momentum Acceleration Strategy

    Thesis: Standard momentum is a lagging indicator - it buys AFTER the move started.
    Stocks that are ACCELERATING (momentum increasing) are in the early/mid phase of their move.
    Stocks with decelerating momentum are nearing the end of their run.

    Acceleration signal:
    - Current 3-month momentum > 3-month momentum from 1 month ago
    - This means the rate of price increase is itself increasing

    Rules:
    - Universe: Mega-cap stocks (including NVDA)
    - Entry:
      1. Positive momentum (3-month return > 0)
      2. Accelerating momentum (current mom > mom 21 days ago)
      3. Price > 50 SMA
    - Selection: Top 5 by momentum acceleration rate
    - Rebalance: Monthly

    Edge: Earlier entry into trends, exit before momentum fades.
    Catches the "sweet spot" of momentum - after confirmation but before exhaustion.
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

        # 3-month momentum (63 trading days)
        self.momentum_ind = {}
        for ticker, symbol in self.symbols.items():
            self.momentum_ind[ticker] = self.momp(symbol, 63, Resolution.DAILY)

        # Rolling window to track momentum history (for acceleration)
        self.momentum_history = {}
        for ticker in self.tickers:
            self.momentum_history[ticker] = RollingWindow[float](25)  # ~1 month of history

        # 50-day SMA for trend filter
        self.sma50_ind = {}
        for ticker, symbol in self.symbols.items():
            self.sma50_ind[ticker] = self.sma(symbol, 50, Resolution.DAILY)

        # Number of stocks to hold
        self.top_n = 5

        # Set benchmark
        self.set_benchmark("SPY")
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol

        # Daily update for momentum history
        self.schedule.on(
            self.date_rules.every_day(self.spy),
            self.time_rules.after_market_open(self.spy, 5),
            self.update_momentum_history
        )

        # Monthly rebalance
        self.schedule.on(
            self.date_rules.month_start(1),
            self.time_rules.after_market_open(self.spy, 30),
            self.rebalance
        )

        # Warmup
        self.set_warm_up(100, Resolution.DAILY)

    def update_momentum_history(self):
        """Track momentum values daily to calculate acceleration"""
        if self.is_warming_up:
            return

        for ticker in self.tickers:
            if self.momentum_ind[ticker].is_ready:
                self.momentum_history[ticker].add(self.momentum_ind[ticker].current.value)

    def rebalance(self):
        if self.is_warming_up:
            return

        candidates = []
        for ticker, symbol in self.symbols.items():
            # Check indicators ready
            if not self.momentum_ind[ticker].is_ready or not self.sma50_ind[ticker].is_ready:
                continue

            # Need enough history for acceleration calc
            if not self.momentum_history[ticker].is_ready:
                continue

            price = self.securities[symbol].price
            sma50 = self.sma50_ind[ticker].current.value
            current_mom = self.momentum_ind[ticker].current.value

            # Get momentum from ~21 days ago (index 20 in 0-indexed window)
            past_mom = self.momentum_history[ticker][20] if self.momentum_history[ticker].count > 20 else current_mom

            # Calculate acceleration (change in momentum)
            acceleration = current_mom - past_mom

            # Filter criteria:
            # 1. Positive momentum
            # 2. Accelerating (momentum increasing)
            # 3. Price above 50 SMA
            if current_mom > 0 and acceleration > 0 and price > sma50:
                candidates.append({
                    'ticker': ticker,
                    'symbol': symbol,
                    'momentum': current_mom,
                    'acceleration': acceleration
                })

        if len(candidates) == 0:
            self.debug(f"{self.time.date()}: No accelerating stocks found")
            # Keep existing positions or go to cash
            return

        # Sort by acceleration (momentum increase), take top N
        sorted_candidates = sorted(candidates, key=lambda x: x['acceleration'], reverse=True)
        top_stocks = sorted_candidates[:min(self.top_n, len(sorted_candidates))]

        # Log selection
        self.debug(f"{self.time.date()}: Top accelerating stocks:")
        for stock in top_stocks:
            self.debug(f"  {stock['ticker']}: mom={stock['momentum']:.1f}%, accel={stock['acceleration']:.1f}%")

        # Liquidate positions not in top stocks
        top_tickers = [s['ticker'] for s in top_stocks]
        for ticker, symbol in self.symbols.items():
            if ticker not in top_tickers and self.portfolio[symbol].invested:
                self.liquidate(symbol)

        # Equal weight
        weight = 0.95 / len(top_stocks)
        for stock in top_stocks:
            self.set_holdings(stock['symbol'], weight)

    def on_data(self, data):
        pass
