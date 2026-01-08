from AlgorithmImports import *
from collections import defaultdict

class Near52WeekHighSectors(QCAlgorithm):
    """
    Near 52-Week High Sector Momentum Strategy

    THESIS: Academic research shows stocks near their 52-week high
    significantly outperform (0.65%/month vs 0.38% for standard momentum).
    Combine this with sector diversification.

    WHY THIS SHOULD WORK:
    - George & Hwang (2004): 52WH proximity predicts returns better than momentum
    - Stocks near highs have institutional support
    - Reduces "falling knife" risk - only buying strong stocks
    - Sector caps maintain diversification

    RULES:
    - Universe: 30 stocks across 6 sectors
    - Filter 1: Within 15% of 52-week high (price >= 0.85 * max_252)
    - Filter 2: 6-month momentum > 0
    - Filter 3: Price > 50 SMA
    - Ranking: Sort by proximity to 52WH (closer = better)
    - Sector cap: 35% max
    - Hold: Top 8

    EDGE: 52WH filter captures strongest stocks with institutional backing.
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Universe
        self.universe_map = {
            'Technology': ['AAPL', 'MSFT', 'NVDA', 'AVGO', 'CRM'],
            'Consumer': ['AMZN', 'TSLA', 'HD', 'COST', 'NKE'],
            'Communications': ['META', 'GOOGL', 'NFLX', 'DIS', 'CMCSA'],
            'Healthcare': ['UNH', 'JNJ', 'LLY', 'PFE', 'ABBV'],
            'Financials': ['JPM', 'V', 'MA', 'GS', 'BLK'],
            'Industrials': ['CAT', 'HON', 'UPS', 'BA', 'GE']
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
        self.max_252 = {}  # 52-week high

        for ticker, symbol in self.symbols.items():
            self.momentum[ticker] = self.momp(symbol, 126)
            self.sma50[ticker] = self.sma(symbol, 50)
            self.max_252[ticker] = self.max_indicator(symbol, 252)

        self.spy_sma200 = self.sma(self.spy, 200)

        # Settings
        self.near_high_threshold = 0.85  # Within 15% of 52WH
        self.max_sector_weight = 0.35
        self.max_position_weight = 0.125
        self.target_positions = 8

        # Monthly rebalance
        self.schedule.on(
            self.date_rules.month_start(5),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )

        self.set_warm_up(timedelta(days=260))

    def max_indicator(self, symbol, period):
        """Create a Maximum indicator for 52-week high."""
        indicator = Maximum(period)
        self.register_indicator(symbol, indicator, Resolution.DAILY)
        return indicator

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
            if not all([
                self.momentum[ticker].is_ready,
                self.sma50[ticker].is_ready,
                self.max_252[ticker].is_ready
            ]):
                continue

            price = self.securities[symbol].price
            sma_value = self.sma50[ticker].current.value
            mom_value = self.momentum[ticker].current.value
            high_52w = self.max_252[ticker].current.value

            if high_52w <= 0:
                continue

            # Calculate proximity to 52-week high (1.0 = at high, 0.85 = 15% below)
            proximity = price / high_52w

            # Filters
            if (price > sma_value and  # Uptrend
                mom_value > 0 and  # Positive momentum
                proximity >= self.near_high_threshold):  # Near 52WH
                candidates.append({
                    'ticker': ticker,
                    'symbol': symbol,
                    'sector': self.stock_to_sector[ticker],
                    'proximity': proximity,
                    'momentum': mom_value
                })

        if len(candidates) < 4:
            self.log(f"Only {len(candidates)} near 52WH. Cash.")
            self.liquidate()
            return

        # Sort by proximity to 52WH (higher = better)
        sorted_candidates = sorted(candidates, key=lambda x: x['proximity'], reverse=True)

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

        self.log(f"Selected {len(selected)} stocks near 52WH")
        for stock in selected[:3]:
            self.log(f"  {stock['ticker']}: {stock['proximity']*100:.1f}% of 52WH")

        # Liquidate non-selected
        for ticker, symbol in self.symbols.items():
            if ticker not in weights and self.portfolio[symbol].invested:
                self.liquidate(symbol)

        # Allocate
        for stock in selected:
            self.set_holdings(stock['symbol'], weights[stock['ticker']])

    def on_data(self, data):
        pass
