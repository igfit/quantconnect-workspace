from AlgorithmImports import *

class QualityConcentrated10(QCAlgorithm):
    """
    Quality Concentrated 10 - Sweet Spot Between Concentration and Diversification

    THESIS:
    R6 (3 positions) = 40% CAGR, 45% DD
    R7 (20 positions) = 18% CAGR, 17% DD
    Target: 10 positions = ~30% CAGR, <30% DD

    WHY 10 POSITIONS:
    - Concentrated enough to capture winners (10% per position)
    - Diversified enough that one stock crashing doesn't kill portfolio
    - Quality filter ensures no junk stocks that could blow up

    RULES:
    - Universe: 25 highest-quality mega-caps (NO NVDA)
    - Selection: Top 10 by 6-month momentum
    - Filter: Price > 50 SMA (uptrend)
    - Regime: SPY > 200 SMA (bull market only)
    - Position: Equal weight ~10% each

    TARGET: 28-32% CAGR, <28% DD, Sharpe > 0.9
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Quality universe - only blue-chip mega-caps (NO NVDA)
        self.tickers = [
            # Tech giants
            "AAPL", "MSFT", "GOOGL", "AMZN", "META", "CRM", "ADBE", "ORCL",
            # Quality semis (no NVDA)
            "AVGO", "TXN", "QCOM",
            # Consumer/Internet
            "TSLA", "NFLX", "COST", "HD",
            # Finance (quality)
            "JPM", "V", "MA", "GS",
            # Healthcare
            "UNH", "LLY", "ABBV",
            # Industrial
            "CAT", "DE", "HON"
        ]

        self.symbols = {}
        for ticker in self.tickers:
            try:
                self.symbols[ticker] = self.add_equity(ticker, Resolution.DAILY).symbol
            except:
                pass

        # Market regime filter
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.spy_sma200 = self.sma(self.spy, 200, Resolution.DAILY)

        # Momentum indicators
        self.momentum_ind = {}
        for ticker, symbol in self.symbols.items():
            self.momentum_ind[ticker] = self.momp(symbol, 126, Resolution.DAILY)

        # Trend filter
        self.sma50_ind = {}
        for ticker, symbol in self.symbols.items():
            self.sma50_ind[ticker] = self.sma(symbol, 50, Resolution.DAILY)

        # KEY: 10 positions for balance
        self.top_n = 10

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

        # Regime filter
        spy_price = self.securities[self.spy].price
        bull_market = spy_price > self.spy_sma200.current.value

        if not bull_market:
            self.liquidate()
            self.debug(f"{self.time.date()}: BEAR - Cash")
            return

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

        if len(candidates) < 5:
            self.liquidate()
            return

        sorted_candidates = sorted(candidates, key=lambda x: x['momentum'], reverse=True)
        top_stocks = sorted_candidates[:min(self.top_n, len(sorted_candidates))]

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
