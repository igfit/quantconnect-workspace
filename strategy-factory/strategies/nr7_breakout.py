"""
NR7 Narrow Range Breakout Strategy

NR7 (Narrow Range 7) identifies days with the narrowest range in 7 days,
signaling volatility compression. Trades the subsequent expansion.

Universe: Large-Cap Liquid (Universe C) - 80+ mega-cap stocks
Rebalance: Daily signal check
Holding Period: 3-10 days typically

WHY THIS WORKS:
- Volatility compression often precedes expansion
- Narrow range days indicate equilibrium between buyers/sellers
- Breakout direction often continues
- Works best with trending stocks

KEY PARAMETERS:
- NR_LOOKBACK = 7 (narrowest range in 7 days)
- ATR_PERIOD = 14 (for stop calculation)
- ATR_STOP_MULT = 2 (stop at 2 ATR)
- MAX_POSITIONS = 10 (diversification limit)
- REGIME_FILTER = True (only enter when SPY > 200 SMA)

EXPECTED CHARACTERISTICS:
- Win rate: 45-55%
- Captures volatility expansion
- Quick trades (few days)
- Requires discipline on stops
"""

from AlgorithmImports import *
from datetime import timedelta
from collections import deque


class NR7Breakout(QCAlgorithm):
    """
    NR7 Narrow Range Breakout on Large-Cap Universe

    Rules:
    1. Identify NR7 days (narrowest high-low range in 7 days)
    2. Next day, buy on break above NR7 day high
    3. Place stop at entry - 2*ATR
    4. Exit on stop or after profit target
    5. Max 10 positions at a time
    """

    # Configuration
    NR_LOOKBACK = 7        # Days for narrow range comparison
    ATR_PERIOD = 14        # ATR period for stop
    ATR_STOP_MULT = 2      # Stop distance in ATRs
    ATR_TARGET_MULT = 3    # Profit target in ATRs
    MAX_POSITIONS = 10     # Maximum concurrent positions
    USE_REGIME_FILTER = True

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
        self.atr_indicators = {}
        self.range_windows = {}  # Rolling window of daily ranges
        self.prev_bar = {}       # Previous day's bar data

        for ticker in self.universe_symbols:
            equity = self.add_equity(ticker, Resolution.DAILY)
            equity.set_slippage_model(ConstantSlippageModel(0.001))
            equity.set_fee_model(InteractiveBrokersFeeModel())
            symbol = equity.symbol
            self.stocks.append(symbol)

            self.atr_indicators[symbol] = self.atr(symbol, self.ATR_PERIOD)
            self.range_windows[symbol] = deque(maxlen=self.NR_LOOKBACK)
            self.prev_bar[symbol] = None

        # SPY for regime filter and benchmark
        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.set_benchmark(self.spy)

        # Regime filter: 200-day SMA
        self.spy_sma = self.sma(self.spy, 200, Resolution.DAILY)

        # Position tracking
        self.positions = {}
        self.nr7_signals = {}  # Stocks with NR7 signal waiting for breakout
        self.completed_trades = []

        # Warmup
        self.set_warmup(timedelta(days=30))

        # Check for NR7 at end of day
        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.before_market_close(self.spy, 5),
            self.check_nr7_signals
        )

        # Check for entries at open
        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.after_market_open(self.spy, 30),
            self.check_entries
        )

    def on_data(self, data):
        """Update range windows and check stops"""
        if self.is_warming_up:
            return

        for symbol in self.stocks:
            if data.contains_key(symbol) and data[symbol] is not None:
                bar = data[symbol]
                daily_range = bar.high - bar.low
                self.range_windows[symbol].append(daily_range)

                # Store bar for NR7 check
                self.prev_bar[symbol] = {
                    'high': bar.high,
                    'low': bar.low,
                    'range': daily_range,
                }

        # Check stops for open positions
        self.check_stops()

    def is_nr7(self, symbol) -> bool:
        """Check if previous day was NR7 (narrowest range in 7 days)"""
        ranges = list(self.range_windows[symbol])
        if len(ranges) < self.NR_LOOKBACK:
            return False

        # Last range is the most recent day
        last_range = ranges[-1]
        min_range = min(ranges)

        return last_range == min_range

    def check_nr7_signals(self):
        """End of day: identify NR7 patterns for next day trading"""
        if self.is_warming_up:
            return

        # Clear old signals
        self.nr7_signals = {}

        for symbol in self.stocks:
            if symbol in self.positions:
                continue

            if self.is_nr7(symbol) and self.prev_bar.get(symbol):
                bar = self.prev_bar[symbol]
                self.nr7_signals[symbol] = {
                    'nr7_high': bar['high'],
                    'nr7_low': bar['low'],
                }

    def check_entries(self):
        """Check for NR7 breakout entries"""
        if self.is_warming_up:
            return

        # Check regime filter
        if self.USE_REGIME_FILTER:
            if not self.spy_sma.is_ready:
                return
            if self.securities[self.spy].price < self.spy_sma.current.value:
                return  # Don't enter in bear market

        if len(self.positions) >= self.MAX_POSITIONS:
            return

        # Check breakouts from NR7 signals
        entry_candidates = []
        for symbol, signal in list(self.nr7_signals.items()):
            if symbol in self.positions:
                continue

            price = self.securities[symbol].price
            if price <= 0:
                continue

            # Check for upside breakout
            if price > signal['nr7_high']:
                breakout_strength = (price - signal['nr7_high']) / signal['nr7_high']
                entry_candidates.append((symbol, signal, breakout_strength))

        # Sort by breakout strength
        entry_candidates.sort(key=lambda x: x[2], reverse=True)

        # Enter positions
        positions_to_add = self.MAX_POSITIONS - len(self.positions)
        for symbol, signal, _ in entry_candidates[:positions_to_add]:
            self.enter_position(symbol, signal)

    def enter_position(self, symbol, signal: dict):
        """Enter long position with ATR-based stop and target"""
        price = self.securities[symbol].price
        atr = self.atr_indicators[symbol].current.value if self.atr_indicators[symbol].is_ready else price * 0.02

        # Calculate stop and target
        stop_price = price - (self.ATR_STOP_MULT * atr)
        target_price = price + (self.ATR_TARGET_MULT * atr)

        # Equal weight allocation
        weight = 0.99 / self.MAX_POSITIONS
        self.set_holdings(symbol, weight)

        self.positions[symbol] = {
            'entry_price': price,
            'entry_date': self.time,
            'nr7_high': signal['nr7_high'],
            'stop_price': stop_price,
            'target_price': target_price,
        }

        self.log(f"ENTRY: {symbol} @ ${price:.2f} (NR7 breakout > ${signal['nr7_high']:.2f}) Stop=${stop_price:.2f} Target=${target_price:.2f}")

        # Remove from signals
        if symbol in self.nr7_signals:
            del self.nr7_signals[symbol]

    def check_stops(self):
        """Check stops and targets for open positions"""
        for symbol in list(self.positions.keys()):
            pos = self.positions[symbol]
            price = self.securities[symbol].price

            # Check stop
            if price < pos['stop_price']:
                self.exit_position(symbol, f"Stop @ ${pos['stop_price']:.2f}")
                continue

            # Check target
            if price > pos['target_price']:
                self.exit_position(symbol, f"Target @ ${pos['target_price']:.2f}")

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
        self.log("NR7 BREAKOUT - TRADE SUMMARY")
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
