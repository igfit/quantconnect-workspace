from AlgorithmImports import *

class DiversifiedMomentumWithCaps(QCAlgorithm):
    """
    Diversified Momentum with Hard Position Caps

    THESIS: Simple approach - just enforce hard position caps
    and hold more stocks to spread risk.

    WHY THIS WORKS:
    - Max 10% per position limits any single-stock impact
    - 10 positions required = forced diversification
    - Still captures momentum alpha
    - Simple rules = robust performance

    RULES:
    - Universe: 25 mega/large caps across sectors
    - Filter: 6-month momentum > 0, Price > 50 SMA
    - Select: Top 10 by momentum
    - Weight: 10% each (hard cap)
    - Regime: SPY > 200 SMA
    - Rebalance: Monthly

    EDGE: Simplicity. Most concentration issues are solved
    by just holding more stocks with equal weight.

    EXPECTED: Lower returns than concentrated strategies,
    but much better risk profile and diversification.
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Broader universe: 25 stocks across sectors
        self.tickers = [
            # Tech (7)
            "AAPL", "MSFT", "NVDA", "AVGO", "CRM", "ORCL", "ADBE",
            # Consumer (4)
            "AMZN", "TSLA", "HD", "COST",
            # Communications (3)
            "META", "GOOGL", "NFLX",
            # Healthcare (4)
            "UNH", "JNJ", "LLY", "ABBV",
            # Financials (4)
            "JPM", "V", "MA", "GS",
            # Industrials (3)
            "CAT", "HON", "UPS"
        ]

        # Add equities
        self.symbols = {}
        for ticker in self.tickers:
            equity = self.add_equity(ticker, Resolution.DAILY)
            equity.set_leverage(1.0)
            self.symbols[ticker] = equity.symbol

        # SPY for regime
        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.set_benchmark("SPY")

        # Indicators
        self.momentum = {}
        self.sma50 = {}

        for ticker, symbol in self.symbols.items():
            self.momentum[ticker] = self.momp(symbol, 126)  # 6-month
            self.sma50[ticker] = self.sma(symbol, 50)

        # Market regime
        self.spy_sma200 = self.sma(self.spy, 200)

        # Settings - enforced diversification
        self.target_positions = 10  # Must hold 10 stocks
        self.max_weight = 0.10  # 10% max per position

        # Monthly rebalance
        self.schedule.on(
            self.date_rules.month_start(5),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )

        # Warmup
        self.set_warm_up(timedelta(days=210))

    def rebalance(self):
        if self.is_warming_up:
            return

        # Check market regime
        if not self.spy_sma200.is_ready:
            return

        spy_price = self.securities[self.spy].price
        spy_sma = self.spy_sma200.current.value

        if spy_price < spy_sma:
            self.log(f"BEAR MARKET: SPY ({spy_price:.2f}) < 200 SMA. Cash.")
            self.liquidate()
            return

        # Calculate momentum scores
        candidates = []

        for ticker, symbol in self.symbols.items():
            if not self.securities[symbol].is_tradable:
                continue
            if not self.momentum[ticker].is_ready or not self.sma50[ticker].is_ready:
                continue

            price = self.securities[symbol].price
            sma_value = self.sma50[ticker].current.value
            mom_value = self.momentum[ticker].current.value

            # Filter: uptrend and positive momentum
            if price > sma_value and mom_value > 0:
                candidates.append({
                    'ticker': ticker,
                    'symbol': symbol,
                    'momentum': mom_value
                })

        if len(candidates) < self.target_positions:
            self.log(f"Only {len(candidates)} candidates, need {self.target_positions}. Taking all available.")
            if len(candidates) < 5:
                self.log("Too few candidates. Cash.")
                self.liquidate()
                return

        # Sort by momentum, take top N
        sorted_candidates = sorted(candidates, key=lambda x: x['momentum'], reverse=True)
        selected = sorted_candidates[:self.target_positions]

        # Hard equal weight with cap
        weight = min(self.max_weight, 0.95 / len(selected))

        # Log selection
        self.log(f"Selected {len(selected)} stocks (10% max each):")
        for i, stock in enumerate(selected, 1):
            self.log(f"  {i}. {stock['ticker']}: {stock['momentum']:.1f}%")

        # Liquidate non-selected
        selected_tickers = set(s['ticker'] for s in selected)
        for ticker, symbol in self.symbols.items():
            if ticker not in selected_tickers and self.portfolio[symbol].invested:
                self.liquidate(symbol)

        # Allocate
        for stock in selected:
            self.set_holdings(stock['symbol'], weight)

    def on_data(self, data):
        pass
