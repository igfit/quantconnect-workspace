"""
Donchian 20/10 Breakout Strategy

Classic trend-following system made famous by the Turtle Traders.
Buy on 20-day high breakout, exit on 10-day low.

Universe: Large-Cap Liquid (Universe C) - 80+ mega-cap stocks
Rebalance: Daily signal check
Holding Period: Variable (trend dependent)

WHY THIS WORKS:
- Breakout to new highs often signals continuation of trend
- Asymmetric exits (faster exit) help preserve profits
- Works best on stocks with trending characteristics
- Time-tested since 1960s (Richard Donchian)

KEY PARAMETERS:
- ENTRY_PERIOD = 20 (buy on 20-day high)
- EXIT_PERIOD = 10 (exit on 10-day low)
- MAX_POSITIONS = 10 (diversification limit)
- REGIME_FILTER = True (only enter when SPY > 200 SMA)

EXPECTED CHARACTERISTICS:
- Win rate: 35-45% (trend following has lower win rate)
- Larger winners than losers
- Works in trending markets
- Struggles in choppy/range-bound markets
"""

from AlgorithmImports import *
from datetime import timedelta
from collections import deque


class DonchianBreakout(QCAlgorithm):
    """
    Donchian Channel Breakout on Large-Cap Universe

    Rules:
    1. Long entry when price breaks above 20-day high
    2. Exit when price breaks below 10-day low
    3. Max 10 positions at a time
    4. Only enter when SPY > 200 SMA (regime filter)
    """

    # Configuration
    ENTRY_PERIOD = 20  # Days for entry channel
    EXIT_PERIOD = 10   # Days for exit channel
    MAX_POSITIONS = 10  # Maximum concurrent positions
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

        # Add all stocks and create Donchian channels
        self.stocks = []
        self.entry_channels = {}  # 20-day highs
        self.exit_channels = {}   # 10-day lows
        self.high_windows = {}    # Rolling high tracker
        self.low_windows = {}     # Rolling low tracker

        for ticker in self.universe_symbols:
            equity = self.add_equity(ticker, Resolution.DAILY)
            equity.set_slippage_model(ConstantSlippageModel(0.001))
            equity.set_fee_model(InteractiveBrokersFeeModel())
            symbol = equity.symbol
            self.stocks.append(symbol)

            # Custom rolling windows for Donchian channels
            self.high_windows[symbol] = deque(maxlen=self.ENTRY_PERIOD)
            self.low_windows[symbol] = deque(maxlen=self.EXIT_PERIOD)

        # SPY for regime filter and benchmark
        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.set_benchmark(self.spy)

        # Regime filter: 200-day SMA
        self.spy_sma = self.sma(self.spy, 200, Resolution.DAILY)

        # Position tracking
        self.positions = {}  # symbol -> entry_price
        self.completed_trades = []

        # Warmup
        self.set_warmup(timedelta(days=30))

        # Check signals at market close
        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.before_market_close(self.spy, 5),
            self.check_signals
        )

    def on_data(self, data):
        """Update rolling windows with new price data (including warmup)"""
        # Update windows even during warmup to build history
        for symbol in self.stocks:
            if data.contains_key(symbol) and data[symbol] is not None:
                bar = data[symbol]
                self.high_windows[symbol].append(bar.high)
                self.low_windows[symbol].append(bar.low)

    def get_entry_high(self, symbol) -> float:
        """Get 20-day high for entry signal (excluding today)"""
        if len(self.high_windows[symbol]) < self.ENTRY_PERIOD:
            return None
        # Exclude today's high (last element) to check for breakout
        highs = list(self.high_windows[symbol])[:-1] if len(self.high_windows[symbol]) > 1 else []
        return max(highs) if highs else None

    def get_exit_low(self, symbol) -> float:
        """Get 10-day low for exit signal (excluding today)"""
        if len(self.low_windows[symbol]) < self.EXIT_PERIOD:
            return None
        # Exclude today's low (last element)
        lows = list(self.low_windows[symbol])[:-1] if len(self.low_windows[symbol]) > 1 else []
        return min(lows) if lows else None

    def check_signals(self):
        """Check for entry/exit signals"""
        if self.is_warming_up:
            return

        # Check regime filter
        in_bull_regime = True
        if self.USE_REGIME_FILTER:
            if not self.spy_sma.is_ready:
                return
            in_bull_regime = self.securities[self.spy].price > self.spy_sma.current.value

        # Process exits first (free up capital)
        for symbol in list(self.positions.keys()):
            exit_low = self.get_exit_low(symbol)
            if exit_low is None:
                continue

            price = self.securities[symbol].price
            if price < exit_low:
                self.exit_position(symbol, f"Below {self.EXIT_PERIOD}-day low")

        # Process entries (only if in bull regime)
        if not in_bull_regime:
            return

        # Check for entry signals
        num_positions = len(self.positions)
        if num_positions >= self.MAX_POSITIONS:
            return

        # Rank stocks by breakout strength (% above 20-day high)
        breakout_candidates = []
        for symbol in self.stocks:
            if symbol in self.positions:
                continue

            entry_high = self.get_entry_high(symbol)
            if entry_high is None:
                continue

            price = self.securities[symbol].price
            if price <= 0:
                continue

            # Check for breakout
            if price > entry_high:
                breakout_pct = (price - entry_high) / entry_high
                breakout_candidates.append((symbol, breakout_pct))

        # Sort by breakout strength (strongest first)
        breakout_candidates.sort(key=lambda x: x[1], reverse=True)

        # Enter positions (up to max)
        positions_to_add = self.MAX_POSITIONS - num_positions
        for symbol, _ in breakout_candidates[:positions_to_add]:
            self.enter_position(symbol)

    def enter_position(self, symbol):
        """Enter long position"""
        price = self.securities[symbol].price

        # Equal weight allocation
        weight = 0.99 / self.MAX_POSITIONS
        self.set_holdings(symbol, weight)

        self.positions[symbol] = {
            'entry_price': price,
            'entry_date': self.time,
            'entry_high': self.get_entry_high(symbol),
        }

        self.log(f"ENTRY: {symbol} @ ${price:.2f} (>{self.ENTRY_PERIOD}d high)")

    def exit_position(self, symbol, reason: str):
        """Exit position and log trade"""
        if symbol not in self.positions:
            return

        entry_info = self.positions[symbol]
        exit_price = self.securities[symbol].price
        pnl_pct = (exit_price - entry_info['entry_price']) / entry_info['entry_price']
        days_held = (self.time - entry_info['entry_date']).days

        self.liquidate(symbol)

        # Log completed trade
        self.completed_trades.append({
            'symbol': str(symbol),
            'entry_date': str(entry_info['entry_date'].date()),
            'exit_date': str(self.time.date()),
            'entry_price': entry_info['entry_price'],
            'exit_price': exit_price,
            'pnl_pct': pnl_pct,
            'days_held': days_held,
        })

        self.log(f"EXIT: {symbol} | {reason} | P&L={pnl_pct*100:.1f}% | Days={days_held}")

        del self.positions[symbol]

    def on_end_of_algorithm(self):
        """Log summary at end of backtest"""
        self.log("=" * 60)
        self.log("DONCHIAN BREAKOUT - TRADE SUMMARY")
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
