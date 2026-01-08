from AlgorithmImports import *

class SectorETFMomentum(QCAlgorithm):
    """
    Sector ETF Momentum Strategy

    THESIS: Use sector ETFs instead of individual stocks for
    natural diversification and reduced single-stock risk.

    WHY THIS WORKS:
    - Each ETF contains dozens of stocks - built-in diversification
    - No NVDA-type concentration risk
    - Lower volatility than individual stocks
    - Still captures sector momentum (tech outperformance)
    - Simpler to manage, lower turnover

    RULES:
    - Universe: 11 S&P 500 Sector ETFs
    - Filter: 6-month momentum > 0, Price > 50 SMA
    - Select: Top 4 sectors by momentum
    - Weight: Equal (25% each)
    - Regime: SPY > 200 SMA
    - Rebalance: Monthly

    EDGE: Sector rotation captures momentum alpha while
    eliminating single-stock risk entirely.

    TRADE-OFF: Lower returns than concentrated stock picks,
    but significantly lower risk and concentration.
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # 11 S&P 500 Sector ETFs
        self.sector_etfs = {
            'XLK': 'Technology',
            'XLV': 'Healthcare',
            'XLF': 'Financials',
            'XLY': 'Consumer Discretionary',
            'XLP': 'Consumer Staples',
            'XLI': 'Industrials',
            'XLE': 'Energy',
            'XLB': 'Materials',
            'XLRE': 'Real Estate',
            'XLU': 'Utilities',
            'XLC': 'Communications'
        }

        # Add ETFs
        self.symbols = {}
        for ticker, sector in self.sector_etfs.items():
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

        # Settings
        self.top_n = 4  # Hold top 4 sectors

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
                    'sector': self.sector_etfs[ticker],
                    'momentum': mom_value
                })

        if len(candidates) < 2:
            self.log(f"Only {len(candidates)} sector ETFs qualify. Cash.")
            self.liquidate()
            return

        # Sort by momentum, take top N
        sorted_candidates = sorted(candidates, key=lambda x: x['momentum'], reverse=True)
        selected = sorted_candidates[:self.top_n]

        # Log selection
        self.log(f"Top {len(selected)} sectors:")
        for etf in selected:
            self.log(f"  {etf['ticker']} ({etf['sector']}): {etf['momentum']:.1f}%")

        # Equal weight
        weight = 0.95 / len(selected)

        # Liquidate non-selected
        for ticker, symbol in self.symbols.items():
            if ticker not in [s['ticker'] for s in selected]:
                if self.portfolio[symbol].invested:
                    self.liquidate(symbol)

        # Allocate
        for etf in selected:
            self.set_holdings(etf['symbol'], weight)

    def on_data(self, data):
        pass
