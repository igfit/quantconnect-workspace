from AlgorithmImports import *

class VolatilityWeightedMomentum(QCAlgorithm):
    """
    Volatility-Weighted Momentum Strategy

    Thesis: Traditional momentum strategies equal-weight positions, ignoring risk.
    Higher volatility = higher risk. By weighting positions inversely to volatility,
    we allocate more to stable winners and less to volatile ones.

    Rules:
    - Universe: Mega-cap tech stocks (excluding NVDA for robustness testing)
    - Entry: Buy top 5 stocks by 6-month momentum
    - Position sizing: Weight by inverse ATR (lower volatility = larger position)
    - Exit: Monthly rebalance
    - Filter: Stock must be above 50 SMA

    Edge: Better risk-adjusted returns by penalizing volatile stocks.
    Risk parity-lite approach within momentum framework.
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Universe - mega-caps excluding NVDA
        self.tickers = [
            "AAPL", "MSFT", "GOOGL", "AMZN", "META",
            "TSLA", "AMD", "AVGO", "CRM", "ORCL",
            "ADBE", "NFLX", "CSCO", "INTC", "QCOM",
            "TXN", "IBM", "NOW", "UBER", "SHOP"
        ]

        # Add equities
        self.symbols = {}
        for ticker in self.tickers:
            self.symbols[ticker] = self.add_equity(ticker, Resolution.DAILY).symbol

        # Momentum indicators (126 days = 6 months)
        self.momentum_ind = {}
        for ticker, symbol in self.symbols.items():
            self.momentum_ind[ticker] = self.momp(symbol, 126, Resolution.DAILY)

        # ATR for volatility (20 days)
        self.atr_ind = {}
        for ticker, symbol in self.symbols.items():
            self.atr_ind[ticker] = self.atr(symbol, 20, MovingAverageType.SIMPLE, Resolution.DAILY)

        # 50-day SMA for trend filter
        self.sma50_ind = {}
        for ticker, symbol in self.symbols.items():
            self.sma50_ind[ticker] = self.sma(symbol, 50, Resolution.DAILY)

        # Number of stocks to hold
        self.top_n = 5

        # Set benchmark
        self.set_benchmark("SPY")

        # Monthly rebalance
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.schedule.on(
            self.date_rules.month_start(1),
            self.time_rules.after_market_open(self.spy, 30),
            self.rebalance
        )

        # Warmup
        self.set_warm_up(150, Resolution.DAILY)

    def rebalance(self):
        if self.is_warming_up:
            return

        # Calculate momentum and volatility for eligible stocks
        candidates = []
        for ticker, symbol in self.symbols.items():
            # Check all indicators ready
            if not all([
                self.momentum_ind[ticker].is_ready,
                self.atr_ind[ticker].is_ready,
                self.sma50_ind[ticker].is_ready
            ]):
                continue

            price = self.securities[symbol].price
            sma50 = self.sma50_ind[ticker].current.value

            # Filter: price above 50 SMA (uptrend)
            if price <= sma50:
                continue

            momentum = self.momentum_ind[ticker].current.value
            atr = self.atr_ind[ticker].current.value

            # Skip if ATR is too small (avoid division issues)
            if atr < 0.01 * price:
                continue

            # Calculate inverse volatility (ATR as % of price)
            atr_pct = atr / price
            inv_vol = 1.0 / atr_pct

            candidates.append({
                'ticker': ticker,
                'symbol': symbol,
                'momentum': momentum,
                'atr_pct': atr_pct,
                'inv_vol': inv_vol
            })

        if len(candidates) < self.top_n:
            self.debug(f"{self.time.date()}: Only {len(candidates)} candidates, need {self.top_n}")
            return

        # Sort by momentum, take top N
        sorted_candidates = sorted(candidates, key=lambda x: x['momentum'], reverse=True)
        top_stocks = sorted_candidates[:self.top_n]

        # Calculate volatility-weighted positions
        total_inv_vol = sum(s['inv_vol'] for s in top_stocks)

        # Log selection
        self.debug(f"{self.time.date()}: Selected stocks (vol-weighted):")

        # Liquidate positions not in top stocks
        top_tickers = [s['ticker'] for s in top_stocks]
        for ticker, symbol in self.symbols.items():
            if ticker not in top_tickers and self.portfolio[symbol].invested:
                self.liquidate(symbol)

        # Set volatility-weighted positions
        for stock in top_stocks:
            weight = (stock['inv_vol'] / total_inv_vol) * 0.95
            self.set_holdings(stock['symbol'], weight)
            self.debug(f"  {stock['ticker']}: mom={stock['momentum']:.1f}%, ATR={stock['atr_pct']*100:.1f}%, weight={weight*100:.1f}%")

    def on_data(self, data):
        pass
