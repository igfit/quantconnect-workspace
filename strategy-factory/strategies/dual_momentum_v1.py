"""
Dual Momentum Strategy v1

Based on Gary Antonacci's Dual Momentum concept:
1. Compare momentum of stocks (SPY) vs bonds (BND)
2. Invest in whichever has better momentum
3. If both negative, go to cash (SHY - short term treasuries)

This provides:
- Bull market: Capture stock gains
- Bear market: Rotate to bonds for protection
- Crash: Go to cash

Target: Consistent 15-25% returns with much lower drawdown than stocks
"""

from AlgorithmImports import *
from datetime import timedelta
import numpy as np


class DualMomentumV1(QCAlgorithm):

    # Momentum lookback
    LOOKBACK_DAYS = 252  # 12-month momentum (standard)
    SHORT_LOOKBACK = 63  # 3-month for confirmation

    # Assets
    STOCK_SYMBOL = "SPY"
    BOND_SYMBOL = "BND"  # Total bond market
    CASH_SYMBOL = "SHY"  # Short-term treasury (cash equivalent)

    # Leverage
    LEVERAGE = 1.0

    def initialize(self):
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2026, 1, 9)
        self.set_cash(100000)

        # Add assets
        self.spy = self.add_equity(self.STOCK_SYMBOL, Resolution.DAILY).symbol
        self.bnd = self.add_equity(self.BOND_SYMBOL, Resolution.DAILY).symbol
        self.shy = self.add_equity(self.CASH_SYMBOL, Resolution.DAILY).symbol

        self.set_benchmark(self.spy)

        # Current holding
        self.current_asset = None

        self.set_warmup(timedelta(days=self.LOOKBACK_DAYS + 10))

        # Monthly rebalancing
        self.schedule.on(
            self.date_rules.month_start(0),
            self.time_rules.after_market_open(self.spy, 30),
            self.rebalance
        )

    def calculate_momentum(self, symbol, lookback):
        """Calculate simple momentum (return over period)"""
        history = self.history(symbol, lookback + 1, Resolution.DAILY)
        if history.empty or len(history) < lookback:
            return None
        try:
            prices = history['close'].values
            return (prices[-1] / prices[0]) - 1
        except:
            return None

    def rebalance(self):
        if self.is_warming_up:
            return

        # Calculate 12-month momentum for each asset
        spy_mom_12m = self.calculate_momentum(self.spy, self.LOOKBACK_DAYS)
        bnd_mom_12m = self.calculate_momentum(self.bnd, self.LOOKBACK_DAYS)

        # Calculate 3-month momentum for confirmation
        spy_mom_3m = self.calculate_momentum(self.spy, self.SHORT_LOOKBACK)
        bnd_mom_3m = self.calculate_momentum(self.bnd, self.SHORT_LOOKBACK)

        if spy_mom_12m is None or bnd_mom_12m is None:
            return

        # Dual momentum logic:
        # 1. Absolute momentum: Is the asset positive?
        # 2. Relative momentum: Which asset is stronger?

        spy_positive = spy_mom_12m > 0 and (spy_mom_3m is None or spy_mom_3m > -0.05)
        bnd_positive = bnd_mom_12m > 0

        target_asset = None

        if spy_positive and spy_mom_12m > bnd_mom_12m:
            # SPY has positive momentum and beats bonds
            target_asset = self.spy
        elif bnd_positive:
            # Bonds have positive momentum (and SPY doesn't beat them)
            target_asset = self.bnd
        else:
            # Both negative, go to cash
            target_asset = self.shy

        # Log the decision
        self.log(f"SPY 12m: {spy_mom_12m*100:.1f}%, BND 12m: {bnd_mom_12m*100:.1f}% -> {target_asset.value}")

        # Only trade if target changed
        if target_asset != self.current_asset:
            self.liquidate()
            self.set_holdings(target_asset, self.LEVERAGE)
            self.current_asset = target_asset

    def on_data(self, data):
        pass
