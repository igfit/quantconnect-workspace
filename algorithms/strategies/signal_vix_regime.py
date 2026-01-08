from AlgorithmImports import *

class SignalVIXRegime(QCAlgorithm):
    """
    SIGNAL-DRIVEN Strategy 3: VIX Regime Timing

    THESIS: Volatility regime determines risk exposure.
    The VIX SIGNAL is the edge, not stock picking.

    WHY THIS IS SIGNAL-DRIVEN:
    - Trade broad index (SPY) - no stock selection
    - VIX level determines position sizing
    - Edge comes from volatility timing

    Signal:
    - VIX < 15: Full risk-on (100% SPY)
    - VIX 15-25: Normal (80% SPY)
    - VIX 25-35: Reduce risk (50% SPY)
    - VIX > 35: Risk-off (0% SPY, all cash)
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100000)

        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.vix = self.add_data(CBOE, "VIX", Resolution.DAILY).symbol

        self.set_benchmark("SPY")
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)

        # Weekly rebalance based on VIX
        self.schedule.on(
            self.date_rules.every_day("SPY"),
            self.time_rules.after_market_open("SPY", 30),
            self.check_vix_regime
        )

        self.set_warm_up(30, Resolution.DAILY)
        self.current_regime = None

    def check_vix_regime(self):
        if self.is_warming_up:
            return

        if not self.securities.contains_key(self.vix):
            return

        vix_value = self.securities[self.vix].price

        if vix_value <= 0:
            return

        # Determine regime and target allocation
        if vix_value < 15:
            regime = "FULL_RISK"
            target = 1.0
        elif vix_value < 25:
            regime = "NORMAL"
            target = 0.8
        elif vix_value < 35:
            regime = "REDUCED"
            target = 0.5
        else:
            regime = "RISK_OFF"
            target = 0.0

        # Only trade on regime change
        if regime != self.current_regime:
            self.debug(f"VIX Regime Change: {self.current_regime} -> {regime} (VIX={vix_value:.1f})")
            self.current_regime = regime

            if target == 0:
                self.liquidate()
            else:
                self.set_holdings(self.spy, target)
