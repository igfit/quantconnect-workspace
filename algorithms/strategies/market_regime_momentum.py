from AlgorithmImports import *

class MarketRegimeMomentum(QCAlgorithm):
    """
    Market Regime Momentum Strategy

    THESIS: Only invest in momentum stocks when the market is in a bull regime.
    Go to cash during bear markets to avoid drawdowns.

    EDGE: The 2022 drawdown (-27%) hurt all momentum strategies.
    A simple SPY > 200 SMA filter could have avoided most of it.

    RULES:
    - Bull Market: SPY > 200 SMA → invest in top 3 momentum stocks
    - Bear Market: SPY < 200 SMA → 100% cash (or T-bills)
    - Same momentum signal as Quality MegaCap (6-mo return > 0, Price > 50 SMA)
    - Monthly rebalancing

    TARGET: 30%+ CAGR, >1.0 Sharpe, <20% Max DD
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Mega-cap universe (19 stocks) - NVDA EXCLUDED for robustness test
        self.symbols = [
            "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "BRK.B",
            "JPM", "JNJ", "V", "UNH", "HD", "PG", "MA", "LLY", "AVGO", "COST",
            "MRK", "ABBV"
        ]

        # Add securities
        self.equities = {}
        for symbol in self.symbols:
            equity = self.add_equity(symbol, Resolution.DAILY)
            equity.set_leverage(1.0)
            self.equities[symbol] = equity.symbol

        # Add SPY for regime detection
        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.set_benchmark("SPY")

        # Indicators
        self.momentum = {}
        self.sma50 = {}

        for symbol in self.symbols:
            sym = self.equities[symbol]
            self.momentum[symbol] = self.momp(sym, 126)  # 6-month momentum
            self.sma50[symbol] = self.sma(sym, 50)  # 50-day SMA

        # Market regime indicator
        self.spy_sma200 = self.sma(self.spy, 200)

        # Settings
        self.top_n = 3
        self.rebalance_month = -1

        # Schedule monthly rebalancing
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

        # Avoid rebalancing same month twice
        if self.time.month == self.rebalance_month:
            return
        self.rebalance_month = self.time.month

        # Check market regime
        if not self.spy_sma200.is_ready:
            return

        spy_price = self.securities[self.spy].price
        spy_sma = self.spy_sma200.current.value

        if spy_price < spy_sma:
            # BEAR MARKET: Go to cash
            self.log(f"BEAR MARKET: SPY ({spy_price:.2f}) < 200 SMA ({spy_sma:.2f}). Going to cash.")
            self.liquidate()
            return

        # BULL MARKET: Select momentum stocks
        self.log(f"BULL MARKET: SPY ({spy_price:.2f}) > 200 SMA ({spy_sma:.2f}). Selecting momentum stocks.")

        # Calculate momentum scores
        momentum_scores = {}

        for symbol in self.symbols:
            sym = self.equities[symbol]

            if not self.securities[sym].is_tradable:
                continue

            if not self.momentum[symbol].is_ready or not self.sma50[symbol].is_ready:
                continue

            price = self.securities[sym].price
            sma_value = self.sma50[symbol].current.value
            mom_value = self.momentum[symbol].current.value

            # Price > 50 SMA and positive momentum
            if price > sma_value and mom_value > 0:
                momentum_scores[symbol] = mom_value

        if len(momentum_scores) == 0:
            self.log("No stocks with positive momentum. Staying in cash.")
            self.liquidate()
            return

        # Select top N
        sorted_stocks = sorted(momentum_scores.items(), key=lambda x: x[1], reverse=True)
        selected = [s[0] for s in sorted_stocks[:self.top_n]]

        self.log(f"Selected: {selected}")

        # Equal weight
        weight = 1.0 / len(selected)

        # Liquidate non-selected
        for symbol in self.symbols:
            sym = self.equities[symbol]
            if symbol not in selected and self.portfolio[sym].invested:
                self.liquidate(sym)

        # Allocate
        for symbol in selected:
            sym = self.equities[symbol]
            self.set_holdings(sym, weight)

    def on_data(self, data):
        pass
