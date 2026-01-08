from AlgorithmImports import *

class DefensiveMomentumRotation(QCAlgorithm):
    """
    Defensive Momentum Rotation Strategy

    THESIS: Rotate to bonds (TLT) when equity momentum signals are weak.
    This should dramatically reduce drawdowns while capturing equity upside.

    EDGE: Most momentum strategies stay invested during corrections.
    Adding a defensive asset provides crisis protection.

    RULES:
    - Universe: 20 mega-cap stocks + TLT (bonds)
    - If top 3 momentum stocks have 6-mo return > 0: invest in them
    - If NO stocks have positive momentum: rotate 100% to TLT
    - Monthly rebalancing

    TARGET: 25%+ CAGR, >1.0 Sharpe, <20% Max DD
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Mega-cap universe (20 stocks)
        self.equity_symbols = [
            "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK.B",
            "JPM", "JNJ", "V", "UNH", "HD", "PG", "MA", "LLY", "AVGO", "COST",
            "MRK", "ABBV"
        ]

        # Defensive asset
        self.defensive_symbol = "TLT"  # 20+ Year Treasury Bond ETF

        # Add all securities
        self.equities = {}
        for symbol in self.equity_symbols:
            equity = self.add_equity(symbol, Resolution.DAILY)
            equity.set_leverage(1.0)
            self.equities[symbol] = equity.symbol

        # Add defensive asset
        tlt = self.add_equity(self.defensive_symbol, Resolution.DAILY)
        tlt.set_leverage(1.0)
        self.tlt = tlt.symbol

        # Add SPY for benchmark
        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.set_benchmark("SPY")

        # Indicators
        self.momentum = {}
        self.sma_ind = {}

        for symbol in self.equity_symbols:
            sym = self.equities[symbol]
            self.momentum[symbol] = self.momp(sym, 126)  # 6-month momentum
            self.sma_ind[symbol] = self.sma(sym, 50)  # 50-day SMA

        self.spy_sma = self.sma(self.spy, 200)  # Market regime filter

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
        self.set_warm_up(timedelta(days=140))

    def rebalance(self):
        if self.is_warming_up:
            return

        # Avoid rebalancing same month twice
        if self.time.month == self.rebalance_month:
            return
        self.rebalance_month = self.time.month

        # Calculate momentum scores for all equities
        momentum_scores = {}

        for symbol in self.equity_symbols:
            sym = self.equities[symbol]

            # Skip if not tradable
            if not self.securities[sym].is_tradable:
                continue

            # Check indicators are ready
            if not self.momentum[symbol].is_ready or not self.sma_ind[symbol].is_ready:
                continue

            price = self.securities[sym].price
            sma_value = self.sma_ind[symbol].current.value
            mom_value = self.momentum[symbol].current.value

            # Only consider stocks above SMA with positive momentum
            if price > sma_value and mom_value > 0:
                momentum_scores[symbol] = mom_value

        # Determine allocation
        if len(momentum_scores) >= self.top_n:
            # OFFENSIVE MODE: Top 3 momentum stocks
            sorted_stocks = sorted(momentum_scores.items(), key=lambda x: x[1], reverse=True)
            selected = [s[0] for s in sorted_stocks[:self.top_n]]

            self.log(f"OFFENSIVE: Investing in {selected}")

            # Liquidate TLT if held
            if self.portfolio[self.tlt].invested:
                self.liquidate(self.tlt)

            # Equal weight allocation to top stocks
            weight = 1.0 / self.top_n

            # Liquidate stocks not in selection
            for symbol in self.equity_symbols:
                sym = self.equities[symbol]
                if symbol not in selected and self.portfolio[sym].invested:
                    self.liquidate(sym)

            # Allocate to selected stocks
            for symbol in selected:
                sym = self.equities[symbol]
                self.set_holdings(sym, weight)

        else:
            # DEFENSIVE MODE: Rotate to bonds
            self.log(f"DEFENSIVE: Only {len(momentum_scores)} stocks with positive momentum. Rotating to TLT.")

            # Liquidate all equities
            for symbol in self.equity_symbols:
                sym = self.equities[symbol]
                if self.portfolio[sym].invested:
                    self.liquidate(sym)

            # Allocate 100% to TLT
            self.set_holdings(self.tlt, 1.0)

    def on_data(self, data):
        pass
