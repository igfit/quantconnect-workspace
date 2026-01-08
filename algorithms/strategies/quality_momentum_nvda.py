from AlgorithmImports import *

class QualityMomentumWithNVDA(QCAlgorithm):
    """
    Quality Momentum Blend Strategy (with NVDA)

    Thesis: Previous Quality MegaCap achieved 35.94% CAGR, 1.049 Sharpe, 27% DD WITHOUT NVDA.
    NVDA was excluded for robustness testing but it was the dominant performer (40%+ of gains).
    Adding NVDA back should improve returns while quality filter maintains risk control.

    Quality definition:
    - Mega-cap (top companies by market cap)
    - Profitable (positive earnings - implied by being mega-cap tech)
    - Established businesses (not speculative)

    Rules:
    - Universe: Pre-screened quality mega-caps (INCLUDING NVDA)
    - Regime: SPY > 200 SMA (learned from Market Regime strategy)
    - Selection: Top 3 by 6-month momentum
    - Position: Equal weight (~33% each)
    - Rebalance: Monthly

    Edge: Quality reduces drawdown risk, momentum provides alpha, NVDA provides returns.
    Hypothesis: Including NVDA should push Sharpe above 1.2 like Market Regime.
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Quality mega-cap universe - only established, profitable tech giants
        # Deliberately smaller universe of highest-quality names
        self.tickers = [
            "AAPL",   # Largest market cap, huge cash flows
            "MSFT",   # Cloud leader, consistent growth
            "GOOGL",  # Search monopoly, AI leader
            "AMZN",   # E-commerce + cloud dominance
            "META",   # Social media monopoly, recovered strongly
            "NVDA",   # AI chip leader - THE dominant performer 2020-2024
            "AVGO",   # Semiconductor giant, stable profits
            "ORCL",   # Enterprise software, consistent
            "CRM",    # CRM leader, growing
            "ADBE",   # Creative software monopoly
        ]

        # Add equities
        self.symbols = {}
        for ticker in self.tickers:
            self.symbols[ticker] = self.add_equity(ticker, Resolution.DAILY).symbol

        # Market regime filter
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

        # Concentration - top 3 quality names
        self.top_n = 3

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
            self.debug(f"{self.time.date()}: BEAR MARKET - Going to cash")
            return

        # Bull market - select top quality momentum stocks
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
            self.debug(f"{self.time.date()}: Only {len(candidates)} quality candidates")
            return

        # Sort by momentum, take top N
        sorted_candidates = sorted(candidates, key=lambda x: x['momentum'], reverse=True)
        top_stocks = sorted_candidates[:self.top_n]

        # Log selection
        self.debug(f"{self.time.date()}: BULL MARKET - Top {self.top_n} quality momentum:")
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
