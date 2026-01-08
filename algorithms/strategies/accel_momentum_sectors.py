from AlgorithmImports import *
from collections import defaultdict

class AcceleratingMomentumSectors(QCAlgorithm):
    """
    Accelerating Momentum with Sector Diversification

    THESIS: Combine the best of Round 6 (strong momentum signal) with
    Round 7 (sector diversification) for better risk-adjusted returns.

    WHY THIS SHOULD WORK:
    - Accelerating momentum (avg of 1m, 3m, 6m) captures trend acceleration
    - Sector caps prevent NVDA-type concentration
    - Academic research shows multi-lookback outperforms single lookback
    - Faster signals catch momentum earlier than 6-month alone

    RULES:
    - Universe: 30 stocks across 6 sectors
    - Momentum: Average of ROC(21), ROC(63), ROC(126)
    - Sector cap: 35% max
    - Position cap: 12.5% max
    - Hold: Top 8 by accelerating momentum
    - Filter: Price > 50 SMA, SPY > 200 SMA
    - Rebalance: Monthly

    EDGE: Faster momentum detection + diversification = better Sharpe
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Universe: 30 stocks, 5 per sector
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

        # SPY for regime
        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.set_benchmark("SPY")

        # Indicators: 3 momentum periods for accelerating momentum
        self.roc_21 = {}  # 1-month
        self.roc_63 = {}  # 3-month
        self.roc_126 = {}  # 6-month
        self.sma50 = {}

        for ticker, symbol in self.symbols.items():
            self.roc_21[ticker] = self.rocp(symbol, 21)
            self.roc_63[ticker] = self.rocp(symbol, 63)
            self.roc_126[ticker] = self.rocp(symbol, 126)
            self.sma50[ticker] = self.sma(symbol, 50)

        self.spy_sma200 = self.sma(self.spy, 200)

        # Settings
        self.max_sector_weight = 0.35
        self.max_position_weight = 0.125
        self.target_positions = 8

        # Monthly rebalance
        self.schedule.on(
            self.date_rules.month_start(5),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )

        self.set_warm_up(timedelta(days=140))

    def calculate_accel_momentum(self, ticker):
        """Calculate accelerating momentum as average of 3 lookbacks."""
        if not all([
            self.roc_21[ticker].is_ready,
            self.roc_63[ticker].is_ready,
            self.roc_126[ticker].is_ready
        ]):
            return None

        roc1 = self.roc_21[ticker].current.value
        roc3 = self.roc_63[ticker].current.value
        roc6 = self.roc_126[ticker].current.value

        # Weight recent momentum more heavily
        return (roc1 * 0.5 + roc3 * 0.3 + roc6 * 0.2)

    def rebalance(self):
        if self.is_warming_up:
            return

        # Check market regime
        if not self.spy_sma200.is_ready:
            return

        spy_price = self.securities[self.spy].price
        spy_sma = self.spy_sma200.current.value

        if spy_price < spy_sma:
            self.log(f"BEAR MARKET: Cash.")
            self.liquidate()
            return

        # Calculate accelerating momentum
        candidates = []

        for ticker, symbol in self.symbols.items():
            if not self.securities[symbol].is_tradable:
                continue
            if not self.sma50[ticker].is_ready:
                continue

            accel_mom = self.calculate_accel_momentum(ticker)
            if accel_mom is None:
                continue

            price = self.securities[symbol].price
            sma_value = self.sma50[ticker].current.value

            # Filter: uptrend and positive accelerating momentum
            if price > sma_value and accel_mom > 0:
                candidates.append({
                    'ticker': ticker,
                    'symbol': symbol,
                    'sector': self.stock_to_sector[ticker],
                    'momentum': accel_mom
                })

        if len(candidates) < 4:
            self.log(f"Only {len(candidates)} candidates. Cash.")
            self.liquidate()
            return

        # Sort by accelerating momentum
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

        # Calculate weights with sector cap
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

        # Log
        self.log(f"Selected {len(selected)} stocks with accel momentum")

        # Liquidate non-selected
        for ticker, symbol in self.symbols.items():
            if ticker not in weights and self.portfolio[symbol].invested:
                self.liquidate(symbol)

        # Allocate
        for stock in selected:
            self.set_holdings(stock['symbol'], weights[stock['ticker']])

    def on_data(self, data):
        pass
