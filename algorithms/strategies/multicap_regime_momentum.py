from AlgorithmImports import *

class MultiCapRegimeMomentum(QCAlgorithm):
    """
    Multi-Cap Regime Momentum Strategy

    THESIS: Blend large-cap stability with mid-cap growth potential.
    Mid-caps often have stronger momentum but more risk - blending with
    large caps provides balance.

    EDGE:
    - Regime filter for downside protection
    - Large caps: stability, liquidity
    - Mid caps: higher growth potential, stronger momentum
    - 60/40 blend captures best of both

    RULES:
    - Bull market: 60% large cap momentum, 40% mid cap momentum
    - Bear market: 100% cash
    - Top 4 large caps + Top 4 mid caps = 8 positions
    - Monthly rebalancing

    TARGET: 25%+ CAGR, >0.9 Sharpe, <30% Max DD
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Large cap universe (mega caps, $100B+) - no NVDA
        self.large_caps = [
            "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA",
            "BRK.B", "JPM", "V", "UNH", "JNJ", "MA",
            "HD", "PG", "LLY", "AVGO", "COST", "ABBV"
        ]

        # Mid cap universe ($10B-$100B, high growth)
        self.mid_caps = [
            "CRWD", "NET", "DDOG", "ZS", "SNOW",  # Cybersecurity/Cloud
            "PANW", "FTNT", "WDAY",  # Tech services
            "CDNS", "SNPS", "KLAC", "LRCX",  # Semi equipment
            "ABNB", "UBER", "DASH",  # Consumer tech
            "MELI", "NU",  # LatAm fintech
            "TTD", "TEAM"  # Adtech/SaaS
        ]

        self.equities = {}
        self.cap_type = {}

        for symbol in self.large_caps:
            equity = self.add_equity(symbol, Resolution.DAILY)
            equity.set_leverage(1.0)
            self.equities[symbol] = equity.symbol
            self.cap_type[symbol] = 'large'

        for symbol in self.mid_caps:
            try:
                equity = self.add_equity(symbol, Resolution.DAILY)
                equity.set_leverage(1.0)
                self.equities[symbol] = equity.symbol
                self.cap_type[symbol] = 'mid'
            except:
                pass  # Some tickers may not be available

        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.set_benchmark("SPY")

        # Indicators
        self.momentum = {}
        self.sma50 = {}

        all_symbols = list(self.equities.keys())
        for symbol in all_symbols:
            sym = self.equities[symbol]
            self.momentum[symbol] = self.momp(sym, 126)
            self.sma50[symbol] = self.sma(sym, 50)

        self.spy_sma200 = self.sma(self.spy, 200)
        self.spy_momentum = self.momp(self.spy, 126)

        # Allocation settings
        self.large_cap_allocation = 0.60
        self.mid_cap_allocation = 0.40
        self.num_large = 4
        self.num_mid = 4
        self.rebalance_month = -1

        self.schedule.on(
            self.date_rules.month_start(5),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )

        self.set_warm_up(timedelta(days=210))

    def get_qualified_stocks(self, symbols, spy_mom):
        """Get qualified stocks from a list"""
        candidates = []

        for symbol in symbols:
            if symbol not in self.equities:
                continue

            sym = self.equities[symbol]

            if not self.securities[sym].is_tradable:
                continue

            if symbol not in self.momentum or symbol not in self.sma50:
                continue

            if not self.momentum[symbol].is_ready or not self.sma50[symbol].is_ready:
                continue

            price = self.securities[sym].price
            sma_value = self.sma50[symbol].current.value
            mom_value = self.momentum[symbol].current.value

            # Qualify: above SMA, positive momentum
            if price > sma_value and mom_value > 0:
                candidates.append((symbol, mom_value))

        # Sort by momentum
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates

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

        # BEAR MARKET
        if spy_price < spy_sma:
            self.log(f"BEAR MARKET: Going to cash.")
            self.liquidate()
            return

        spy_mom = self.spy_momentum.current.value if self.spy_momentum.is_ready else 0

        # Get candidates from each cap segment
        large_candidates = self.get_qualified_stocks(self.large_caps, spy_mom)
        mid_candidates = self.get_qualified_stocks(self.mid_caps, spy_mom)

        # Select top from each
        selected_large = [c[0] for c in large_candidates[:self.num_large]]
        selected_mid = [c[0] for c in mid_candidates[:self.num_mid]]

        self.log(f"Large caps: {selected_large}")
        self.log(f"Mid caps: {selected_mid}")

        # Calculate weights
        large_weight = self.large_cap_allocation / max(len(selected_large), 1) if selected_large else 0
        mid_weight = self.mid_cap_allocation / max(len(selected_mid), 1) if selected_mid else 0

        # If one segment is empty, redistribute to the other
        if len(selected_large) == 0 and len(selected_mid) > 0:
            mid_weight = 1.0 / len(selected_mid)
        elif len(selected_mid) == 0 and len(selected_large) > 0:
            large_weight = 1.0 / len(selected_large)
        elif len(selected_large) == 0 and len(selected_mid) == 0:
            self.log("No qualified stocks. Going to cash.")
            self.liquidate()
            return

        all_selected = set(selected_large + selected_mid)

        # Liquidate non-selected
        for symbol in self.equities:
            sym = self.equities[symbol]
            if symbol not in all_selected and self.portfolio[sym].invested:
                self.liquidate(sym)

        # Allocate large caps
        for symbol in selected_large:
            sym = self.equities[symbol]
            self.set_holdings(sym, large_weight)

        # Allocate mid caps
        for symbol in selected_mid:
            sym = self.equities[symbol]
            self.set_holdings(sym, mid_weight)

    def on_data(self, data):
        pass
