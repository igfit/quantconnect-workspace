# region imports
from AlgorithmImports import *
# endregion

class SectorRotationV13(QCAlgorithm):
    """
    V13: Sector ETF Rotation

    Hypothesis: Sector momentum is more robust than individual stock momentum
    - Use liquid sector ETFs (no stock-specific risk)
    - Rotate to top 2-3 sectors by momentum
    - Monthly rebalance (sectors move slower)
    - Market regime filter
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Sector ETFs
        self.sector_etfs = [
            "XLK",  # Technology
            "XLY",  # Consumer Discretionary
            "XLC",  # Communication Services
            "XLI",  # Industrials
            "XLF",  # Financials
            "XLV",  # Healthcare
            "XLE",  # Energy
            "XLB",  # Materials
            "XLU",  # Utilities
            "XLRE", # Real Estate
        ]

        self.top_n = 3  # Hold top 3 sectors

        # Add all ETFs
        self.etf_symbols = []
        for ticker in self.sector_etfs:
            security = self.add_equity(ticker, Resolution.DAILY)
            self.etf_symbols.append(security.symbol)

        # Market regime
        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)

        vix = self.add_data(CBOE, "VIX", Resolution.DAILY)
        self.vix = vix.symbol

        # Price history for momentum calculation
        self.price_history = {s: [] for s in self.etf_symbols}

        # Monthly rebalance (first Monday of month)
        self.schedule.on(
            self.date_rules.month_start("SPY", 0),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )

        self.holdings = {}
        self.set_benchmark("SPY")
        self.set_warm_up(200, Resolution.DAILY)

    def get_vix(self):
        if self.vix in self.securities and self.securities[self.vix].price > 0:
            return self.securities[self.vix].price
        return 20

    def on_data(self, data):
        if self.is_warming_up:
            return

        for symbol in self.etf_symbols:
            if symbol in data and data[symbol] is not None:
                price = data[symbol].close
                self.price_history[symbol].append(price)
                if len(self.price_history[symbol]) > 200:
                    self.price_history[symbol] = self.price_history[symbol][-200:]

    def get_momentum(self, symbol, lookback):
        """Calculate momentum over lookback period"""
        if symbol not in self.price_history:
            return None
        prices = self.price_history[symbol]
        if len(prices) < lookback:
            return None
        return (prices[-1] - prices[-lookback]) / prices[-lookback]

    def get_volatility(self, symbol, lookback=21):
        """Calculate annualized volatility"""
        if symbol not in self.price_history:
            return None
        prices = self.price_history[symbol]
        if len(prices) < lookback + 1:
            return None

        returns = []
        for i in range(-lookback, 0):
            ret = (prices[i] - prices[i-1]) / prices[i-1]
            returns.append(ret)

        if len(returns) < 10:
            return None

        mean_ret = sum(returns) / len(returns)
        variance = sum((r - mean_ret) ** 2 for r in returns) / len(returns)
        return (variance ** 0.5) * (252 ** 0.5)

    def rebalance(self):
        if self.is_warming_up:
            return

        # Market regime filter
        spy_price = self.securities[self.spy].price
        if not self.spy_sma_200.is_ready or spy_price < self.spy_sma_200.current.value:
            self.liquidate()
            self.holdings = {}
            return

        vix = self.get_vix()
        if vix > 35:
            self.liquidate()
            self.holdings = {}
            return

        # Calculate momentum for each sector
        scores = []
        for symbol in self.etf_symbols:
            mom_3m = self.get_momentum(symbol, 63)   # 3-month
            mom_1m = self.get_momentum(symbol, 21)   # 1-month

            if mom_3m is None or mom_1m is None:
                continue

            # Require positive 3-month momentum
            if mom_3m < 0:
                continue

            # Require positive 1-month momentum (trend confirmation)
            if mom_1m < 0:
                continue

            # Risk-adjusted score: momentum / volatility
            vol = self.get_volatility(symbol)
            if vol is None or vol <= 0:
                score = mom_3m
            else:
                score = mom_3m / vol

            scores.append((symbol, score, mom_3m))

        scores.sort(key=lambda x: x[1], reverse=True)
        top_sectors = scores[:self.top_n]

        if len(top_sectors) == 0:
            self.liquidate()
            self.holdings = {}
            return

        # Equal weight
        weight = 1.0 / len(top_sectors)

        # Liquidate old holdings
        new_holdings = set(s for s, _, _ in top_sectors)
        for symbol in list(self.holdings.keys()):
            if symbol not in new_holdings:
                self.liquidate(symbol)
                del self.holdings[symbol]

        # Set new holdings
        for symbol, score, mom in top_sectors:
            self.set_holdings(symbol, weight)
            self.holdings[symbol] = weight
