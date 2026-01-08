"""
SMA Crossover Test Strategy

Simple 50/200 SMA crossover on SPY to validate infrastructure.
Uses the BaseSwingStrategy framework.

Expected behavior:
- Long when SMA50 crosses above SMA200 (golden cross)
- Exit when SMA50 crosses below SMA200 (death cross)
- Regime filter disabled to isolate signal testing

This is a TEST strategy to validate the framework works correctly.
Do NOT use for actual trading decisions.
"""

from AlgorithmImports import *
from datetime import timedelta
from typing import List


class SmaCrossoverTestStrategy(QCAlgorithm):
    """
    SMA 50/200 Crossover on SPY

    This is a simplified version that doesn't inherit from BaseSwingStrategy
    to test independently, but follows the same patterns.
    """

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
        self.sma50 = self.sma(self.spy, 50, Resolution.DAILY)
        self.sma200 = self.sma(self.spy, 200, Resolution.DAILY)

        # Track previous values for crossover detection
        self.prev_sma50 = None
        self.prev_sma200 = None

        # Position tracking
        self.entry_price = None
        self.entry_date = None

        # Trade log
        self.completed_trades = []

        # Warmup
        self.set_warmup(timedelta(days=210))

        # Schedule events
        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.before_market_close("SPY", 5),
            self.check_signals
        )

    def check_signals(self):
        """Check for entry/exit signals at market close"""
        if self.is_warming_up:
            return

        if not self.sma50.is_ready or not self.sma200.is_ready:
            return

        # Get current values
        sma50_val = self.sma50.current.value
        sma200_val = self.sma200.current.value
        price = self.securities[self.spy].price

        # Skip if no previous values yet
        if self.prev_sma50 is None:
            self.prev_sma50 = sma50_val
            self.prev_sma200 = sma200_val
            return

        # Check for golden cross (SMA50 crosses above SMA200)
        golden_cross = self.prev_sma50 <= self.prev_sma200 and sma50_val > sma200_val

        # Check for death cross (SMA50 crosses below SMA200)
        death_cross = self.prev_sma50 >= self.prev_sma200 and sma50_val < sma200_val

        # Execute signals
        if not self.portfolio[self.spy].invested:
            if golden_cross:
                # Entry
                shares = int(self.portfolio.cash * 0.95 / price)  # 95% of cash
                if shares > 0:
                    self.market_order(self.spy, shares)
                    self.entry_price = price
                    self.entry_date = self.time
                    self.log(f"GOLDEN CROSS ENTRY: {shares} shares @ ${price:.2f}")
        else:
            if death_cross:
                # Exit
                shares = self.portfolio[self.spy].quantity
                exit_price = price
                pnl = (exit_price - self.entry_price) * shares
                pnl_pct = (exit_price - self.entry_price) / self.entry_price
                days_held = (self.time - self.entry_date).days if self.entry_date else 0

                self.liquidate(self.spy)
                self.log(f"DEATH CROSS EXIT: {shares} shares @ ${price:.2f} | P&L: ${pnl:.0f} ({pnl_pct*100:.1f}%)")

                # Log trade
                self.completed_trades.append({
                    'entry_date': str(self.entry_date.date()) if self.entry_date else '',
                    'exit_date': str(self.time.date()),
                    'entry_price': self.entry_price,
                    'exit_price': exit_price,
                    'shares': shares,
                    'pnl': pnl,
                    'pnl_pct': pnl_pct,
                    'days_held': days_held,
                })

                self.entry_price = None
                self.entry_date = None

        # Update previous values
        self.prev_sma50 = sma50_val
        self.prev_sma200 = sma200_val

    def on_end_of_algorithm(self):
        """Log summary at end of backtest"""
        self.log("=" * 60)
        self.log("SMA CROSSOVER TEST - TRADE SUMMARY")
        self.log("=" * 60)

        if not self.completed_trades:
            self.log("No completed trades")
            return

        total_trades = len(self.completed_trades)
        winners = [t for t in self.completed_trades if t['pnl'] > 0]
        losers = [t for t in self.completed_trades if t['pnl'] <= 0]

        win_rate = len(winners) / total_trades * 100 if total_trades > 0 else 0
        total_pnl = sum(t['pnl'] for t in self.completed_trades)
        avg_win = sum(t['pnl_pct'] for t in winners) / len(winners) * 100 if winners else 0
        avg_loss = sum(t['pnl_pct'] for t in losers) / len(losers) * 100 if losers else 0
        avg_days = sum(t['days_held'] for t in self.completed_trades) / total_trades

        self.log(f"Total Trades: {total_trades}")
        self.log(f"Winners: {len(winners)} | Losers: {len(losers)}")
        self.log(f"Win Rate: {win_rate:.1f}%")
        self.log(f"Total P&L: ${total_pnl:,.0f}")
        self.log(f"Avg Win: {avg_win:.1f}% | Avg Loss: {avg_loss:.1f}%")
        self.log(f"Avg Holding Days: {avg_days:.0f}")

        if avg_loss != 0:
            self.log(f"Risk/Reward: {abs(avg_win/avg_loss):.2f}")

        self.log("=" * 60)

    def on_data(self, data):
        """Required method - signals generated via scheduled event"""
        pass
