from AlgorithmImports import *

class RiskParityMomentum(QCAlgorithm):
    """
    Risk Parity Momentum - Weight by Inverse Volatility

    THESIS:
    Equal dollar weighting gives volatile stocks (TSLA) same weight as stable
    stocks (JNJ). This creates unequal RISK contribution. By weighting
    inversely to volatility, each position contributes equal risk.

    WHY IT SHOULD WORK:
    1. Risk equalization: TSLA (60% vol) gets 1/3 the weight of JNJ (20% vol)
    2. Lower portfolio vol: Overweight stable stocks = smoother returns
    3. Still captures momentum: Select by momentum, SIZE by risk
    4. Volatility predicts: High vol stocks have higher future DD

    WHY DD SHOULD BE LOW:
    - Volatile stocks get smaller positions → less impact when they crash
    - Stable stocks dominate → portfolio behaves like low-vol stock
    - 2022: TSLA fell 65%, but small position = small impact

    MATH:
    - Stock A: 40% volatility → weight = 1/0.40 = 2.5 (normalized)
    - Stock B: 20% volatility → weight = 1/0.20 = 5.0 (normalized)
    - Stock B gets 2x the weight despite same dollar momentum

    TARGET: 15-20% CAGR, <20% DD, Sharpe > 0.9

    EXCLUSIONS: No NVDA (robustness test)
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Diversified universe (NO NVDA)
        self.tickers = [
            # Growth/Tech
            "AAPL", "MSFT", "GOOGL", "AMZN", "META", "CRM", "ADBE", "ORCL",
            # Semis
            "AMD", "AVGO", "QCOM", "TXN", "INTC",
            # High vol
            "TSLA", "NFLX", "SHOP", "UBER",
            # Finance
            "JPM", "V", "MA", "GS",
            # Healthcare (low vol)
            "UNH", "JNJ", "LLY", "PFE", "ABBV",
            # Stable/Consumer
            "PG", "KO", "WMT", "COST", "HD",
            # Industrial
            "CAT", "HON", "UPS",
            # Energy
            "XOM", "CVX"
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

        # Volatility indicators (20-day standard deviation of returns)
        self.std_ind = {}
        for ticker, symbol in self.symbols.items():
            self.std_ind[ticker] = self.std(symbol, 20, Resolution.DAILY)

        # Trend filter
        self.sma50_ind = {}
        for ticker, symbol in self.symbols.items():
            self.sma50_ind[ticker] = self.sma(symbol, 50, Resolution.DAILY)

        # 15 positions for diversification
        self.top_n = 15

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
            self.debug(f"{self.time.date()}: BEAR MARKET - Going to cash")
            return

        # Select candidates with momentum and volatility
        candidates = []
        for ticker, symbol in self.symbols.items():
            if ticker not in self.momentum_ind or ticker not in self.sma50_ind:
                continue
            if not self.momentum_ind[ticker].is_ready or not self.sma50_ind[ticker].is_ready:
                continue
            if not self.std_ind[ticker].is_ready:
                continue

            price = self.securities[symbol].price
            sma50 = self.sma50_ind[ticker].current.value
            momentum = self.momentum_ind[ticker].current.value
            volatility = self.std_ind[ticker].current.value

            # Filter: positive momentum and uptrend
            if momentum > 0 and price > sma50 and volatility > 0:
                # Annualize volatility (daily std * sqrt(252))
                annual_vol = volatility * (252 ** 0.5) / price * 100  # as percentage

                candidates.append({
                    'ticker': ticker,
                    'symbol': symbol,
                    'momentum': momentum,
                    'volatility': max(annual_vol, 10)  # Floor at 10% to avoid extreme weights
                })

        if len(candidates) < 5:
            self.liquidate()
            return

        # Sort by momentum, take top N
        sorted_candidates = sorted(candidates, key=lambda x: x['momentum'], reverse=True)
        top_stocks = sorted_candidates[:min(self.top_n, len(sorted_candidates))]

        # Calculate inverse volatility weights
        inverse_vols = [1 / s['volatility'] for s in top_stocks]
        total_inverse_vol = sum(inverse_vols)

        # Normalize weights
        weights = {}
        for i, stock in enumerate(top_stocks):
            raw_weight = inverse_vols[i] / total_inverse_vol
            weights[stock['ticker']] = raw_weight * 0.95  # Scale to 95% invested

        # Liquidate positions not in top stocks
        for ticker, symbol in self.symbols.items():
            if ticker not in weights and self.portfolio[symbol].invested:
                self.liquidate(symbol)

        # Apply risk parity weights
        for stock in top_stocks:
            weight = weights[stock['ticker']]
            self.set_holdings(stock['symbol'], weight)

        # Log weight distribution
        max_weight = max(weights.values())
        min_weight = min(weights.values())
        self.debug(f"{self.time.date()}: {len(top_stocks)} positions, Weights: {min_weight:.1%} to {max_weight:.1%}")

    def on_data(self, data):
        pass
