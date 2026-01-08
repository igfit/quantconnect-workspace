"""
Momentum Ranking Strategy - Broad Volatile Universe

North Star: ~30% CAGR, ≤30% Max DD, no single-name dependency

Strategy:
- Universe: 60 high-beta stocks from S&P 500 + Russell 2000 (volatile, trading names)
- Signal: Rank by 6-month momentum (ROC)
- Positions: Hold Top 15 (diversified, equal weight)
- Rebalance: Monthly (reduce turnover)
- Regime filter: Optional SPY > 200 SMA

Why this should work:
1. Momentum is a proven factor across academic research
2. High-beta stocks amplify momentum returns
3. Diversification across 15 names reduces single-stock risk
4. Monthly rebalancing captures trends without excessive turnover
"""

from AlgorithmImports import *


class MomentumRankingBroad(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # High-beta volatile universe: S&P 500 + Russell 2000 trading names
        # Focused on stocks that MOVE - no utilities, staples, or low-beta names
        self.universe_tickers = [
            # Mega-cap tech (high beta, liquid)
            "NVDA", "TSLA", "AMD", "META", "GOOGL", "AMZN", "AAPL", "MSFT",
            # High-growth tech
            "CRM", "NOW", "SNOW", "CRWD", "DDOG", "NET", "ZS", "PANW",
            # Semiconductors
            "AVGO", "QCOM", "MU", "MRVL", "ON", "AMAT", "LRCX", "KLAC",
            # Consumer discretionary (volatile)
            "LULU", "NKE", "SBUX", "CMG", "DPZ", "DECK", "CROX", "BOOT",
            # Fintech / high-beta financials
            "COIN", "SQ", "PYPL", "HOOD", "SOFI", "AFRM", "UPST",
            # Travel / leisure (cyclical)
            "ABNB", "BKNG", "RCL", "CCL", "MAR", "HLT", "WYNN", "LVS",
            # High-beta industrials
            "CAT", "DE", "URI", "PWR", "EME",
            # Russell 2000 movers
            "SMCI", "AXON", "TOST", "DUOL", "CELH", "WING", "CAVA",
            # Energy (volatile)
            "XOM", "CVX", "OXY", "DVN", "FANG",
        ]

        # Strategy parameters
        self.lookback_days = 126  # ~6 months for momentum calculation
        self.top_n = 15  # Number of positions to hold
        self.use_regime_filter = True  # Only invest when SPY > 200 SMA

        # Add SPY for regime filter
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.spy_sma = self.sma(self.spy, 200, Resolution.DAILY)

        # Add universe
        self.symbols = []
        for ticker in self.universe_tickers:
            try:
                equity = self.add_equity(ticker, Resolution.DAILY)
                self.symbols.append(equity.symbol)
            except:
                self.debug(f"Could not add {ticker}")

        # Track momentum scores
        self.momentum = {}
        for symbol in self.symbols:
            self.momentum[symbol] = self.roc(symbol, self.lookback_days, Resolution.DAILY)

        # Warmup
        self.set_warm_up(self.lookback_days + 10, Resolution.DAILY)

        # Monthly rebalance
        self.schedule.on(
            self.date_rules.month_start("SPY"),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )

        self.set_benchmark("SPY")

    def rebalance(self):
        """Monthly rebalance: rank by momentum, hold top N"""

        if self.is_warming_up:
            return

        # Regime filter: only invest when SPY > 200 SMA
        if self.use_regime_filter:
            if not self.spy_sma.is_ready:
                return
            spy_price = self.securities[self.spy].price
            if spy_price < self.spy_sma.current.value:
                # Bear market - go to cash
                self.liquidate()
                self.debug(f"{self.time.date()}: Bear market (SPY < 200 SMA) - going to cash")
                return

        # Calculate momentum scores for all symbols
        scores = {}
        for symbol in self.symbols:
            if symbol not in self.momentum:
                continue
            if not self.momentum[symbol].is_ready:
                continue
            if not self.securities[symbol].has_data:
                continue
            if self.securities[symbol].price < 5:  # Min price filter
                continue

            scores[symbol] = self.momentum[symbol].current.value

        if len(scores) < self.top_n:
            self.debug(f"{self.time.date()}: Not enough stocks with data ({len(scores)})")
            return

        # Rank and select top N
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_symbols = [s for s, _ in ranked[:self.top_n]]

        # Log top picks
        top_picks_str = ", ".join([f"{s.value}:{scores[s]:.1f}%" for s in top_symbols[:5]])
        self.debug(f"{self.time.date()}: Top 5: {top_picks_str}")

        # Calculate equal weight
        weight = 1.0 / self.top_n

        # Liquidate positions not in top N
        for holding in self.portfolio.values():
            if holding.invested and holding.symbol not in top_symbols:
                self.liquidate(holding.symbol)

        # Rebalance to equal weight
        for symbol in top_symbols:
            self.set_holdings(symbol, weight)

    def on_data(self, data):
        """Daily processing - not used, rebalance is monthly"""
        pass
