from AlgorithmImports import *
from collections import defaultdict

class MultiSectorBalancedMomentum(QCAlgorithm):
    """
    Multi-Sector Balanced Momentum Strategy

    THESIS: Force diversification by allocating across sectors.
    Tech shouldn't dominate - max 35% per sector.

    WHY THIS WORKS:
    - Momentum is sector-agnostic - winners exist in all sectors
    - Sector crashes (2022 tech) don't destroy entire portfolio
    - Reduces correlation, improves risk-adjusted returns
    - Prevents NVDA-type concentration

    RULES:
    - Universe: 30 stocks across 6 sectors (5 per sector)
    - Sector cap: 35% max
    - Position cap: 12.5% max per stock
    - Hold: Top 8 stocks by momentum, respecting sector caps
    - Filter: 6-month momentum > 0, Price > 50 SMA, SPY > 200 SMA
    - Rebalance: Monthly

    EDGE: Sector diversification reduces concentration risk
    while maintaining momentum alpha.
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Universe: 30 stocks, 5 per sector (6 sectors)
        self.universe_map = {
            'Technology': ['AAPL', 'MSFT', 'NVDA', 'AVGO', 'CRM'],
            'Consumer': ['AMZN', 'TSLA', 'HD', 'COST', 'NKE'],
            'Communications': ['META', 'GOOGL', 'NFLX', 'DIS', 'CMCSA'],
            'Healthcare': ['UNH', 'JNJ', 'LLY', 'PFE', 'ABBV'],
            'Financials': ['JPM', 'V', 'MA', 'GS', 'BLK'],
            'Industrials': ['CAT', 'HON', 'UPS', 'BA', 'GE']
        }

        # Flatten universe and track sectors
        self.symbols = {}
        self.stock_to_sector = {}

        for sector, tickers in self.universe_map.items():
            for ticker in tickers:
                equity = self.add_equity(ticker, Resolution.DAILY)
                equity.set_leverage(1.0)
                self.symbols[ticker] = equity.symbol
                self.stock_to_sector[ticker] = sector

        # SPY for regime detection
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
        self.max_sector_weight = 0.35  # 35% max per sector
        self.max_position_weight = 0.125  # 12.5% max per stock
        self.target_positions = 8

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
            self.log(f"BEAR MARKET: SPY ({spy_price:.2f}) < 200 SMA ({spy_sma:.2f}). Cash.")
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
                    'sector': self.stock_to_sector[ticker],
                    'momentum': mom_value
                })

        if len(candidates) < 4:
            self.log(f"Only {len(candidates)} candidates. Staying in cash.")
            self.liquidate()
            return

        # Sort by momentum (descending)
        sorted_candidates = sorted(candidates, key=lambda x: x['momentum'], reverse=True)

        # Select stocks respecting sector caps
        selected = []
        sector_counts = defaultdict(int)
        max_per_sector = 3  # At most 3 stocks per sector

        for candidate in sorted_candidates:
            sector = candidate['sector']

            # Check sector limit
            if sector_counts[sector] >= max_per_sector:
                continue

            selected.append(candidate)
            sector_counts[sector] += 1

            if len(selected) >= self.target_positions:
                break

        if len(selected) == 0:
            self.log("No stocks selected. Cash.")
            self.liquidate()
            return

        # Calculate weights with sector cap enforcement
        sector_weights = defaultdict(float)
        base_weight = 0.95 / len(selected)

        # First pass: assign weights
        weights = {}
        for stock in selected:
            weight = min(base_weight, self.max_position_weight)
            weights[stock['ticker']] = weight
            sector_weights[stock['sector']] += weight

        # Second pass: enforce sector caps by reducing proportionally
        for sector, total_weight in sector_weights.items():
            if total_weight > self.max_sector_weight:
                scale = self.max_sector_weight / total_weight
                for stock in selected:
                    if stock['sector'] == sector:
                        weights[stock['ticker']] *= scale

        # Log selection
        self.log(f"Selected {len(selected)} stocks:")
        for sector, count in sector_counts.items():
            self.log(f"  {sector}: {count}")

        # Liquidate non-selected
        for ticker, symbol in self.symbols.items():
            if ticker not in weights and self.portfolio[symbol].invested:
                self.liquidate(symbol)

        # Allocate
        for stock in selected:
            weight = weights[stock['ticker']]
            self.set_holdings(stock['symbol'], weight)

    def on_data(self, data):
        pass
