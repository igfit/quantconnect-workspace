from AlgorithmImports import *

class DefensiveRegime7030(QCAlgorithm):
    """
    Defensive Regime Momentum Strategy (70/30)

    THESIS: Combine momentum stocks with defensive bond allocation
    to reduce drawdown while maintaining upside capture.

    EDGE:
    - 70% momentum stocks for growth
    - 30% TLT (long bonds) for defense/diversification
    - Bear market: 100% bonds
    - Negative correlation between stocks and bonds reduces volatility

    RULES:
    - Bull market: 70% top momentum stocks, 30% TLT
    - Bear market: 100% TLT or BIL (short-term treasuries)
    - Monthly rebalancing

    TARGET: 15-20% CAGR, >1.0 Sharpe, <15% Max DD
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Equity universe (no NVDA for robustness)
        self.equity_symbols = [
            "AAPL", "MSFT", "GOOGL", "AMZN", "META",
            "AMD", "AVGO", "QCOM",
            "TSLA", "HD", "COST",
            "UNH", "LLY", "JNJ", "ABBV",
            "JPM", "V", "MA", "BRK.B",
            "NFLX", "CAT", "XOM"
        ]

        self.equities = {}
        for symbol in self.equity_symbols:
            equity = self.add_equity(symbol, Resolution.DAILY)
            equity.set_leverage(1.0)
            self.equities[symbol] = equity.symbol

        # Defensive assets
        tlt = self.add_equity("TLT", Resolution.DAILY)  # Long bonds
        self.tlt = tlt.symbol

        bil = self.add_equity("BIL", Resolution.DAILY)  # T-bills (cash proxy)
        self.bil = bil.symbol

        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.set_benchmark("SPY")

        # Indicators
        self.momentum = {}
        self.sma50 = {}

        for symbol in self.equity_symbols:
            sym = self.equities[symbol]
            self.momentum[symbol] = self.momp(sym, 126)
            self.sma50[symbol] = self.sma(sym, 50)

        self.spy_sma200 = self.sma(self.spy, 200)
        self.spy_momentum = self.momp(self.spy, 126)

        # Allocation settings
        self.equity_allocation = 0.70
        self.bond_allocation = 0.30
        self.num_stocks = 6
        self.rebalance_month = -1

        self.schedule.on(
            self.date_rules.month_start(5),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )

        self.set_warm_up(timedelta(days=210))

    def rebalance(self):
        if self.is_warming_up:
            return

        if self.time.month == self.rebalance_month:
            return
        self.rebalance_month = self.time.month

        if not self.spy_sma200.is_ready:
            return

        spy_price = self.securities[self.spy].price
        spy_sma = self.spy_sma200.current.value

        # BEAR MARKET: 100% bonds/cash
        if spy_price < spy_sma:
            self.log(f"BEAR MARKET: Going defensive (100% TLT)")
            for symbol in self.equity_symbols:
                self.liquidate(self.equities[symbol])
            self.liquidate(self.bil)
            self.set_holdings(self.tlt, 1.0)
            return

        # BULL MARKET: 70% equities, 30% bonds
        spy_mom = self.spy_momentum.current.value if self.spy_momentum.is_ready else 0

        # Score equity candidates
        candidates = []

        for symbol in self.equity_symbols:
            sym = self.equities[symbol]

            if not self.securities[sym].is_tradable:
                continue

            if not self.momentum[symbol].is_ready or not self.sma50[symbol].is_ready:
                continue

            price = self.securities[sym].price
            sma_value = self.sma50[symbol].current.value
            mom_value = self.momentum[symbol].current.value

            if price > sma_value and mom_value > 0 and mom_value > spy_mom:
                candidates.append((symbol, mom_value))

        # Sort by momentum
        candidates.sort(key=lambda x: x[1], reverse=True)
        selected = [c[0] for c in candidates[:self.num_stocks]]

        # Calculate weights
        if len(selected) > 0:
            equity_weight_each = self.equity_allocation / len(selected)
        else:
            equity_weight_each = 0

        self.log(f"BULL: {len(selected)} stocks at {equity_weight_each*100:.1f}% each + {self.bond_allocation*100:.0f}% TLT")

        # Liquidate non-selected equities
        for symbol in self.equity_symbols:
            sym = self.equities[symbol]
            if symbol not in selected and self.portfolio[sym].invested:
                self.liquidate(sym)

        # Allocate to equities
        for symbol in selected:
            sym = self.equities[symbol]
            self.set_holdings(sym, equity_weight_each)

        # Allocate to bonds
        self.liquidate(self.bil)
        self.set_holdings(self.tlt, self.bond_allocation)

    def on_data(self, data):
        pass
