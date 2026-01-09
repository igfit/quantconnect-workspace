"""
Dual Momentum Strategy v2 - Aggressive

More aggressive version:
1. QQQ instead of SPY (more growth)
2. TLT instead of BND (more volatility, higher returns in flight-to-safety)
3. Shorter lookback: 6 months (faster switching)
4. 1.2x leverage for boost
5. Weekly check for faster response
"""

from AlgorithmImports import *
from datetime import timedelta
import numpy as np


class DualMomentumV2(QCAlgorithm):

    # Shorter lookback for faster signals
    LOOKBACK_DAYS = 126  # 6-month momentum
    SHORT_LOOKBACK = 42  # 2-month for confirmation

    # More aggressive assets
    STOCK_SYMBOL = "QQQ"  # Nasdaq-100
    BOND_SYMBOL = "TLT"   # Long-term treasuries (more volatile)
    CASH_SYMBOL = "SHY"   # Cash equivalent

    LEVERAGE = 1.2

    def initialize(self):
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2026, 1, 9)
        self.set_cash(100000)

        self.qqq = self.add_equity(self.STOCK_SYMBOL, Resolution.DAILY).symbol
        self.tlt = self.add_equity(self.BOND_SYMBOL, Resolution.DAILY).symbol
        self.shy = self.add_equity(self.CASH_SYMBOL, Resolution.DAILY).symbol

        self.set_benchmark(self.qqq)

        self.current_asset = None

        self.set_warmup(timedelta(days=self.LOOKBACK_DAYS + 10))

        # Weekly check for faster response
        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.after_market_open(self.qqq, 30),
            self.rebalance
        )

    def calculate_momentum(self, symbol, lookback):
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

        # 6-month momentum
        qqq_mom = self.calculate_momentum(self.qqq, self.LOOKBACK_DAYS)
        tlt_mom = self.calculate_momentum(self.tlt, self.LOOKBACK_DAYS)

        # 2-month momentum for confirmation
        qqq_short = self.calculate_momentum(self.qqq, self.SHORT_LOOKBACK)
        tlt_short = self.calculate_momentum(self.tlt, self.SHORT_LOOKBACK)

        if qqq_mom is None or tlt_mom is None:
            return

        target_asset = None

        # More aggressive logic:
        # QQQ if it's positive OR if it's better than TLT (even if negative)
        if qqq_mom > 0 and qqq_mom > tlt_mom:
            target_asset = self.qqq
        elif qqq_mom > tlt_mom and qqq_short is not None and qqq_short > 0:
            # QQQ recovering, switch back
            target_asset = self.qqq
        elif tlt_mom > 0:
            target_asset = self.tlt
        elif tlt_mom > qqq_mom:
            # TLT less bad than QQQ
            target_asset = self.tlt
        else:
            target_asset = self.shy

        if target_asset != self.current_asset:
            self.liquidate()
            self.set_holdings(target_asset, self.LEVERAGE)
            self.current_asset = target_asset
            self.log(f"Switch to {target_asset.value}: QQQ={qqq_mom*100:.1f}%, TLT={tlt_mom*100:.1f}%")

    def on_data(self, data):
        pass
