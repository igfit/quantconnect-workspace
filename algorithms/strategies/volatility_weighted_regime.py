from AlgorithmImports import *

class VolatilityWeightedRegime(QCAlgorithm):
    """
    Volatility-Weighted Regime Momentum Strategy

    THESIS: Size positions inversely to their volatility. High-volatility stocks
    get smaller positions, which should reduce overall portfolio risk and drawdown.

    EDGE:
    - Momentum captures winners
    - Vol-weighting normalizes risk contribution
    - Regime filter avoids bear markets
    - More stable returns

    RULES:
    - Bull market: SPY > 200 SMA
    - Select top 8-10 momentum stocks
    - Size inversely proportional to 30-day ATR%
    - Monthly rebalancing

    TARGET: 20%+ CAGR, >1.0 Sharpe, <20% Max DD
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Diversified universe (no NVDA for robustness)
        self.symbols_list = [
            # Tech
            "AAPL", "MSFT", "GOOGL", "AMZN", "META", "CRM", "ADBE",
            # Semiconductors
            "AMD", "AVGO", "QCOM",
            # Consumer
            "TSLA", "HD", "COST", "NKE",
            # Healthcare
            "UNH", "LLY", "JNJ", "ABBV", "MRK",
            # Financials
            "JPM", "V", "MA", "GS", "BRK.B",
            # Communication
            "NFLX", "DIS",
            # Industrials/Energy
            "CAT", "HON", "XOM", "CVX"
        ]

        self.equities = {}
        for symbol in self.symbols_list:
            equity = self.add_equity(symbol, Resolution.DAILY)
            equity.set_leverage(1.0)
            self.equities[symbol] = equity.symbol

        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.set_benchmark("SPY")

        # Indicators
        self.momentum = {}
        self.sma50 = {}
        self.atr = {}

        for symbol in self.symbols_list:
            sym = self.equities[symbol]
            self.momentum[symbol] = self.momp(sym, 126)
            self.sma50[symbol] = self.sma(sym, 50)
            self.atr[symbol] = self.atr_indicator(sym, 30, MovingAverageType.SIMPLE, Resolution.DAILY)

        self.spy_sma200 = self.sma(self.spy, 200)
        self.spy_momentum = self.momp(self.spy, 126)

        self.top_n = 10
        self.rebalance_month = -1

        self.schedule.on(
            self.date_rules.month_start(5),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )

        self.set_warm_up(timedelta(days=210))

    def atr_indicator(self, symbol, period, ma_type, resolution):
        """Create ATR indicator with proper signature"""
        return self.atr(symbol, period, ma_type, resolution)

    def calculate_atr_pct(self, symbol):
        """Calculate ATR as percentage of price"""
        sym = self.equities[symbol]
        atr_ind = self.atr.get(symbol)

        if atr_ind is None or not atr_ind.is_ready:
            return None

        price = self.securities[sym].price
        if price <= 0:
            return None

        return atr_ind.current.value / price

    def rebalance(self):
        if self.is_warming_up:
            return

        if self.time.month == self.rebalance_month:
            return
        self.rebalance_month = self.time.month

        # Market regime check
        if not self.spy_sma200.is_ready:
            return

        spy_price = self.securities[self.spy].price
        spy_sma = self.spy_sma200.current.value

        if spy_price < spy_sma:
            self.log(f"BEAR MARKET: Liquidating.")
            self.liquidate()
            return

        spy_mom = self.spy_momentum.current.value if self.spy_momentum.is_ready else 0

        # Score momentum stocks
        candidates = []

        for symbol in self.symbols_list:
            sym = self.equities[symbol]

            if not self.securities[sym].is_tradable:
                continue

            if not self.momentum[symbol].is_ready or not self.sma50[symbol].is_ready:
                continue

            price = self.securities[sym].price
            sma_value = self.sma50[symbol].current.value
            mom_value = self.momentum[symbol].current.value
            atr_pct = self.calculate_atr_pct(symbol)

            if atr_pct is None:
                continue

            # Qualify: above SMA, positive momentum, beats SPY
            if price > sma_value and mom_value > 0 and mom_value > spy_mom:
                candidates.append({
                    'symbol': symbol,
                    'momentum': mom_value,
                    'atr_pct': atr_pct
                })

        if len(candidates) == 0:
            self.log("No qualifying stocks.")
            self.liquidate()
            return

        # Sort by momentum, take top N
        candidates.sort(key=lambda x: x['momentum'], reverse=True)
        selected = candidates[:self.top_n]

        # Calculate inverse-volatility weights
        # Weight = 1/ATR%, normalized
        total_inv_vol = sum(1.0 / c['atr_pct'] for c in selected)

        weights = {}
        for c in selected:
            raw_weight = (1.0 / c['atr_pct']) / total_inv_vol
            # Cap at 20% to prevent extreme concentration
            weights[c['symbol']] = min(raw_weight, 0.20)

        # Normalize if capped weights don't sum to 1
        total_weight = sum(weights.values())
        if total_weight < 0.95:  # If significant weight was capped
            for symbol in weights:
                weights[symbol] /= total_weight

        self.log(f"Selected {len(selected)} stocks with vol-weighted positions")

        # Liquidate non-selected
        for symbol in self.symbols_list:
            sym = self.equities[symbol]
            if symbol not in weights and self.portfolio[sym].invested:
                self.liquidate(sym)

        # Allocate with vol weights
        for symbol, weight in weights.items():
            sym = self.equities[symbol]
            self.set_holdings(sym, weight)

    def on_data(self, data):
        pass
