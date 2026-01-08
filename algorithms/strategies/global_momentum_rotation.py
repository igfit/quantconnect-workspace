from AlgorithmImports import *

class GlobalMomentumRotation(QCAlgorithm):
    """
    Global Momentum Rotation Strategy

    THESIS: Diversify momentum across US, developed, and emerging markets.
    When US underperforms, international markets may offer better returns.

    EDGE: 2020-2024 was dominated by US tech. But historically,
    international markets have had periods of outperformance.

    RULES:
    - Universe: SPY (US), QQQ (US Tech), EFA (Developed ex-US), EEM (Emerging)
    - Calculate 6-month momentum for each
    - Invest 100% in top performer (if momentum > 0)
    - If all negative, go to cash (or bonds via AGG)
    - Monthly rebalancing

    TARGET: 25%+ CAGR, >0.8 Sharpe, <25% Max DD
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Global ETFs
        self.etf_symbols = {
            "SPY": "US Large Cap (S&P 500)",
            "QQQ": "US Tech (Nasdaq 100)",
            "EFA": "Developed Markets ex-US",
            "EEM": "Emerging Markets",
            "VWO": "Emerging Markets (Vanguard)"
        }

        # Defensive asset
        self.defensive = "AGG"  # US Aggregate Bond ETF

        # Add all ETFs
        self.etfs = {}
        for symbol in self.etf_symbols:
            etf = self.add_equity(symbol, Resolution.DAILY)
            etf.set_leverage(1.0)
            self.etfs[symbol] = etf.symbol

        # Add defensive
        agg = self.add_equity(self.defensive, Resolution.DAILY)
        agg.set_leverage(1.0)
        self.agg = agg.symbol

        self.set_benchmark("SPY")

        # Momentum indicators
        self.momentum = {}
        self.sma_ind = {}

        for symbol in self.etf_symbols:
            sym = self.etfs[symbol]
            self.momentum[symbol] = self.momp(sym, 126)  # 6-month
            self.sma_ind[symbol] = self.sma(sym, 50)

        # Settings
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

        # Avoid same month
        if self.time.month == self.rebalance_month:
            return
        self.rebalance_month = self.time.month

        # Calculate momentum for each ETF
        momentum_scores = {}

        for symbol in self.etf_symbols:
            sym = self.etfs[symbol]

            if not self.securities[sym].is_tradable:
                continue

            if not self.momentum[symbol].is_ready or not self.sma_ind[symbol].is_ready:
                continue

            price = self.securities[sym].price
            sma_value = self.sma_ind[symbol].current.value
            mom_value = self.momentum[symbol].current.value

            # Only consider if above SMA (uptrend) and positive momentum
            if price > sma_value and mom_value > 0:
                momentum_scores[symbol] = mom_value

            self.log(f"{symbol}: Mom={mom_value:.2f}, Above SMA={price > sma_value}")

        if len(momentum_scores) == 0:
            # Defensive: rotate to bonds
            self.log("All ETFs have negative momentum. Rotating to AGG (bonds).")
            self.liquidate()
            self.set_holdings(self.agg, 1.0)
            return

        # Find best performer
        best_etf = max(momentum_scores.items(), key=lambda x: x[1])
        best_symbol = best_etf[0]

        self.log(f"Best momentum: {best_symbol} ({self.etf_symbols[best_symbol]}) with {best_etf[1]:.2f}")

        # Rotate to best performer
        target = self.etfs[best_symbol]

        # Liquidate others
        for symbol in self.etf_symbols:
            sym = self.etfs[symbol]
            if sym != target and self.portfolio[sym].invested:
                self.liquidate(sym)

        # Liquidate defensive if held
        if self.portfolio[self.agg].invested:
            self.liquidate(self.agg)

        # 100% allocation to best
        self.set_holdings(target, 1.0)

    def on_data(self, data):
        pass
