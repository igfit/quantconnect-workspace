from AlgorithmImports import *

class RegimeConcentratedMomentum(QCAlgorithm):
    """
    Regime + Concentrated Momentum Strategy

    Thesis: Combine the two best-performing elements:
    1. Market Regime filter (SPY > 200 SMA) - gave best Sharpe (1.23) by avoiding bear markets
    2. Concentrated positions (Top 3) - gave highest returns (44%) by maximizing winner exposure

    Expected outcome: High returns WITH controlled drawdown.

    Rules:
    - Universe: Mega-cap tech stocks (INCLUDING NVDA for max returns)
    - Regime: Only invest when SPY > 200 SMA (bull market)
    - Selection: Top 3 stocks by 6-month momentum
    - Filter: Stock must be above its 50 SMA
    - Position: Equal weight (~33% each)
    - Exit: Go to cash when SPY < 200 SMA

    Edge: Best of both worlds - regime filter protects capital in bear markets,
    concentration captures maximum upside in bull markets.
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Universe - mega-caps INCLUDING NVDA (testing if it improves Sharpe)
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

        # Market regime indicator
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.spy_sma200 = self.sma(self.spy, 200, Resolution.DAILY)

        # Momentum indicators (126 days = 6 months)
        self.momentum_ind = {}
        for ticker, symbol in self.symbols.items():
            self.momentum_ind[ticker] = self.momp(symbol, 126, Resolution.DAILY)

        # 50-day SMA for stock trend filter
        self.sma50_ind = {}
        for ticker, symbol in self.symbols.items():
            self.sma50_ind[ticker] = self.sma(symbol, 50, Resolution.DAILY)

        # Concentration parameters
        self.top_n = 3  # High concentration for max returns

        # Set benchmark
        self.set_benchmark("SPY")

        # Monthly rebalance
        self.schedule.on(
            self.date_rules.month_start(1),
            self.time_rules.after_market_open(self.spy, 30),
            self.rebalance
        )

        # Warmup
        self.set_warm_up(210, Resolution.DAILY)

    def rebalance(self):
        if self.is_warming_up:
            return

        if not self.spy_sma200.is_ready:
            return

        # Check market regime
        spy_price = self.securities[self.spy].price
        bull_market = spy_price > self.spy_sma200.current.value

        if not bull_market:
            # Bear market - go to cash
            self.liquidate()
            self.debug(f"{self.time.date()}: BEAR MARKET - Going to cash (SPY={spy_price:.2f} < 200SMA={self.spy_sma200.current.value:.2f})")
            return

        # Bull market - select top momentum stocks
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
            self.debug(f"{self.time.date()}: Only {len(candidates)} candidates, need {self.top_n}")
            return

        # Sort by momentum, take top N
        sorted_candidates = sorted(candidates, key=lambda x: x['momentum'], reverse=True)
        top_stocks = sorted_candidates[:self.top_n]

        # Log selection
        self.debug(f"{self.time.date()}: BULL MARKET - Top {self.top_n} momentum:")
        for stock in top_stocks:
            self.debug(f"  {stock['ticker']}: {stock['momentum']:.1f}%")

        # Liquidate positions not in top stocks
        top_tickers = [s['ticker'] for s in top_stocks]
        for ticker, symbol in self.symbols.items():
            if ticker not in top_tickers and self.portfolio[symbol].invested:
                self.liquidate(symbol)

        # Equal weight concentrated positions
        weight = 0.95 / self.top_n
        for stock in top_stocks:
            self.set_holdings(stock['symbol'], weight)

    def on_data(self, data):
        pass
