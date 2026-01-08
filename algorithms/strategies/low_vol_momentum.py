from AlgorithmImports import *

class LowVolMomentum(QCAlgorithm):
    """
    Low Volatility Momentum - Exclude High-Vol Stocks for Lower DD

    THESIS:
    TSLA, AMD, SHOP have 60%+ volatility. When they crash, they crash HARD.
    By excluding stocks with >50% volatility, we get momentum with less DD.

    WHY IT SHOULD WORK:
    1. Low-vol anomaly: Low-vol stocks have better risk-adjusted returns
    2. Momentum still applies: Low-vol stocks can still have momentum
    3. Avoid blow-ups: High-vol stocks cause most of the DD
    4. More consistent: Portfolio behaves more predictably

    FILTER:
    - Calculate 60-day realized volatility (annualized)
    - Exclude stocks with vol > 50%
    - Select top 8 by momentum from remaining

    TRADE-OFF:
    - May miss TSLA's 10x run
    - But also misses TSLA's -65% crash

    TARGET: 25-30% CAGR, <22% DD, Sharpe > 0.95
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Broad universe - will filter by volatility (NO NVDA)
        self.tickers = [
            "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA",
            "AVGO", "CRM", "ORCL", "ADBE", "NFLX", "AMD",
            "JPM", "V", "MA", "UNH", "LLY", "COST",
            "CAT", "DE", "TXN", "QCOM", "GS", "HD",
            "NOW", "UBER", "SHOP", "PG", "JNJ", "WMT",
            "ABBV", "MRK", "PFE", "KO", "PEP"
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

        # Volatility indicators
        self.std_ind = {}
        for ticker, symbol in self.symbols.items():
            self.std_ind[ticker] = self.std(symbol, 60, Resolution.DAILY)

        self.sma50_ind = {}
        for ticker, symbol in self.symbols.items():
            self.sma50_ind[ticker] = self.sma(symbol, 50, Resolution.DAILY)

        # Volatility ceiling (annualized)
        self.max_vol = 50  # 50% max volatility
        self.top_n = 8

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
            return

        # Select candidates with volatility filter
        candidates = []
        excluded_high_vol = []

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
            daily_std = self.std_ind[ticker].current.value

            # Annualize volatility
            annual_vol = (daily_std / price) * (252 ** 0.5) * 100

            # VOLATILITY FILTER: exclude high-vol stocks
            if annual_vol > self.max_vol:
                excluded_high_vol.append(f"{ticker}({annual_vol:.0f}%)")
                continue

            if momentum > 0 and price > sma50:
                candidates.append({
                    'ticker': ticker,
                    'symbol': symbol,
                    'momentum': momentum,
                    'volatility': annual_vol
                })

        if len(candidates) < 4:
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

        if excluded_high_vol:
            self.debug(f"{self.time.date()}: Excluded high-vol: {excluded_high_vol[:5]}")

    def on_data(self, data):
        pass
