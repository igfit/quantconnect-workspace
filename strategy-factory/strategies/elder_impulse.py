"""
Elder Impulse System Strategy

Based on Alexander Elder's "Trading for a Living" methodology.
Combines EMA (trend) with MACD Histogram (momentum) for entry/exit signals.

Universe: Large-Cap Liquid (Universe C) - 80+ mega-cap stocks
Rebalance: Daily signal check
Holding Period: Variable (trend dependent)

WHY THIS WORKS:
- Combines trend (EMA) and momentum (MACD-H) for confirmation
- Avoids buying in declining trends
- Green impulse = strong buying pressure
- Time-tested system from professional trader

KEY PARAMETERS:
- EMA_PERIOD = 13 (short-term trend)
- MACD_FAST = 12, MACD_SLOW = 26, MACD_SIGNAL = 9 (standard MACD)
- MAX_POSITIONS = 10 (diversification limit)
- REGIME_FILTER = True (only enter when SPY > 200 SMA)

IMPULSE COLORS:
- GREEN: EMA rising AND MACD-H rising → BUY signal
- RED: EMA falling AND MACD-H falling → SELL signal
- BLUE: Mixed → HOLD (no new entries)

EXPECTED CHARACTERISTICS:
- Win rate: 45-55%
- Catches strong trends early
- Multiple confirmations reduce whipsaws
- Works across different market conditions
"""

from AlgorithmImports import *
from datetime import timedelta


class ElderImpulseSystem(QCAlgorithm):
    """
    Elder Impulse System on Large-Cap Universe

    Rules:
    1. Calculate impulse color for each stock (GREEN, RED, BLUE)
    2. Enter long when impulse turns GREEN from non-GREEN
    3. Exit when impulse turns RED
    4. Max 10 positions at a time
    5. Only enter when SPY > 200 SMA (regime filter)
    """

    # Configuration
    EMA_PERIOD = 13
    MACD_FAST = 12
    MACD_SLOW = 26
    MACD_SIGNAL = 9
    MAX_POSITIONS = 10
    USE_REGIME_FILTER = True

    # Impulse colors
    GREEN = "GREEN"  # Both rising
    RED = "RED"      # Both falling
    BLUE = "BLUE"    # Mixed

    def initialize(self):
        # Backtest period
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Large-cap liquid universe (Universe C)
        self.universe_symbols = [
            # Technology
            "AAPL", "MSFT", "GOOGL", "INTC", "CSCO", "ORCL", "IBM", "QCOM", "TXN", "ADBE", "CRM", "AVGO",
            # Financials
            "JPM", "BAC", "WFC", "C", "GS", "MS", "BLK", "AXP", "USB", "PNC",
            # Healthcare
            "JNJ", "UNH", "PFE", "MRK", "ABBV", "TMO", "ABT", "MDT", "AMGN", "GILD", "BMY", "LLY",
            # Consumer
            "AMZN", "HD", "MCD", "NKE", "SBUX", "TGT", "COST", "LOW", "TJX",
            # Industrials
            "BA", "HON", "UNP", "CAT", "GE", "MMM", "LMT", "RTX", "DE", "FDX",
            # Energy
            "XOM", "CVX", "COP", "SLB", "EOG",
            # Communications
            "META", "NFLX", "DIS", "CMCSA", "VZ", "T",
            # Consumer Staples
            "KO", "PEP", "PM", "WMT", "PG", "CL",
            # Other
            "BRK.B", "V", "MA",
            # Utilities
            "NEE", "DUK", "SO",
        ]

        # Add stocks and create indicators
        self.stocks = []
        self.ema_indicators = {}
        self.macd_indicators = {}
        self.prev_ema = {}
        self.prev_macd_h = {}

        for ticker in self.universe_symbols:
            equity = self.add_equity(ticker, Resolution.DAILY)
            equity.set_slippage_model(ConstantSlippageModel(0.001))
            equity.set_fee_model(InteractiveBrokersFeeModel())
            symbol = equity.symbol
            self.stocks.append(symbol)

            # Create indicators (no Resolution parameter for MACD)
            self.ema_indicators[symbol] = self.ema(symbol, self.EMA_PERIOD, Resolution.DAILY)
            self.macd_indicators[symbol] = self.macd(symbol, self.MACD_FAST, self.MACD_SLOW, self.MACD_SIGNAL)

            # Previous values for direction
            self.prev_ema[symbol] = None
            self.prev_macd_h[symbol] = None

        # SPY for regime filter and benchmark
        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.set_benchmark(self.spy)

        # Regime filter: 200-day SMA
        self.spy_sma = self.sma(self.spy, 200, Resolution.DAILY)

        # Position tracking
        self.positions = {}
        self.prev_impulse = {}  # Track previous impulse color
        self.completed_trades = []

        # Warmup
        self.set_warmup(timedelta(days=60))

        # Check signals daily
        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.before_market_close(self.spy, 5),
            self.check_signals
        )

    def get_impulse_color(self, symbol) -> str:
        """
        Calculate Elder Impulse color.
        GREEN = EMA rising AND MACD-H rising
        RED = EMA falling AND MACD-H falling
        BLUE = mixed
        """
        ema = self.ema_indicators[symbol]
        macd = self.macd_indicators[symbol]

        if not ema.is_ready or not macd.is_ready:
            return None

        curr_ema = ema.current.value
        curr_macd_h = macd.histogram.current.value

        prev_ema = self.prev_ema[symbol]
        prev_macd_h = self.prev_macd_h[symbol]

        if prev_ema is None or prev_macd_h is None:
            return None

        ema_rising = curr_ema > prev_ema
        ema_falling = curr_ema < prev_ema
        macd_h_rising = curr_macd_h > prev_macd_h
        macd_h_falling = curr_macd_h < prev_macd_h

        if ema_rising and macd_h_rising:
            return self.GREEN
        elif ema_falling and macd_h_falling:
            return self.RED
        else:
            return self.BLUE

    def update_previous_values(self):
        """Store current values as previous for next comparison"""
        for symbol in self.stocks:
            ema = self.ema_indicators[symbol]
            macd = self.macd_indicators[symbol]

            if ema.is_ready:
                self.prev_ema[symbol] = ema.current.value
            if macd.is_ready:
                self.prev_macd_h[symbol] = macd.histogram.current.value

    def check_signals(self):
        """Check for Elder Impulse entry/exit signals"""
        if self.is_warming_up:
            # Still update values during warmup
            self.update_previous_values()
            return

        # Check regime filter
        in_bull_regime = True
        if self.USE_REGIME_FILTER:
            if not self.spy_sma.is_ready:
                return
            in_bull_regime = self.securities[self.spy].price > self.spy_sma.current.value

        # Check exits first
        for symbol in list(self.positions.keys()):
            impulse = self.get_impulse_color(symbol)
            if impulse == self.RED:
                self.exit_position(symbol, "Impulse turned RED")

        # Check entries (only in bull regime)
        if in_bull_regime and len(self.positions) < self.MAX_POSITIONS:
            entry_candidates = []

            for symbol in self.stocks:
                if symbol in self.positions:
                    continue

                impulse = self.get_impulse_color(symbol)
                prev_impulse = self.prev_impulse.get(symbol)

                # Entry: impulse turns GREEN from non-GREEN
                if impulse == self.GREEN and prev_impulse != self.GREEN:
                    # Get MACD histogram for ranking
                    macd = self.macd_indicators[symbol]
                    if macd.is_ready:
                        entry_candidates.append((symbol, macd.histogram.current.value))

            # Sort by MACD histogram strength
            entry_candidates.sort(key=lambda x: x[1], reverse=True)

            # Enter top candidates
            positions_to_add = self.MAX_POSITIONS - len(self.positions)
            for symbol, _ in entry_candidates[:positions_to_add]:
                self.enter_position(symbol)

        # Update previous impulse colors and values
        for symbol in self.stocks:
            impulse = self.get_impulse_color(symbol)
            if impulse:
                self.prev_impulse[symbol] = impulse

        self.update_previous_values()

    def enter_position(self, symbol):
        """Enter long position"""
        price = self.securities[symbol].price

        # Equal weight allocation
        weight = 0.99 / self.MAX_POSITIONS
        self.set_holdings(symbol, weight)

        self.positions[symbol] = {
            'entry_price': price,
            'entry_date': self.time,
        }

        self.log(f"ENTRY: {symbol} @ ${price:.2f} (GREEN impulse)")

    def exit_position(self, symbol, reason: str):
        """Exit position and log trade"""
        if symbol not in self.positions:
            return

        pos = self.positions[symbol]
        exit_price = self.securities[symbol].price
        pnl_pct = (exit_price - pos['entry_price']) / pos['entry_price']
        days_held = (self.time - pos['entry_date']).days

        self.liquidate(symbol)

        # Log completed trade
        self.completed_trades.append({
            'symbol': str(symbol),
            'entry_date': str(pos['entry_date'].date()),
            'exit_date': str(self.time.date()),
            'entry_price': pos['entry_price'],
            'exit_price': exit_price,
            'pnl_pct': pnl_pct,
            'days_held': days_held,
        })

        self.log(f"EXIT: {symbol} | {reason} | P&L={pnl_pct*100:.1f}% | Days={days_held}")

        del self.positions[symbol]

    def on_end_of_algorithm(self):
        """Log summary at end of backtest"""
        self.log("=" * 60)
        self.log("ELDER IMPULSE SYSTEM - TRADE SUMMARY")
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
