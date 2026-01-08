from AlgorithmImports import *

class DiversifiedRegimeMomentum(QCAlgorithm):
    """
    Diversified Regime Momentum Strategy

    THESIS: Keep the proven SPY > 200 SMA regime filter, but spread across
    more positions (8-10) to reduce concentration risk.

    EDGE: Market regime filter avoids bear market drawdowns.
    Diversification reduces single-stock risk without sacrificing much return.

    RULES:
    - Bull Market: SPY > 200 SMA → invest in top 8-10 momentum stocks
    - Bear Market: SPY < 200 SMA → 100% cash
    - Signal: 6-month return > 0, Price > 50 SMA, relative strength vs SPY
    - Monthly rebalancing
    - Max 12.5% per position (8 positions) or 10% (10 positions)

    TARGET: 25%+ CAGR, >1.0 Sharpe, <30% Max DD, diversified across sectors
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # DIVERSIFIED universe (35 stocks across sectors) - NO NVDA for robustness
        self.symbols_list = [
            # Tech (limit exposure)
            "AAPL", "MSFT", "GOOGL", "AMZN", "META", "CRM", "ADBE", "ORCL",
            # Semiconductors (no NVDA)
            "AMD", "AVGO", "QCOM", "INTC",
            # Consumer
            "TSLA", "HD", "COST", "NKE", "SBUX", "MCD",
            # Healthcare
            "UNH", "LLY", "JNJ", "PFE", "ABBV", "MRK",
            # Financials
            "JPM", "V", "MA", "GS", "BRK.B",
            # Energy/Industrials
            "XOM", "CVX", "CAT", "HON", "UNP",
            # Communication
            "NFLX", "DIS"
        ]

        # Add securities
        self.equities = {}
        for symbol in self.symbols_list:
            equity = self.add_equity(symbol, Resolution.DAILY)
            equity.set_leverage(1.0)
            self.equities[symbol] = equity.symbol

        # SPY for regime detection
        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.set_benchmark("SPY")

        # Indicators
        self.momentum = {}
        self.sma50 = {}

        for symbol in self.symbols_list:
            sym = self.equities[symbol]
            self.momentum[symbol] = self.momp(sym, 126)  # 6-month momentum
            self.sma50[symbol] = self.sma(sym, 50)

        # Market regime indicators
        self.spy_sma200 = self.sma(self.spy, 200)
        self.spy_momentum = self.momp(self.spy, 126)

        # Diversification settings
        self.top_n = 10  # More positions for diversification
        self.max_position_pct = 0.12  # Max 12% per position
        self.rebalance_month = -1

        # Monthly rebalancing
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

        # Check market regime
        if not self.spy_sma200.is_ready:
            return

        spy_price = self.securities[self.spy].price
        spy_sma = self.spy_sma200.current.value

        if spy_price < spy_sma:
            self.log(f"BEAR MARKET: SPY ({spy_price:.2f}) < 200 SMA ({spy_sma:.2f}). Going to cash.")
            self.liquidate()
            return

        self.log(f"BULL MARKET: SPY ({spy_price:.2f}) > 200 SMA ({spy_sma:.2f})")

        # Get SPY momentum for relative strength
        spy_mom = self.spy_momentum.current.value if self.spy_momentum.is_ready else 0

        # Calculate momentum scores
        momentum_scores = {}

        for symbol in self.symbols_list:
            sym = self.equities[symbol]

            if not self.securities[sym].is_tradable:
                continue

            if not self.momentum[symbol].is_ready or not self.sma50[symbol].is_ready:
                continue

            price = self.securities[sym].price
            sma_value = self.sma50[symbol].current.value
            mom_value = self.momentum[symbol].current.value

            # Price > 50 SMA, positive momentum, beats SPY
            if price > sma_value and mom_value > 0 and mom_value > spy_mom:
                momentum_scores[symbol] = mom_value

        if len(momentum_scores) == 0:
            self.log("No qualifying stocks. Going to cash.")
            self.liquidate()
            return

        # Select top N
        sorted_stocks = sorted(momentum_scores.items(), key=lambda x: x[1], reverse=True)
        selected = [s[0] for s in sorted_stocks[:self.top_n]]

        self.log(f"Selected {len(selected)}: {selected}")

        # Equal weight with max cap
        weight = min(1.0 / len(selected), self.max_position_pct)

        # Liquidate non-selected
        for symbol in self.symbols_list:
            sym = self.equities[symbol]
            if symbol not in selected and self.portfolio[sym].invested:
                self.liquidate(sym)

        # Allocate
        for symbol in selected:
            sym = self.equities[symbol]
            self.set_holdings(sym, weight)

    def on_data(self, data):
        pass
