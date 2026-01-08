from AlgorithmImports import *
from collections import defaultdict

class MomentumWeightedSectors(QCAlgorithm):
    """
    Momentum-Weighted Sector Strategy

    THESIS: Instead of equal-weighting sectors, weight them by their
    momentum strength. Stronger sectors get more allocation.

    WHY THIS SHOULD WORK:
    - Sector momentum persists (academic research)
    - Equal weighting dilutes best opportunities
    - Momentum-weighting captures more upside from hot sectors
    - Still diversified across multiple sectors (min 4)

    RULES:
    - Universe: 30 stocks across 6 sectors
    - Calculate sector momentum: Average 6-mo momentum of top 2 stocks
    - Weight sectors by relative momentum (stronger = more weight)
    - Within sector: Equal weight top 2 stocks
    - Min 4 sectors, max sector weight 40%
    - Regime: SPY > 200 SMA

    EDGE: Capture more from winning sectors while maintaining diversification.
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
        self.sector_stocks = defaultdict(list)

        for sector, tickers in self.universe_map.items():
            for ticker in tickers:
                equity = self.add_equity(ticker, Resolution.DAILY)
                equity.set_leverage(1.0)
                self.symbols[ticker] = equity.symbol
                self.stock_to_sector[ticker] = sector
                self.sector_stocks[sector].append(ticker)

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
        self.min_sectors = 4
        self.max_sector_weight = 0.40
        self.stocks_per_sector = 2

        # Monthly rebalance
        self.schedule.on(
            self.date_rules.month_start(5),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )

        self.set_warm_up(timedelta(days=140))

    def calculate_sector_momentum(self, sector):
        """Calculate sector momentum as average of top 2 stocks."""
        stock_moms = []

        for ticker in self.sector_stocks[sector]:
            symbol = self.symbols[ticker]
            if not self.securities[symbol].is_tradable:
                continue
            if not self.momentum[ticker].is_ready or not self.sma50[ticker].is_ready:
                continue

            price = self.securities[symbol].price
            sma_value = self.sma50[ticker].current.value
            mom_value = self.momentum[ticker].current.value

            # Only count stocks in uptrend with positive momentum
            if price > sma_value and mom_value > 0:
                stock_moms.append({'ticker': ticker, 'momentum': mom_value})

        if len(stock_moms) < 1:
            return None, []

        # Sort and take top 2
        sorted_stocks = sorted(stock_moms, key=lambda x: x['momentum'], reverse=True)
        top_stocks = sorted_stocks[:self.stocks_per_sector]

        # Sector momentum = average of top stocks
        sector_mom = sum(s['momentum'] for s in top_stocks) / len(top_stocks)

        return sector_mom, [s['ticker'] for s in top_stocks]

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

        # Calculate sector momentums
        sector_data = {}

        for sector in self.universe_map.keys():
            sector_mom, top_stocks = self.calculate_sector_momentum(sector)
            if sector_mom is not None and sector_mom > 0:
                sector_data[sector] = {
                    'momentum': sector_mom,
                    'stocks': top_stocks
                }

        if len(sector_data) < self.min_sectors:
            self.log(f"Only {len(sector_data)} sectors with positive momentum. Cash.")
            self.liquidate()
            return

        # Sort sectors by momentum
        sorted_sectors = sorted(sector_data.items(), key=lambda x: x[1]['momentum'], reverse=True)

        # Take top 5 sectors (or all if less)
        selected_sectors = sorted_sectors[:5]

        # Calculate momentum-weighted sector allocations
        total_momentum = sum(s[1]['momentum'] for s in selected_sectors)

        sector_weights = {}
        for sector, data in selected_sectors:
            raw_weight = data['momentum'] / total_momentum if total_momentum > 0 else 0.2
            # Cap at max sector weight
            sector_weights[sector] = min(raw_weight, self.max_sector_weight)

        # Normalize weights to sum to 95%
        total_weight = sum(sector_weights.values())
        scale = 0.95 / total_weight if total_weight > 0 else 0

        for sector in sector_weights:
            sector_weights[sector] *= scale

        # Build stock allocations
        stock_weights = {}
        for sector, data in selected_sectors:
            sector_weight = sector_weights.get(sector, 0)
            stocks = data['stocks']
            if len(stocks) > 0:
                per_stock_weight = sector_weight / len(stocks)
                for ticker in stocks:
                    stock_weights[ticker] = per_stock_weight

        self.log(f"Sector weights:")
        for sector, weight in sorted(sector_weights.items(), key=lambda x: x[1], reverse=True):
            self.log(f"  {sector}: {weight*100:.1f}%")

        # Liquidate non-selected
        for ticker, symbol in self.symbols.items():
            if ticker not in stock_weights and self.portfolio[symbol].invested:
                self.liquidate(symbol)

        # Allocate
        for ticker, weight in stock_weights.items():
            symbol = self.symbols[ticker]
            self.set_holdings(symbol, weight)

    def on_data(self, data):
        pass
