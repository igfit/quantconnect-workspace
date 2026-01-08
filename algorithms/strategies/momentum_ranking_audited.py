"""
Momentum Ranking Strategy - AUDITED VERSION

Same as momentum_ranking_broad.py but with realistic trading constraints:
1. SLIPPAGE: 0.1% per trade (10 bps)
2. COMMISSIONS: Interactive Brokers fee model
3. LIQUIDITY: $1M minimum daily dollar volume

This version validates that the strategy works under realistic conditions.
"""

from AlgorithmImports import *


class MomentumRankingAudited(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # ============================================================
        # REALISTIC TRADING CONSTRAINTS
        # ============================================================

        # 1. SLIPPAGE: 0.1% per trade (conservative estimate)
        self.set_security_initializer(lambda security: security.set_slippage_model(
            ConstantSlippageModel(0.001)  # 0.1% = 10 basis points
        ))

        # 2. COMMISSIONS: IBKR fee model
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        # 3. LIQUIDITY: Minimum dollar volume filter
        self.min_dollar_volume = 1_000_000  # $1M daily minimum

        # ============================================================
        # UNIVERSE: Same 60 high-beta stocks
        # ============================================================
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

        # Strategy parameters (unchanged)
        self.lookback_days = 126  # ~6 months
        self.top_n = 15
        self.use_regime_filter = True

        # SPY for regime filter
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.spy_sma = self.sma(self.spy, 200, Resolution.DAILY)

        # Add universe
        self.symbols = []
        for ticker in self.universe_tickers:
            try:
                equity = self.add_equity(ticker, Resolution.DAILY)
                self.symbols.append(equity.symbol)
            except Exception as e:
                self.debug(f"Could not add {ticker}: {e}")

        # Momentum indicators
        self.momentum = {}
        self.volume_sma = {}  # For liquidity check
        for symbol in self.symbols:
            self.momentum[symbol] = self.roc(symbol, self.lookback_days, Resolution.DAILY)
            self.volume_sma[symbol] = self.sma(symbol, 20, Resolution.DAILY, Field.VOLUME)

        # Warmup
        self.set_warm_up(self.lookback_days + 10, Resolution.DAILY)

        # Monthly rebalance - 30 min after open
        self.schedule.on(
            self.date_rules.month_start("SPY"),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )

        self.set_benchmark("SPY")

    def rebalance(self):
        """Monthly rebalance with realistic constraints"""

        if self.is_warming_up:
            return

        # Regime filter
        if self.use_regime_filter:
            if not self.spy_sma.is_ready:
                return
            spy_price = self.securities[self.spy].price
            if spy_price < self.spy_sma.current.value:
                self.liquidate()
                self.debug(f"{self.time.date()}: Bear market - going to cash")
                return

        # Score symbols with LIQUIDITY CHECK
        scores = {}
        skipped_liquidity = 0
        for symbol in self.symbols:
            # Data checks
            if symbol not in self.momentum:
                continue
            if not self.momentum[symbol].is_ready:
                continue
            if not self.securities[symbol].has_data:
                continue

            price = self.securities[symbol].price
            if price < 5:  # Min price
                continue

            # LIQUIDITY CHECK: Require $1M+ daily dollar volume
            if symbol in self.volume_sma and self.volume_sma[symbol].is_ready:
                avg_volume = self.volume_sma[symbol].current.value
                dollar_volume = avg_volume * price
                if dollar_volume < self.min_dollar_volume:
                    skipped_liquidity += 1
                    continue  # Skip illiquid stocks

            scores[symbol] = self.momentum[symbol].current.value

        if skipped_liquidity > 0:
            self.debug(f"{self.time.date()}: Skipped {skipped_liquidity} illiquid stocks")

        if len(scores) < self.top_n:
            self.debug(f"{self.time.date()}: Not enough liquid stocks ({len(scores)})")
            return

        # Rank and select top N
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_symbols = [s for s, _ in ranked[:self.top_n]]

        # Log selection
        top_picks_str = ", ".join([f"{s.value}:{scores[s]:.1f}%" for s in top_symbols[:5]])
        self.debug(f"{self.time.date()}: Top 5: {top_picks_str}")

        # Equal weight
        weight = 1.0 / self.top_n

        # Liquidate non-top positions
        for holding in self.portfolio.values():
            if holding.invested and holding.symbol not in top_symbols:
                self.liquidate(holding.symbol)

        # Rebalance
        for symbol in top_symbols:
            self.set_holdings(symbol, weight)

    def on_data(self, data):
        pass
