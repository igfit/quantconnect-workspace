from AlgorithmImports import *

class MomentumStrategy(QCAlgorithm):
    """
    Simple Momentum Strategy Example

    Strategy:
        - Go long top N momentum stocks from universe
        - Rebalance monthly
        - Equal weight positions

    Parameters:
        - lookback: Momentum lookback period (days)
        - num_holdings: Number of stocks to hold
        - rebalance_freq: Rebalance frequency

    Universe: Top 500 US equities by dollar volume
    """

    def initialize(self):
        # Backtest period
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 1, 1)
        self.set_cash(100000)

        # Strategy parameters
        self.lookback = 252  # 1 year momentum
        self.num_holdings = 10
        self.rebalance_day = 1  # First trading day of month

        # Universe selection
        self.universe_settings.resolution = Resolution.DAILY
        self.add_universe(self.coarse_selection)

        # Track momentum scores
        self.momentum = {}

        # Schedule rebalancing
        self.schedule.on(
            self.date_rules.month_start(),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )

    def coarse_selection(self, coarse):
        """Select top 500 stocks by dollar volume"""
        # Filter for price > $5 and has fundamental data
        filtered = [x for x in coarse if x.price > 5 and x.has_fundamental_data]

        # Sort by dollar volume and take top 500
        sorted_by_volume = sorted(filtered, key=lambda x: x.dollar_volume, reverse=True)
        return [x.symbol for x in sorted_by_volume[:500]]

    def on_securities_changed(self, changes):
        """Handle universe changes"""
        for security in changes.added_securities:
            symbol = security.symbol
            # Initialize momentum indicator
            self.momentum[symbol] = self.momp(symbol, self.lookback, Resolution.DAILY)

        for security in changes.removed_securities:
            symbol = security.symbol
            if symbol in self.momentum:
                del self.momentum[symbol]

    def rebalance(self):
        """Monthly rebalancing logic"""
        # Get momentum scores for all symbols with ready indicators
        scores = {}
        for symbol, indicator in self.momentum.items():
            if indicator.is_ready and self.securities[symbol].price > 0:
                scores[symbol] = indicator.current.value

        if not scores:
            return

        # Sort by momentum and select top N
        sorted_symbols = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        selected = [x[0] for x in sorted_symbols[:self.num_holdings]]

        # Calculate target weights
        weight = 1.0 / self.num_holdings

        # Liquidate positions not in selected
        for symbol in list(self.portfolio.keys()):
            if self.portfolio[symbol].invested and symbol not in selected:
                self.liquidate(symbol)

        # Enter new positions
        for symbol in selected:
            self.set_holdings(symbol, weight)

    def on_data(self, data):
        """Called on each data update - not used for this strategy"""
        pass
