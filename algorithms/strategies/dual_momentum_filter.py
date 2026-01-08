from AlgorithmImports import *

class DualMomentumFilter(QCAlgorithm):
    """
    Dual Momentum Filter Strategy

    Thesis: Absolute momentum (trend) combined with relative momentum (outperformance)
    is more powerful than either alone. Absolute momentum confirms uptrend.
    Relative momentum confirms outperformance vs market.

    Rules:
    - Universe: Mega-cap tech stocks (excluding NVDA)
    - Entry: Buy only when BOTH conditions met:
      1. Absolute momentum: Price > Price 6 months ago
      2. Relative momentum: 6-month return > SPY 6-month return
    - Exit: Monthly rebalance - sell if either condition fails
    - Position: Equal weight top 5 passing dual filter
    - Safety: Go to cash if no stocks pass filter

    Edge: Double filter reduces false signals, only buys strongest uptrends.
    Based on Gary Antonacci's dual momentum research.
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Universe - mega-caps excluding NVDA
        self.tickers = [
            "AAPL", "MSFT", "GOOGL", "AMZN", "META",
            "TSLA", "AMD", "AVGO", "CRM", "ORCL",
            "ADBE", "NFLX", "CSCO", "INTC", "QCOM",
            "TXN", "IBM", "NOW", "UBER", "SHOP"
        ]

        # Add equities
        self.symbols = {}
        for ticker in self.tickers:
            self.symbols[ticker] = self.add_equity(ticker, Resolution.DAILY).symbol

        # SPY for relative momentum comparison
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol

        # 6-month momentum (126 trading days)
        self.momentum_ind = {}
        for ticker, symbol in self.symbols.items():
            self.momentum_ind[ticker] = self.momp(symbol, 126, Resolution.DAILY)

        # SPY momentum for relative comparison
        self.spy_momentum = self.momp(self.spy, 126, Resolution.DAILY)

        # Number of stocks to hold
        self.top_n = 5

        # Set benchmark
        self.set_benchmark("SPY")

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

        if not self.spy_momentum.is_ready:
            return

        spy_mom = self.spy_momentum.current.value

        # Find stocks passing dual momentum filter
        candidates = []
        for ticker, symbol in self.symbols.items():
            if not self.momentum_ind[ticker].is_ready:
                continue

            stock_mom = self.momentum_ind[ticker].current.value

            # Dual momentum filter:
            # 1. Absolute momentum: stock return > 0 (price higher than 6 months ago)
            # 2. Relative momentum: stock return > SPY return
            passes_absolute = stock_mom > 0
            passes_relative = stock_mom > spy_mom

            if passes_absolute and passes_relative:
                candidates.append({
                    'ticker': ticker,
                    'symbol': symbol,
                    'momentum': stock_mom,
                    'excess_return': stock_mom - spy_mom
                })

        self.debug(f"{self.time.date()}: SPY 6M momentum: {spy_mom:.2f}%")
        self.debug(f"{self.time.date()}: {len(candidates)} stocks pass dual momentum filter")

        # If no candidates, go to cash
        if len(candidates) == 0:
            self.liquidate()
            self.debug(f"{self.time.date()}: No candidates - going to cash")
            return

        # Sort by excess return (relative outperformance)
        sorted_candidates = sorted(candidates, key=lambda x: x['excess_return'], reverse=True)
        top_stocks = sorted_candidates[:min(self.top_n, len(sorted_candidates))]

        # Log selection
        self.debug(f"{self.time.date()}: Selected (dual momentum):")
        for stock in top_stocks:
            self.debug(f"  {stock['ticker']}: mom={stock['momentum']:.1f}%, excess={stock['excess_return']:.1f}%")

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
