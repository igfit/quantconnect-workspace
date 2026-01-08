from AlgorithmImports import *

class SignalMeanReversion(QCAlgorithm):
    """
    SIGNAL-DRIVEN Strategy 2: Mean Reversion RSI on QQQ

    THESIS: Buy oversold conditions, sell overbought.
    The RSI SIGNAL is the edge, not stock picking.

    WHY THIS IS SIGNAL-DRIVEN:
    - Single instrument (QQQ) - no stock selection
    - Pure timing signal based on RSI
    - Edge comes from WHEN to buy/sell, not WHAT to buy

    Signal:
    - Buy when RSI(14) < 30 (oversold)
    - Sell when RSI(14) > 70 (overbought)
    - Must be in uptrend (price > 200 SMA)
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100000)

        self.qqq = self.add_equity("QQQ", Resolution.DAILY).symbol

        # Signal indicators
        self.rsi = self.RSI(self.qqq, 14, MovingAverageType.WILDERS, Resolution.DAILY)
        self.sma200 = self.sma(self.qqq, 200)

        self.set_benchmark("QQQ")
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)

        self.set_warm_up(210, Resolution.DAILY)

        # Track position state
        self.invested = False

    def on_data(self, data):
        if self.is_warming_up:
            return

        if not self.rsi.is_ready or not self.sma200.is_ready:
            return

        if self.qqq not in data.bars:
            return

        price = data.bars[self.qqq].close
        rsi_value = self.rsi.current.value
        sma_value = self.sma200.current.value

        # Must be in uptrend for mean reversion to work
        in_uptrend = price > sma_value

        if not in_uptrend:
            # Exit if trend breaks
            if self.invested:
                self.liquidate()
                self.invested = False
            return

        # BUY SIGNAL: RSI oversold in uptrend
        if rsi_value < 30 and not self.invested:
            self.set_holdings(self.qqq, 1.0)
            self.invested = True
            self.debug(f"BUY: RSI={rsi_value:.1f}, Price={price:.2f}")

        # SELL SIGNAL: RSI overbought
        elif rsi_value > 70 and self.invested:
            self.liquidate()
            self.invested = False
            self.debug(f"SELL: RSI={rsi_value:.1f}, Price={price:.2f}")
