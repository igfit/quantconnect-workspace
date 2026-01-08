from AlgorithmImports import *

class AdaptiveConcentration(QCAlgorithm):
    """
    Adaptive Concentration - Concentrate When Safe, Diversify When Risky

    THESIS:
    Concentration works in calm bull markets (2021).
    Diversification works in volatile/uncertain markets (2022).
    Adapt position count based on market conditions.

    RULES:
    - BULL + VIX < 20: 5 positions (aggressive, concentrated)
    - BULL + VIX 20-30: 10 positions (balanced)
    - BULL + VIX > 30: 15 positions (defensive, diversified)
    - BEAR (SPY < 200 SMA): Cash

    WHY IT SHOULD WORK:
    - In calm 2021: 5 positions captured TSLA, GOOGL rally
    - In volatile 2022: 15 positions reduced single-stock impact
    - Automatic adaptation without timing calls

    TARGET: 30-35% CAGR, <28% DD, Sharpe > 1.0
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
            "NOW", "UBER", "SHOP", "AMAT", "MU", "INTC"
        ]

        self.symbols = {}
        for ticker in self.tickers:
            try:
                self.symbols[ticker] = self.add_equity(ticker, Resolution.DAILY).symbol
            except:
                pass

        # VIX for regime detection
        self.vix = self.add_data(CBOE, "VIX", Resolution.DAILY).symbol

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

        # Adaptive position counts
        self.concentrated = 5
        self.balanced = 10
        self.diversified = 15

        self.set_benchmark("SPY")

        self.schedule.on(
            self.date_rules.month_start(1),
            self.time_rules.after_market_open(self.spy, 30),
            self.rebalance
        )

        self.set_warm_up(210, Resolution.DAILY)

    def get_position_count(self, vix_value):
        """Determine position count based on VIX"""
        if vix_value < 20:
            return self.concentrated  # 5 positions
        elif vix_value < 30:
            return self.balanced  # 10 positions
        else:
            return self.diversified  # 15 positions

    def rebalance(self):
        if self.is_warming_up:
            return

        if not self.spy_sma200.is_ready:
            return

        # Get market signals
        spy_price = self.securities[self.spy].price
        bull_market = spy_price > self.spy_sma200.current.value
        vix_value = self.securities[self.vix].price if self.securities[self.vix].price > 0 else 20

        if not bull_market:
            self.liquidate()
            self.debug(f"{self.time.date()}: BEAR - Cash")
            return

        # Determine adaptive position count
        num_positions = self.get_position_count(vix_value)

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

        if len(candidates) < 3:
            self.liquidate()
            return

        sorted_candidates = sorted(candidates, key=lambda x: x['momentum'], reverse=True)
        top_stocks = sorted_candidates[:min(num_positions, len(sorted_candidates))]

        # Rebalance
        top_tickers = [s['ticker'] for s in top_stocks]
        for ticker, symbol in self.symbols.items():
            if ticker not in top_tickers and self.portfolio[symbol].invested:
                self.liquidate(symbol)

        weight = 0.95 / len(top_stocks)
        for stock in top_stocks:
            self.set_holdings(stock['symbol'], weight)

        mode = "CONCENTRATED" if num_positions == 5 else ("BALANCED" if num_positions == 10 else "DIVERSIFIED")
        self.debug(f"{self.time.date()}: VIX={vix_value:.1f} → {mode} ({num_positions} positions)")

    def on_data(self, data):
        pass
