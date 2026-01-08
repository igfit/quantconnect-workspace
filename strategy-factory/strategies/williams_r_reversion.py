"""
Williams %R Mean Reversion Strategy

Short-term mean reversion on SPY using Williams %R oscillator.
Buy when %R < -90 (oversold), sell when %R > -10 (overbought).

Universe: Single Instrument - SPY (Universe E)
Holding Period: 1-5 days typically
Trade Frequency: ~15-25 trades per year

WHY THIS WORKS:
- Williams %R measures where price closed relative to the high-low range
- Extreme values (-100 to -80) indicate oversold conditions
- Mean reversion is strongest in trending markets
- Similar to RSI but more sensitive to recent price action

KEY PARAMETERS:
- WILLIAMS_PERIOD = 10 (10-day lookback)
- OVERSOLD = -90 (entry threshold)
- OVERBOUGHT = -10 (exit threshold)
- USE_REGIME_FILTER = True (only trade when SPY > 200 SMA)

EXPECTED CHARACTERISTICS:
- Win rate: 70-80% (mean reversion)
- Lower risk/reward than trend-following
- Best in sideways-to-up markets
- Struggles in strong downtrends
"""

from AlgorithmImports import *
from datetime import timedelta


class WilliamsRMeanReversion(QCAlgorithm):
    """
    Williams %R Mean Reversion on SPY

    Rules:
    1. Long when Williams %R < -90 (oversold)
    2. Exit when Williams %R > -10 (overbought)
    3. Optional: Only trade when SPY > 200 SMA (regime filter)

    Note: Williams %R ranges from -100 (oversold) to 0 (overbought)
    """

    # Configuration
    WILLIAMS_PERIOD = 10
    OVERSOLD = -90  # Below -90 is oversold
    OVERBOUGHT = -10  # Above -10 is overbought
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
        self.williams_r = self.wilr(self.spy, self.WILLIAMS_PERIOD, Resolution.DAILY)
        self.sma200 = self.sma(self.spy, 200, Resolution.DAILY)

        # Position tracking
        self.entry_price = None
        self.entry_date = None
        self.entry_williams = None

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

    def check_signals(self):
        """Check for entry/exit signals"""
        if self.is_warming_up:
            return

        if not self.williams_r.is_ready or not self.sma200.is_ready:
            return

        price = self.securities[self.spy].price
        williams_value = self.williams_r.current.value
        sma_value = self.sma200.current.value

        # Check regime filter
        in_bull_regime = price > sma_value

        if self.portfolio[self.spy].invested:
            # Check exit: Williams %R > overbought threshold
            if williams_value > self.OVERBOUGHT:
                self.exit_position(f"Williams %R={williams_value:.1f}")
        else:
            # Check entry: Williams %R < oversold threshold AND in bull regime
            if williams_value < self.OVERSOLD:
                if self.USE_REGIME_FILTER and not in_bull_regime:
                    self.log(f"SKIP ENTRY: Williams %R={williams_value:.1f} but SPY below 200 SMA")
                    return
                self.enter_position(williams_value)

    def enter_position(self, williams_value: float):
        """Enter long position"""
        price = self.securities[self.spy].price

        # Use 95% of portfolio
        self.set_holdings(self.spy, 0.95)

        self.entry_price = price
        self.entry_date = self.time
        self.entry_williams = williams_value

        self.log(f"ENTRY: Williams %R={williams_value:.1f} | Price=${price:.2f}")

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
            'entry_williams': self.entry_williams,
            'pnl_pct': pnl_pct,
            'days_held': days_held,
        })

        self.log(f"EXIT: {reason} | P&L={pnl_pct*100:.1f}% | Days={days_held}")

        self.entry_price = None
        self.entry_date = None
        self.entry_williams = None

    def on_end_of_algorithm(self):
        """Log summary at end of backtest"""
        self.log("=" * 60)
        self.log("WILLIAMS %R MEAN REVERSION - TRADE SUMMARY")
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
