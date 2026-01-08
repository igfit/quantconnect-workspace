from AlgorithmImports import *
from collections import defaultdict

class QualityMegaCapDiversified(QCAlgorithm):
    """
    Quality Mega-Cap Diversified Momentum Strategy

    THESIS: Focus only on the highest quality mega-caps with proven
    profitability and stability. Quality + Momentum + Diversification.

    WHY THIS SHOULD WORK:
    - Quality is a proven factor (profitable companies outperform)
    - Mega-caps have lower volatility and drawdowns
    - Combined with momentum, captures best of both factors
    - Tighter universe = less noise

    RULES:
    - Universe: Only top 20 quality mega-caps (market cap > $100B, profitable)
    - No speculative or unprofitable names
    - Momentum: 6-month ROC > 0
    - Filter: Price > 50 SMA
    - Sector cap: 35% max
    - Hold: Top 10 stocks
    - Regime: SPY > 200 SMA

    EDGE: Quality filter removes losers, diversification prevents concentration.
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Quality mega-cap universe (all profitable, >$100B market cap typically)
        # Hand-picked for quality and stability
        self.universe_map = {
            'Technology': ['AAPL', 'MSFT', 'AVGO', 'ORCL'],  # Removed NVDA (too volatile)
            'Consumer': ['AMZN', 'HD', 'COST', 'MCD'],
            'Communications': ['META', 'GOOGL'],
            'Healthcare': ['UNH', 'JNJ', 'LLY', 'ABBV'],
            'Financials': ['JPM', 'V', 'MA', 'BRK.B'],
            'Industrials': ['CAT', 'HON', 'UNP', 'RTX']
        }

        self.symbols = {}
        self.stock_to_sector = {}

        for sector, tickers in self.universe_map.items():
            for ticker in tickers:
                equity = self.add_equity(ticker, Resolution.DAILY)
                equity.set_leverage(1.0)
                self.symbols[ticker] = equity.symbol
                self.stock_to_sector[ticker] = sector

        # SPY
        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.set_benchmark("SPY")

        # Indicators
        self.momentum = {}
        self.sma50 = {}

        for ticker, symbol in self.symbols.items():
            self.momentum[ticker] = self.momp(symbol, 126)
            self.sma50[ticker] = self.sma(symbol, 50)

        self.spy_sma200 = self.sma(self.spy, 200)

        # Settings
        self.max_sector_weight = 0.35
        self.max_position_weight = 0.10  # Tighter cap
        self.target_positions = 10

        # Monthly rebalance
        self.schedule.on(
            self.date_rules.month_start(5),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )

        self.set_warm_up(timedelta(days=140))

    def rebalance(self):
        if self.is_warming_up:
            return

        if not self.spy_sma200.is_ready:
            return

        spy_price = self.securities[self.spy].price
        spy_sma = self.spy_sma200.current.value

        if spy_price < spy_sma:
            self.log("BEAR MARKET: Cash.")
            self.liquidate()
            return

        candidates = []

        for ticker, symbol in self.symbols.items():
            if not self.securities[symbol].is_tradable:
                continue
            if not self.momentum[ticker].is_ready or not self.sma50[ticker].is_ready:
                continue

            price = self.securities[symbol].price
            sma_value = self.sma50[ticker].current.value
            mom_value = self.momentum[ticker].current.value

            if price > sma_value and mom_value > 0:
                candidates.append({
                    'ticker': ticker,
                    'symbol': symbol,
                    'sector': self.stock_to_sector[ticker],
                    'momentum': mom_value
                })

        if len(candidates) < 5:
            self.log(f"Only {len(candidates)} quality candidates. Cash.")
            self.liquidate()
            return

        # Sort by momentum
        sorted_candidates = sorted(candidates, key=lambda x: x['momentum'], reverse=True)

        # Select with sector caps
        selected = []
        sector_counts = defaultdict(int)
        max_per_sector = 3

        for candidate in sorted_candidates:
            sector = candidate['sector']
            if sector_counts[sector] >= max_per_sector:
                continue
            selected.append(candidate)
            sector_counts[sector] += 1
            if len(selected) >= self.target_positions:
                break

        if len(selected) == 0:
            self.liquidate()
            return

        # Calculate weights
        sector_weights = defaultdict(float)
        base_weight = 0.95 / len(selected)

        weights = {}
        for stock in selected:
            weight = min(base_weight, self.max_position_weight)
            weights[stock['ticker']] = weight
            sector_weights[stock['sector']] += weight

        # Enforce sector caps
        for sector, total_weight in sector_weights.items():
            if total_weight > self.max_sector_weight:
                scale = self.max_sector_weight / total_weight
                for stock in selected:
                    if stock['sector'] == sector:
                        weights[stock['ticker']] *= scale

        self.log(f"Selected {len(selected)} quality mega-caps")

        # Liquidate non-selected
        for ticker, symbol in self.symbols.items():
            if ticker not in weights and self.portfolio[symbol].invested:
                self.liquidate(symbol)

        # Allocate
        for stock in selected:
            self.set_holdings(stock['symbol'], weights[stock['ticker']])

    def on_data(self, data):
        pass
