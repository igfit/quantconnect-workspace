"""
Sector Rotation Momentum Strategy

Rotates among the 9 original sector SPDRs based on momentum ranking.
Holds the top N sectors by 3-month return, rebalances monthly.

Universe: Sector SPDRs (Universe B) - Zero survivorship bias
Rebalance: Monthly (first trading day)
Holding Period: ~1 month

WHY THIS WORKS:
- Sector momentum is well-documented (Faber, O'Shaughnessy)
- Sectors trend due to business cycle and sentiment shifts
- Holding top 3 provides diversification while capturing momentum
- Monthly rebalancing balances signal vs transaction costs

KEY PARAMETERS:
- TOP_N = 3 (number of sectors to hold)
- LOOKBACK = 63 (3 months momentum, ~63 trading days)
- REGIME_FILTER = True (only invest when SPY > 200 SMA)

EXPECTED CHARACTERISTICS:
- Win rate: ~50-55%
- Higher returns than equal-weight sector allocation
- Lower drawdowns with regime filter
"""

from AlgorithmImports import *
from datetime import timedelta


class SectorRotationMomentum(QCAlgorithm):
    """
    Sector Momentum Rotation Strategy

    Rules:
    1. Monthly rebalance on first trading day
    2. Rank all 9 sectors by 3-month return
    3. Hold top 3 sectors with equal weight
    4. Optional: Only invest when SPY > 200 SMA (regime filter)
    """

    # Configuration
    TOP_N = 3  # Number of sectors to hold
    LOOKBACK = 63  # 3-month momentum (trading days)
    USE_REGIME_FILTER = True

    def initialize(self):
        # Backtest period
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Original 9 sector SPDRs (all exist since 1998)
        self.sectors = []
        sector_tickers = [
            "XLK",  # Technology
            "XLF",  # Financials
            "XLV",  # Health Care
            "XLE",  # Energy
            "XLI",  # Industrials
            "XLP",  # Consumer Staples
            "XLY",  # Consumer Discretionary
            "XLB",  # Materials
            "XLU",  # Utilities
        ]

        for ticker in sector_tickers:
            equity = self.add_equity(ticker, Resolution.DAILY)
            equity.set_slippage_model(ConstantSlippageModel(0.001))
            equity.set_fee_model(InteractiveBrokersFeeModel())
            self.sectors.append(equity.symbol)

        # SPY for regime filter and benchmark
        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.set_benchmark(self.spy)

        # Regime filter: 200-day SMA
        self.spy_sma = self.sma(self.spy, 200, Resolution.DAILY)

        # Track current holdings
        self.current_holdings = set()

        # Trade logging
        self.rotation_log = []

        # Warmup
        self.set_warmup(timedelta(days=210))

        # Schedule monthly rebalance
        self.schedule.on(
            self.date_rules.month_start(self.spy),
            self.time_rules.after_market_open(self.spy, 30),
            self.rebalance
        )

    def rebalance(self):
        """Monthly sector rotation based on momentum ranking"""
        if self.is_warming_up:
            return

        # Check regime filter
        if self.USE_REGIME_FILTER:
            if not self.spy_sma.is_ready:
                return
            if self.securities[self.spy].price < self.spy_sma.current.value:
                # Bear market - go to cash
                if self.current_holdings:
                    self.liquidate()
                    self.current_holdings = set()
                    self.log(f"REGIME FILTER: SPY below 200 SMA → CASH")
                return

        # Calculate momentum for each sector
        rankings = []
        for symbol in self.sectors:
            mom = self.get_momentum(symbol)
            if mom is not None:
                rankings.append((symbol, mom))

        if len(rankings) < self.TOP_N:
            return

        # Sort by momentum (highest first)
        rankings.sort(key=lambda x: x[1], reverse=True)

        # Select top N
        top_sectors = [r[0] for r in rankings[:self.TOP_N]]
        top_sectors_set = set(top_sectors)

        # Log ranking
        self.log(f"RANKING: {' > '.join([f'{r[0].value}({r[1]*100:.1f}%)' for r in rankings[:5]])}")

        # Check if holdings changed
        if top_sectors_set == self.current_holdings:
            return

        # Log rotation
        entering = top_sectors_set - self.current_holdings
        exiting = self.current_holdings - top_sectors_set

        if entering or exiting:
            self.rotation_log.append({
                'date': str(self.time.date()),
                'entering': [str(s) for s in entering],
                'exiting': [str(s) for s in exiting],
            })

        # Liquidate sectors no longer in top N
        for symbol in exiting:
            self.liquidate(symbol)
            self.log(f"EXIT: {symbol}")

        # Equal weight allocation to top N
        weight = 0.99 / self.TOP_N

        for symbol in top_sectors:
            self.set_holdings(symbol, weight)
            if symbol in entering:
                self.log(f"ENTRY: {symbol}")

        self.current_holdings = top_sectors_set

    def get_momentum(self, symbol) -> float:
        """Calculate momentum (return) over lookback period"""
        history = self.history(symbol, self.LOOKBACK + 1, Resolution.DAILY)

        if history.empty or len(history) < self.LOOKBACK:
            return None

        try:
            start_price = history['close'].iloc[0]
            end_price = history['close'].iloc[-1]
            return (end_price - start_price) / start_price
        except:
            return None

    def on_end_of_algorithm(self):
        """Log summary at end of backtest"""
        self.log("=" * 60)
        self.log("SECTOR ROTATION - SUMMARY")
        self.log("=" * 60)
        self.log(f"Total Rotations: {len(self.rotation_log)}")

        # Count sector appearances
        sector_counts = {}
        for rotation in self.rotation_log:
            for s in rotation['entering']:
                ticker = s.split()[0]
                sector_counts[ticker] = sector_counts.get(ticker, 0) + 1

        self.log("Sector Entry Counts (most to least):")
        for ticker, count in sorted(sector_counts.items(), key=lambda x: x[1], reverse=True):
            self.log(f"  {ticker}: {count}")

        self.log("=" * 60)

    def on_data(self, data):
        """Required method - rebalancing done via scheduled event"""
        pass
