from AlgorithmImports import *

class DefensiveRotation(QCAlgorithm):
    """
    Defensive Asset Rotation - Include Bonds/Gold for Crisis Protection

    THESIS:
    Equities alone can't protect in crashes. By including TLT (bonds) and GLD (gold)
    in the momentum universe, we can rotate to defensive assets when equities weaken.

    WHY IT SHOULD WORK:
    1. Flight to safety: In crises, money flows to bonds/gold (March 2020)
    2. Negative correlation: Bonds often rise when stocks fall
    3. Gold as hedge: Inflation/uncertainty hedge
    4. Momentum works for all assets: Not just stocks

    WHY DD SHOULD BE LOW:
    - 2020 crash: TLT rose while stocks fell
    - 2022: GLD held flat while stocks/bonds both fell (diversification)
    - Defensive assets can be "selected" by momentum when they're stronger

    ALLOCATION:
    - 80% in stocks (12 positions)
    - 20% reserved for TLT/GLD when defensive
    - Or: Momentum selects across all assets including defensives

    TARGET: 15-20% CAGR, <20% DD, Sharpe > 0.9

    EXCLUSIONS: No NVDA (robustness test)
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Equity universe (NO NVDA)
        self.equity_tickers = [
            "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA",
            "AMD", "AVGO", "CRM", "ORCL", "NFLX", "ADBE",
            "JPM", "V", "UNH", "LLY", "XOM", "CAT",
            "HD", "COST", "PG", "JNJ", "MA", "TXN"
        ]

        # Defensive assets
        self.defensive_tickers = ["TLT", "GLD", "SHY"]  # Bonds, Gold, Short-term treasuries

        self.all_tickers = self.equity_tickers + self.defensive_tickers

        self.symbols = {}
        self.is_defensive = {}
        for ticker in self.all_tickers:
            try:
                self.symbols[ticker] = self.add_equity(ticker, Resolution.DAILY).symbol
                self.is_defensive[ticker] = ticker in self.defensive_tickers
            except:
                pass

        # Market regime filter
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.spy_sma200 = self.sma(self.spy, 200, Resolution.DAILY)

        # Momentum indicators (shorter period for defensive rotation speed)
        self.momentum_ind = {}
        for ticker, symbol in self.symbols.items():
            self.momentum_ind[ticker] = self.momp(symbol, 63, Resolution.DAILY)  # 3 months

        # Trend filter
        self.sma50_ind = {}
        for ticker, symbol in self.symbols.items():
            self.sma50_ind[ticker] = self.sma(symbol, 50, Resolution.DAILY)

        # Position limits
        self.max_equity_positions = 12
        self.max_defensive_positions = 2

        self.set_benchmark("SPY")

        self.schedule.on(
            self.date_rules.month_start(1),
            self.time_rules.after_market_open(self.spy, 30),
            self.rebalance
        )

        self.set_warm_up(150, Resolution.DAILY)

    def rebalance(self):
        if self.is_warming_up:
            return

        if not self.spy_sma200.is_ready:
            return

        # Check market regime
        spy_price = self.securities[self.spy].price
        bull_market = spy_price > self.spy_sma200.current.value

        # Separate equity and defensive candidates
        equity_candidates = []
        defensive_candidates = []

        for ticker, symbol in self.symbols.items():
            if ticker not in self.momentum_ind or ticker not in self.sma50_ind:
                continue
            if not self.momentum_ind[ticker].is_ready or not self.sma50_ind[ticker].is_ready:
                continue

            momentum = self.momentum_ind[ticker].current.value
            price = self.securities[symbol].price
            sma50 = self.sma50_ind[ticker].current.value

            candidate = {
                'ticker': ticker,
                'symbol': symbol,
                'momentum': momentum
            }

            if self.is_defensive.get(ticker, False):
                # Defensive assets: always consider them
                defensive_candidates.append(candidate)
            else:
                # Equities: require uptrend
                if momentum > 0 and price > sma50:
                    equity_candidates.append(candidate)

        # In bear market: tilt toward defensive
        if bull_market:
            equity_allocation = 0.80
            defensive_allocation = 0.15
        else:
            equity_allocation = 0.30  # Reduced equity in bear
            defensive_allocation = 0.65  # More defensive

        # Sort and select
        sorted_equities = sorted(equity_candidates, key=lambda x: x['momentum'], reverse=True)
        sorted_defensives = sorted(defensive_candidates, key=lambda x: x['momentum'], reverse=True)

        selected_equities = sorted_equities[:self.max_equity_positions] if bull_market else sorted_equities[:4]
        selected_defensives = sorted_defensives[:self.max_defensive_positions]

        # Liquidate positions not selected
        selected_tickers = [s['ticker'] for s in selected_equities + selected_defensives]
        for ticker, symbol in self.symbols.items():
            if ticker not in selected_tickers and self.portfolio[symbol].invested:
                self.liquidate(symbol)

        # Allocate to equities
        if len(selected_equities) > 0:
            eq_weight = equity_allocation / len(selected_equities)
            for stock in selected_equities:
                self.set_holdings(stock['symbol'], eq_weight)

        # Allocate to defensives
        if len(selected_defensives) > 0:
            def_weight = defensive_allocation / len(selected_defensives)
            for stock in selected_defensives:
                self.set_holdings(stock['symbol'], def_weight)

        regime = "BULL" if bull_market else "BEAR"
        self.debug(f"{self.time.date()}: {regime} - {len(selected_equities)} equities ({equity_allocation:.0%}), {len(selected_defensives)} defensive ({defensive_allocation:.0%})")

    def on_data(self, data):
        pass
