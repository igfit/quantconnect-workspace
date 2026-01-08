"""
Momentum Ranking Strategy - Fast Momentum (3-month)

Faster momentum signal for quicker reaction to trends.
3-month lookback vs 6-month in base strategy.
"""

from AlgorithmImports import *


class MomentumRankingFast(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # High-beta volatile universe
        self.universe_tickers = [
            # Mega-cap tech
            "NVDA", "TSLA", "AMD", "META", "GOOGL", "AMZN", "AAPL", "MSFT",
            # High-growth tech
            "CRM", "NOW", "SNOW", "CRWD", "DDOG", "NET", "ZS", "PANW",
            # Semiconductors
            "AVGO", "QCOM", "MU", "MRVL", "ON", "AMAT", "LRCX", "KLAC",
            # Consumer discretionary
            "LULU", "NKE", "SBUX", "CMG", "DPZ", "DECK", "CROX", "BOOT",
            # Fintech
            "COIN", "SQ", "PYPL", "HOOD", "SOFI", "AFRM", "UPST",
            # Travel / leisure
            "ABNB", "BKNG", "RCL", "CCL", "MAR", "HLT", "WYNN", "LVS",
            # Industrials
            "CAT", "DE", "URI", "PWR", "EME",
            # Russell 2000 movers
            "SMCI", "AXON", "TOST", "DUOL", "CELH", "WING", "CAVA",
            # Energy
            "XOM", "CVX", "OXY", "DVN", "FANG",
        ]

        # FASTER momentum - 3 months instead of 6
        self.lookback_days = 63  # ~3 months
        self.top_n = 15
        self.use_regime_filter = True

        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.spy_sma = self.sma(self.spy, 200, Resolution.DAILY)

        self.symbols = []
        for ticker in self.universe_tickers:
            try:
                equity = self.add_equity(ticker, Resolution.DAILY)
                self.symbols.append(equity.symbol)
            except:
                pass

        self.momentum = {}
        for symbol in self.symbols:
            self.momentum[symbol] = self.roc(symbol, self.lookback_days, Resolution.DAILY)

        self.set_warm_up(self.lookback_days + 10, Resolution.DAILY)

        self.schedule.on(
            self.date_rules.month_start("SPY"),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )

        self.set_benchmark("SPY")

    def rebalance(self):
        if self.is_warming_up:
            return

        if self.use_regime_filter:
            if not self.spy_sma.is_ready:
                return
            if self.securities[self.spy].price < self.spy_sma.current.value:
                self.liquidate()
                return

        scores = {}
        for symbol in self.symbols:
            if symbol not in self.momentum:
                continue
            if not self.momentum[symbol].is_ready:
                continue
            if not self.securities[symbol].has_data:
                continue
            if self.securities[symbol].price < 5:
                continue
            scores[symbol] = self.momentum[symbol].current.value

        if len(scores) < self.top_n:
            return

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_symbols = [s for s, _ in ranked[:self.top_n]]

        weight = 1.0 / self.top_n

        for holding in self.portfolio.values():
            if holding.invested and holding.symbol not in top_symbols:
                self.liquidate(holding.symbol)

        for symbol in top_symbols:
            self.set_holdings(symbol, weight)

    def on_data(self, data):
        pass
