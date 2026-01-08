from AlgorithmImports import *

class SignalEqualWeightMomentum(QCAlgorithm):
    """
    SIGNAL-DRIVEN Strategy 4: Equal Weight Momentum

    THESIS: Apply momentum signal to broad universe, but EQUAL weight
    all positions so no single stock can dominate returns.

    WHY THIS IS SIGNAL-DRIVEN:
    - 50 stocks, each max 5% of portfolio
    - Same momentum signal applied to all
    - If signal works, returns spread across many names
    - No single stock can be >5% of P&L

    Signal: 3-month momentum > 0, price > 50 SMA
    Position: Equal weight top 20 stocks (5% each)
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100000)

        # Broad universe - S&P 100 components (large, liquid)
        self.universe_tickers = [
            # Tech
            "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "AVGO", "ORCL", "CRM", "ADBE",
            "CSCO", "ACN", "IBM", "INTC", "AMD", "TXN", "QCOM", "INTU", "NOW", "AMAT",
            # Financials
            "JPM", "BAC", "WFC", "GS", "MS", "BLK", "SCHW", "C", "AXP", "V", "MA",
            # Healthcare
            "UNH", "JNJ", "PFE", "ABBV", "MRK", "LLY", "TMO", "ABT", "BMY", "AMGN",
            # Consumer
            "WMT", "HD", "MCD", "NKE", "SBUX", "TGT", "LOW", "COST", "PG", "KO", "PEP",
            # Industrials
            "CAT", "DE", "GE", "HON", "BA", "UPS", "RTX", "LMT", "MMM",
            # Energy/Materials
            "XOM", "CVX", "COP", "SLB", "LIN", "APD",
            # Other
            "DIS", "NFLX", "CMCSA", "T", "VZ"
        ]

        self.symbols = {}
        self.momentum_ind = {}
        self.sma50_ind = {}

        for ticker in self.universe_tickers:
            try:
                symbol = self.add_equity(ticker, Resolution.DAILY).symbol
                self.symbols[ticker] = symbol
                self.momentum_ind[ticker] = self.momp(symbol, 63, Resolution.DAILY)
                self.sma50_ind[ticker] = self.sma(symbol, 50)
            except:
                pass

        # Market regime
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.spy_sma200 = self.sma(self.spy, 200)

        self.set_benchmark("SPY")
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)

        # Monthly rebalance
        self.schedule.on(
            self.date_rules.month_start("SPY"),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )

        self.set_warm_up(210, Resolution.DAILY)

        # Position sizing - EQUAL WEIGHT is key
        self.num_positions = 20
        self.weight_per_stock = 1.0 / self.num_positions  # 5% each

    def rebalance(self):
        if self.is_warming_up:
            return

        if not self.spy_sma200.is_ready:
            return

        # Market regime
        spy_price = self.securities[self.spy].price
        bull_market = spy_price > self.spy_sma200.current.value

        if not bull_market:
            self.liquidate()
            return

        # Rank by momentum
        candidates = []
        for ticker in self.symbols.keys():
            if ticker not in self.momentum_ind or ticker not in self.sma50_ind:
                continue
            if not self.momentum_ind[ticker].is_ready or not self.sma50_ind[ticker].is_ready:
                continue

            symbol = self.symbols[ticker]
            price = self.securities[symbol].price
            if not price or price <= 0:
                continue

            momentum = self.momentum_ind[ticker].current.value
            sma50 = self.sma50_ind[ticker].current.value

            # Entry criteria: positive momentum + above SMA
            if momentum > 0 and price > sma50:
                candidates.append({'ticker': ticker, 'momentum': momentum})

        candidates.sort(key=lambda x: x['momentum'], reverse=True)

        # Select top N, EQUAL WEIGHT
        target_holdings = {}
        for c in candidates[:self.num_positions]:
            target_holdings[c['ticker']] = self.weight_per_stock

        # Liquidate non-targets
        for holding in self.portfolio.Values:
            if holding.invested and holding.symbol.value not in target_holdings:
                self.liquidate(holding.symbol)

        # Rebalance to EQUAL weight
        for ticker, weight in target_holdings.items():
            symbol = self.symbols[ticker]
            self.set_holdings(symbol, weight)
