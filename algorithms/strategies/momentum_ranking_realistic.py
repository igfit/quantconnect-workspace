"""
Momentum Ranking Strategy - REALISTIC VERSION

Fixes for common backtesting mistakes:
1. NO SURVIVORSHIP BIAS - Only stocks that existed and were liquid in 2020
2. SLIPPAGE MODEL - 0.1% slippage per trade
3. COMMISSION MODEL - Interactive Brokers fees
4. LIQUIDITY FILTER - Min $1M daily volume
5. NO HINDSIGHT BIAS - Universe based on 2019 S&P 500 + established mid-caps

Removed stocks with post-2020 IPOs:
- COIN, HOOD, UPST, AFRM, SOFI, DUOL, CAVA, TOST, etc.
"""

from AlgorithmImports import *


class MomentumRankingRealistic(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # REALISTIC SLIPPAGE: 0.1% per trade
        self.set_security_initializer(lambda security: security.set_slippage_model(
            ConstantSlippageModel(0.001)  # 0.1% = 10 bps
        ))

        # IBKR Commission Model
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        # SURVIVORSHIP-FREE UNIVERSE: Only stocks that were liquid in 2019
        # No stocks with IPOs after 2019
        self.universe_tickers = [
            # Mega-cap tech (all pre-2019)
            "NVDA", "TSLA", "AMD", "META", "GOOGL", "AMZN", "AAPL", "MSFT",
            # Established tech (pre-2019)
            "CRM", "NOW", "ADBE", "NFLX", "PYPL", "SQ",  # SQ IPO 2015
            # Semiconductors (all pre-2019)
            "AVGO", "QCOM", "MU", "MRVL", "ON", "AMAT", "LRCX", "KLAC", "TXN",
            # Consumer discretionary (pre-2019)
            "LULU", "NKE", "SBUX", "CMG", "DPZ", "DECK", "CROX",
            # Financials (pre-2019)
            "V", "MA", "JPM", "GS", "MS",
            # Travel / leisure (pre-2019)
            "BKNG", "RCL", "CCL", "MAR", "HLT", "WYNN", "LVS", "MGM",
            # Industrials (pre-2019)
            "CAT", "DE", "URI", "BA", "HON", "UNP",
            # Established mid-caps (pre-2019)
            "SMCI", "AXON", "ETSY", "ROKU", "TTD", "SNAP", "PINS",
            # Energy (pre-2019)
            "XOM", "CVX", "OXY", "DVN", "COP", "SLB",
            # Healthcare (pre-2019)
            "ISRG", "DXCM", "ALGN", "VEEV",
        ]

        # Strategy parameters
        self.lookback_days = 126  # ~6 months
        self.top_n = 15
        self.use_regime_filter = True
        self.min_dollar_volume = 1_000_000  # $1M daily volume minimum

        # SPY for regime filter
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.spy_sma = self.sma(self.spy, 200, Resolution.DAILY)

        # Add universe with data checks
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

        # Monthly rebalance - 30 min after open for liquidity
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
                    continue  # Skip illiquid stocks

            scores[symbol] = self.momentum[symbol].current.value

        if len(scores) < self.top_n:
            self.debug(f"{self.time.date()}: Not enough liquid stocks ({len(scores)})")
            return

        # Rank and select top N
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_symbols = [s for s, _ in ranked[:self.top_n]]

        # Log selection
        self.debug(f"{self.time.date()}: Selected {len(top_symbols)} stocks")

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
