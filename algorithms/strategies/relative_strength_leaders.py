from AlgorithmImports import *

class RelativeStrengthLeaders(QCAlgorithm):
    """
    Relative Strength Leaders Strategy

    THESIS: Instead of absolute momentum, use relative strength vs SPY.
    Stocks that consistently outperform the market tend to continue.

    EDGE: Relative strength captures "alpha" - outperformance beyond market beta.
    A stock can be flat but still have positive RS if market is down.

    RULES:
    - Calculate RS = Stock/SPY ratio
    - Buy stocks where RS is above its 50-day SMA (RS trending up)
    - AND 6-month RS return is positive
    - Select top 3 by RS momentum
    - Monthly rebalancing

    TARGET: 35%+ CAGR, >1.0 Sharpe, <30% Max DD
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

        # Add SPY as reference
        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.set_benchmark("SPY")

        # Price history for RS calculation
        self.lookback = 126  # 6 months
        self.rs_sma_period = 50

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
        self.set_warm_up(timedelta(days=180))

    def rebalance(self):
        if self.is_warming_up:
            return

        # Avoid rebalancing same month twice
        if self.time.month == self.rebalance_month:
            return
        self.rebalance_month = self.time.month

        # Get SPY history
        spy_history = self.history(self.spy, self.lookback + self.rs_sma_period, Resolution.DAILY)
        if spy_history.empty:
            return

        spy_prices = spy_history['close'].values

        # Calculate RS scores for each stock
        rs_scores = {}

        for symbol in self.symbols:
            sym = self.equities[symbol]

            if not self.securities[sym].is_tradable:
                continue

            # Get stock history
            stock_history = self.history(sym, self.lookback + self.rs_sma_period, Resolution.DAILY)
            if stock_history.empty or len(stock_history) < self.lookback + self.rs_sma_period:
                continue

            stock_prices = stock_history['close'].values

            # Align lengths
            min_len = min(len(stock_prices), len(spy_prices))
            stock_prices = stock_prices[-min_len:]
            spy_aligned = spy_prices[-min_len:]

            # Calculate RS ratio (Stock/SPY)
            rs_ratio = stock_prices / spy_aligned

            # Calculate RS 50-day SMA
            if len(rs_ratio) < self.rs_sma_period:
                continue

            rs_sma = sum(rs_ratio[-self.rs_sma_period:]) / self.rs_sma_period
            current_rs = rs_ratio[-1]

            # Calculate 6-month RS return
            if len(rs_ratio) < self.lookback:
                continue

            rs_6mo_ago = rs_ratio[-self.lookback]
            rs_return = (current_rs - rs_6mo_ago) / rs_6mo_ago

            # Filter: RS above SMA (uptrend) AND positive RS return
            if current_rs > rs_sma and rs_return > 0:
                rs_scores[symbol] = rs_return

        if len(rs_scores) == 0:
            self.log("No stocks with positive relative strength. Liquidating.")
            self.liquidate()
            return

        # Select top N by RS momentum
        sorted_stocks = sorted(rs_scores.items(), key=lambda x: x[1], reverse=True)
        selected = [s[0] for s in sorted_stocks[:self.top_n]]

        self.log(f"RS Leaders: {selected} (RS returns: {[f'{rs_scores[s]:.2%}' for s in selected]})")

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
