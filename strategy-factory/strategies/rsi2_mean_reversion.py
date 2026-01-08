"""
RSI-2 Mean Reversion Strategy

Classic short-term mean reversion on SPY using 2-period RSI.
Buy when RSI(2) < 10, sell when RSI(2) > 90.

Universe: Single Instrument - SPY (Universe E)
Holding Period: 1-5 days typically
Trade Frequency: ~10-20 trades per year

WHY THIS WORKS:
- Short-term oversold/overbought conditions tend to revert
- 2-period RSI is very sensitive to short-term extremes
- Works best in trending markets (SPY has upward drift)
- Well-documented by Larry Connors in "Short Term Trading Strategies That Work"

KEY PARAMETERS:
- RSI_PERIOD = 2 (very short-term)
- OVERSOLD = 10 (entry threshold)
- OVERBOUGHT = 90 (exit threshold)
- USE_REGIME_FILTER = True (only trade when SPY > 200 SMA)

EXPECTED CHARACTERISTICS:
- Win rate: 70-85% (mean reversion tends to win often)
- Small average win, occasional larger loss
- Works well in bull markets, struggles in crashes
- Higher trade frequency than momentum strategies
"""

from AlgorithmImports import *
from datetime import timedelta


class RSI2MeanReversion(QCAlgorithm):
    """
    RSI-2 Mean Reversion on SPY

    Rules:
    1. Long when RSI(2) < 10 (oversold)
    2. Exit when RSI(2) > 90 (overbought)
    3. Optional: Only trade when SPY > 200 SMA (regime filter)
    """

    # Configuration
    RSI_PERIOD = 2
    OVERSOLD = 10
    OVERBOUGHT = 90
    USE_REGIME_FILTER = True

    def initialize(self):
        # Backtest period
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Add SPY
        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.set_benchmark(self.spy)

        # Execution settings
        spy.set_slippage_model(ConstantSlippageModel(0.001))
        spy.set_fee_model(InteractiveBrokersFeeModel())

        # Indicators
        self.rsi = self.rsi_indicator(self.spy, self.RSI_PERIOD, MovingAverageType.WILDERS, Resolution.DAILY)
        self.sma200 = self.sma(self.spy, 200, Resolution.DAILY)

        # Position tracking
        self.entry_price = None
        self.entry_date = None

        # Trade log
        self.completed_trades = []

        # Warmup
        self.set_warmup(timedelta(days=210))

        # Check signals at market close
        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.before_market_close(self.spy, 5),
            self.check_signals
        )

    def rsi_indicator(self, symbol, period, ma_type, resolution):
        """Create RSI indicator (avoiding name shadowing)"""
        return self.rsi(symbol, period, ma_type, resolution)

    def check_signals(self):
        """Check for entry/exit signals"""
        if self.is_warming_up:
            return

        if not self.rsi.is_ready or not self.sma200.is_ready:
            return

        price = self.securities[self.spy].price
        rsi_value = self.rsi.current.value
        sma_value = self.sma200.current.value

        # Check regime filter
        in_bull_regime = price > sma_value

        if self.portfolio[self.spy].invested:
            # Check exit: RSI > overbought threshold
            if rsi_value > self.OVERBOUGHT:
                self.exit_position("RSI Overbought")
        else:
            # Check entry: RSI < oversold threshold AND in bull regime
            if rsi_value < self.OVERSOLD:
                if self.USE_REGIME_FILTER and not in_bull_regime:
                    self.log(f"SKIP ENTRY: RSI={rsi_value:.1f} but SPY below 200 SMA")
                    return
                self.enter_position(rsi_value)

    def enter_position(self, rsi_value: float):
        """Enter long position"""
        price = self.securities[self.spy].price

        # Use 95% of portfolio
        self.set_holdings(self.spy, 0.95)

        self.entry_price = price
        self.entry_date = self.time

        self.log(f"ENTRY: RSI={rsi_value:.1f} | Price=${price:.2f}")

    def exit_position(self, reason: str):
        """Exit position and log trade"""
        if not self.portfolio[self.spy].invested:
            return

        exit_price = self.securities[self.spy].price
        pnl_pct = (exit_price - self.entry_price) / self.entry_price if self.entry_price else 0
        days_held = (self.time - self.entry_date).days if self.entry_date else 0

        self.liquidate(self.spy)

        # Log completed trade
        self.completed_trades.append({
            'entry_date': str(self.entry_date.date()) if self.entry_date else '',
            'exit_date': str(self.time.date()),
            'entry_price': self.entry_price,
            'exit_price': exit_price,
            'pnl_pct': pnl_pct,
            'days_held': days_held,
            'reason': reason,
        })

        self.log(f"EXIT: {reason} | P&L={pnl_pct*100:.1f}% | Days={days_held}")

        self.entry_price = None
        self.entry_date = None

    def on_end_of_algorithm(self):
        """Log summary at end of backtest"""
        self.log("=" * 60)
        self.log("RSI-2 MEAN REVERSION - TRADE SUMMARY")
        self.log("=" * 60)

        if not self.completed_trades:
            self.log("No completed trades")
            return

        total_trades = len(self.completed_trades)
        winners = [t for t in self.completed_trades if t['pnl_pct'] > 0]
        losers = [t for t in self.completed_trades if t['pnl_pct'] <= 0]

        win_rate = len(winners) / total_trades * 100 if total_trades > 0 else 0
        avg_win = sum(t['pnl_pct'] for t in winners) / len(winners) * 100 if winners else 0
        avg_loss = sum(t['pnl_pct'] for t in losers) / len(losers) * 100 if losers else 0
        avg_days = sum(t['days_held'] for t in self.completed_trades) / total_trades

        self.log(f"Total Trades: {total_trades}")
        self.log(f"Winners: {len(winners)} | Losers: {len(losers)}")
        self.log(f"Win Rate: {win_rate:.1f}%")
        self.log(f"Avg Win: {avg_win:.1f}% | Avg Loss: {avg_loss:.1f}%")
        if avg_loss != 0:
            self.log(f"Risk/Reward: {abs(avg_win/avg_loss):.2f}")
        self.log(f"Avg Holding Days: {avg_days:.1f}")
        self.log("=" * 60)

    def on_data(self, data):
        """Required method - signals checked via scheduled event"""
        pass
