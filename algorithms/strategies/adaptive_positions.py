from AlgorithmImports import *
from collections import defaultdict

class AdaptivePositionsMomentum(QCAlgorithm):
    """
    Adaptive Positions Momentum Strategy

    THESIS: Adjust number of positions based on market conditions.
    When volatility is high or momentum is weak, hold more positions
    for diversification. When conditions are strong, concentrate more.

    WHY THIS SHOULD WORK:
    - Concentration works in strong bull markets
    - Diversification protects in uncertain markets
    - VIX indicates regime - high VIX = uncertain
    - Adapts position count to market conditions

    RULES:
    - Universe: 30 stocks across 6 sectors
    - VIX < 20: Hold top 6 (more concentrated)
    - VIX 20-30: Hold top 8 (balanced)
    - VIX > 30: Hold top 12 (very diversified)
    - Sector cap: 35% max
    - Regime: SPY > 200 SMA

    EDGE: Dynamic concentration based on market regime.
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

        # SPY and VIX
        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.set_benchmark("SPY")

        self.vix = self.add_data(CBOE, "VIX", Resolution.DAILY).symbol

        # Indicators
        self.momentum = {}
        self.sma50 = {}

        for ticker, symbol in self.symbols.items():
            self.momentum[ticker] = self.momp(symbol, 126)
            self.sma50[ticker] = self.sma(symbol, 50)

        self.spy_sma200 = self.sma(self.spy, 200)

        # Settings
        self.max_sector_weight = 0.35

        # Monthly rebalance
        self.schedule.on(
            self.date_rules.month_start(5),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )

        self.set_warm_up(timedelta(days=140))

    def get_target_positions(self, vix_value):
        """Determine number of positions based on VIX."""
        if vix_value < 20:
            return 6, "LOW VIX (Concentrated)"
        elif vix_value < 30:
            return 8, "MEDIUM VIX (Balanced)"
        else:
            return 12, "HIGH VIX (Diversified)"

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

        # Get VIX
        vix_value = self.securities[self.vix].price if self.securities[self.vix].price > 0 else 20
        target_positions, regime = self.get_target_positions(vix_value)

        self.log(f"VIX: {vix_value:.1f} - {regime} - Target: {target_positions} positions")

        # Calculate max position weight based on target positions
        max_position_weight = 0.95 / target_positions

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

        if len(candidates) < target_positions // 2:
            self.log(f"Only {len(candidates)} candidates. Cash.")
            self.liquidate()
            return

        # Sort by momentum
        sorted_candidates = sorted(candidates, key=lambda x: x['momentum'], reverse=True)

        # Select with sector caps (adaptive based on positions)
        selected = []
        sector_counts = defaultdict(int)
        max_per_sector = max(2, target_positions // 3)

        for candidate in sorted_candidates:
            sector = candidate['sector']
            if sector_counts[sector] >= max_per_sector:
                continue
            selected.append(candidate)
            sector_counts[sector] += 1
            if len(selected) >= target_positions:
                break

        if len(selected) == 0:
            self.liquidate()
            return

        # Calculate weights
        sector_weights = defaultdict(float)
        base_weight = 0.95 / len(selected)

        weights = {}
        for stock in selected:
            weight = min(base_weight, max_position_weight)
            weights[stock['ticker']] = weight
            sector_weights[stock['sector']] += weight

        # Enforce sector caps
        for sector, total_weight in sector_weights.items():
            if total_weight > self.max_sector_weight:
                scale = self.max_sector_weight / total_weight
                for stock in selected:
                    if stock['sector'] == sector:
                        weights[stock['ticker']] *= scale

        self.log(f"Selected {len(selected)} stocks")

        # Liquidate non-selected
        for ticker, symbol in self.symbols.items():
            if ticker not in weights and self.portfolio[symbol].invested:
                self.liquidate(symbol)

        # Allocate
        for stock in selected:
            self.set_holdings(stock['symbol'], weights[stock['ticker']])

    def on_data(self, data):
        pass
