"""
Dual Momentum (Global Equities Momentum - GEM) Strategy

Based on Gary Antonacci's dual momentum approach:
1. RELATIVE MOMENTUM: Compare US stocks (SPY) vs International (EFA)
   - Hold whichever has higher 12-month return
2. ABSOLUTE MOMENTUM: If the winner has negative 12-month return
   - Move to bonds (BND) instead

Universe: ETF Core (Universe A) - Zero survivorship bias
Rebalance: Monthly (first trading day)
Holding Period: ~1 month (but can be longer in trends)

WHY THIS WORKS:
- Momentum is one of the most documented market anomalies
- Relative momentum captures which asset class is trending
- Absolute momentum provides crash protection (2008, 2020, 2022)
- Monthly rebalancing reduces transaction costs vs daily

EXPECTED CHARACTERISTICS:
- Win rate: ~55-60% (trend-following)
- Lower drawdowns than buy-and-hold during crashes
- May lag in V-shaped recoveries
- Works across different market regimes
"""

from AlgorithmImports import *
from datetime import timedelta


class DualMomentumGEM(QCAlgorithm):
    """
    Global Equities Momentum (GEM) - Dual Momentum Strategy

    Rules:
    1. Monthly rebalance on first trading day
    2. Calculate 12-month return for SPY and EFA
    3. If both negative → hold BND (absolute momentum filter)
    4. Otherwise → hold the one with higher return (relative momentum)
    """

    def initialize(self):
        # Backtest period
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Universe: Core ETFs for dual momentum
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol  # US Stocks
        self.efa = self.add_equity("EFA", Resolution.DAILY).symbol  # International
        self.bnd = self.add_equity("BND", Resolution.DAILY).symbol  # Bonds

        # Set benchmark
        self.set_benchmark(self.spy)

        # Execution settings
        for symbol in [self.spy, self.efa, self.bnd]:
            self.securities[symbol].set_slippage_model(ConstantSlippageModel(0.001))
            self.securities[symbol].set_fee_model(InteractiveBrokersFeeModel())

        # Momentum lookback period (12 months = ~252 trading days)
        self.lookback = 252

        # Track current holding
        self.current_holding = None

        # Trade log
        self.completed_trades = []
        self.entry_price = None
        self.entry_date = None

        # Warmup for momentum calculation
        self.set_warmup(timedelta(days=260))

        # Schedule monthly rebalance on first trading day of month
        self.schedule.on(
            self.date_rules.month_start(self.spy),
            self.time_rules.after_market_open(self.spy, 30),
            self.rebalance
        )

    def rebalance(self):
        """Monthly rebalance based on dual momentum rules"""
        if self.is_warming_up:
            return

        # Get 12-month returns
        spy_return = self.get_momentum(self.spy)
        efa_return = self.get_momentum(self.efa)

        if spy_return is None or efa_return is None:
            return

        # Determine target holding
        if spy_return <= 0 and efa_return <= 0:
            # Both negative → absolute momentum says go to bonds
            target = self.bnd
            reason = f"Absolute MOM: SPY={spy_return*100:.1f}%, EFA={efa_return*100:.1f}% → BND"
        elif spy_return > efa_return:
            # SPY has higher momentum
            target = self.spy
            reason = f"Relative MOM: SPY={spy_return*100:.1f}% > EFA={efa_return*100:.1f}%"
        else:
            # EFA has higher momentum
            target = self.efa
            reason = f"Relative MOM: EFA={efa_return*100:.1f}% > SPY={spy_return*100:.1f}%"

        # Only trade if target changed
        if target != self.current_holding:
            self.execute_switch(target, reason)

    def get_momentum(self, symbol) -> float:
        """Calculate 12-month momentum (return) for a symbol"""
        history = self.history(symbol, self.lookback + 1, Resolution.DAILY)

        if history.empty or len(history) < self.lookback:
            return None

        try:
            start_price = history['close'].iloc[0]
            end_price = history['close'].iloc[-1]
            return (end_price - start_price) / start_price
        except:
            return None

    def execute_switch(self, target, reason: str):
        """Switch holdings to new target"""
        # Log exit from current position
        if self.current_holding and self.portfolio[self.current_holding].invested:
            exit_price = self.securities[self.current_holding].price
            if self.entry_price and self.entry_date:
                pnl = (exit_price - self.entry_price) / self.entry_price
                days_held = (self.time - self.entry_date).days
                self.completed_trades.append({
                    'symbol': str(self.current_holding),
                    'entry_date': str(self.entry_date.date()),
                    'exit_date': str(self.time.date()),
                    'entry_price': self.entry_price,
                    'exit_price': exit_price,
                    'pnl_pct': pnl,
                    'days_held': days_held,
                })

        # Liquidate current position
        self.liquidate()

        # Enter new position (use 99% to leave room for fees)
        self.set_holdings(target, 0.99)
        self.current_holding = target
        self.entry_price = self.securities[target].price
        self.entry_date = self.time

        self.log(f"SWITCH → {target} | {reason}")

    def on_end_of_algorithm(self):
        """Log summary at end of backtest"""
        self.log("=" * 60)
        self.log("DUAL MOMENTUM (GEM) - TRADE SUMMARY")
        self.log("=" * 60)

        if not self.completed_trades:
            self.log("No completed trades")
            return

        # Summary stats
        total_trades = len(self.completed_trades)
        winners = [t for t in self.completed_trades if t['pnl_pct'] > 0]
        losers = [t for t in self.completed_trades if t['pnl_pct'] <= 0]

        win_rate = len(winners) / total_trades * 100 if total_trades > 0 else 0
        avg_win = sum(t['pnl_pct'] for t in winners) / len(winners) * 100 if winners else 0
        avg_loss = sum(t['pnl_pct'] for t in losers) / len(losers) * 100 if losers else 0
        avg_days = sum(t['days_held'] for t in self.completed_trades) / total_trades

        # Count by asset
        spy_trades = len([t for t in self.completed_trades if 'SPY' in t['symbol']])
        efa_trades = len([t for t in self.completed_trades if 'EFA' in t['symbol']])
        bnd_trades = len([t for t in self.completed_trades if 'BND' in t['symbol']])

        self.log(f"Total Trades: {total_trades}")
        self.log(f"  SPY: {spy_trades} | EFA: {efa_trades} | BND: {bnd_trades}")
        self.log(f"Winners: {len(winners)} | Losers: {len(losers)}")
        self.log(f"Win Rate: {win_rate:.1f}%")
        self.log(f"Avg Win: {avg_win:.1f}% | Avg Loss: {avg_loss:.1f}%")
        if avg_loss != 0:
            self.log(f"Risk/Reward: {abs(avg_win/avg_loss):.2f}")
        self.log(f"Avg Holding Days: {avg_days:.0f}")
        self.log("=" * 60)

    def on_data(self, data):
        """Required method - rebalancing done via scheduled event"""
        pass
