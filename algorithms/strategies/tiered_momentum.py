from AlgorithmImports import *

class TieredMomentum(QCAlgorithm):
    """
    Tiered Momentum - Heavy Weight on Top 3, Diversified Tail

    THESIS:
    Top 3 momentum stocks drive most returns, but holding only 3 = high DD.
    Solution: Give top 3 heavy weights (45% total), but add 7 more for safety.

    ALLOCATION:
    - Top 3 stocks: 15% each = 45% total (captures winners)
    - Next 7 stocks: 7% each = 49% total (safety net)
    - Cash buffer: 6%

    WHY IT SHOULD WORK:
    - Top 3 drive returns like concentrated strategy
    - Positions 4-10 reduce DD when top 3 stumble
    - If #1 stock crashes 50%, only -7.5% to portfolio (not -16% like in top 3)
    - Tail positions often become new leaders

    TARGET: 30-35% CAGR, <28% DD, Sharpe > 0.95
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
            "CAT", "DE", "TXN", "QCOM", "GS", "HD",
            "NOW", "UBER", "SHOP", "AMAT", "MU"
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

        self.sma50_ind = {}
        for ticker, symbol in self.symbols.items():
            self.sma50_ind[ticker] = self.sma(symbol, 50, Resolution.DAILY)

        # Tiered weights
        self.top_tier_count = 3
        self.top_tier_weight = 0.15  # 15% each
        self.second_tier_count = 7
        self.second_tier_weight = 0.07  # 7% each

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

        # Split into tiers
        top_tier = sorted_candidates[:self.top_tier_count]
        second_tier = sorted_candidates[self.top_tier_count:self.top_tier_count + self.second_tier_count]

        all_selected = top_tier + second_tier

        # Liquidate positions not selected
        selected_tickers = [s['ticker'] for s in all_selected]
        for ticker, symbol in self.symbols.items():
            if ticker not in selected_tickers and self.portfolio[symbol].invested:
                self.liquidate(symbol)

        # Apply tiered weights
        for stock in top_tier:
            self.set_holdings(stock['symbol'], self.top_tier_weight)

        for stock in second_tier:
            self.set_holdings(stock['symbol'], self.second_tier_weight)

        self.debug(f"{self.time.date()}: Top 3 at 15%: {[s['ticker'] for s in top_tier]}, Next {len(second_tier)} at 7%")

    def on_data(self, data):
        pass
