"""
52-Week High Breakout Strategy

Buys stocks breaking to new 52-week highs, a sign of institutional interest.
Uses ATR-based trailing stop for exits.

Universe: Large-Cap Liquid (Universe C) - 80+ mega-cap stocks
Rebalance: Weekly signal check
Holding Period: Variable (trend dependent)

WHY THIS WORKS:
- New 52-week highs often signal institutional accumulation
- Breakout to new highs has no overhead resistance
- Large-cap stocks have more institutional following
- ATR trailing stop lets winners run

KEY PARAMETERS:
- HIGH_LOOKBACK = 252 (trading days in a year)
- ATR_MULTIPLIER = 3 (stop at 3 ATR below entry)
- MAX_POSITIONS = 10 (diversification limit)
- REGIME_FILTER = True (only enter when SPY > 200 SMA)

EXPECTED CHARACTERISTICS:
- Win rate: 40-50%
- Larger winners than losers
- Strong in bull markets
- ATR stop prevents catastrophic losses
"""

from AlgorithmImports import *
from datetime import timedelta


class Week52HighBreakout(QCAlgorithm):
    """
    52-Week High Breakout on Large-Cap Universe

    Rules:
    1. Buy when price breaks above 52-week high
    2. Place initial stop at entry - 3*ATR
    3. Trail stop as price makes higher lows
    4. Max 10 positions at a time
    5. Only enter when SPY > 200 SMA (regime filter)
    """

    # Configuration
    HIGH_LOOKBACK = 252  # Trading days for 52-week high
    ATR_PERIOD = 20      # ATR period for stop sizing
    ATR_MULTIPLIER = 3   # Stop distance in ATRs
    MAX_POSITIONS = 10   # Maximum concurrent positions
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

        # Add all stocks and create ATR indicators
        self.stocks = []
        self.atr_indicators = {}

        for ticker in self.universe_symbols:
            equity = self.add_equity(ticker, Resolution.DAILY)
            equity.set_slippage_model(ConstantSlippageModel(0.001))
            equity.set_fee_model(InteractiveBrokersFeeModel())
            symbol = equity.symbol
            self.stocks.append(symbol)
            self.atr_indicators[symbol] = self.atr(symbol, self.ATR_PERIOD)

        # SPY for regime filter and benchmark
        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.set_benchmark(self.spy)

        # Regime filter: 200-day SMA
        self.spy_sma = self.sma(self.spy, 200, Resolution.DAILY)

        # Position tracking
        self.positions = {}  # symbol -> position info
        self.completed_trades = []

        # Warmup
        self.set_warmup(timedelta(days=260))

        # Check signals weekly (Mondays)
        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.after_market_open(self.spy, 30),
            self.check_entry_signals
        )

        # Check stops daily
        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.before_market_close(self.spy, 5),
            self.check_stops
        )

    def get_52week_high(self, symbol) -> float:
        """Get 52-week high for the symbol (excluding today)"""
        history = self.history(symbol, self.HIGH_LOOKBACK + 1, Resolution.DAILY)
        if history.empty or len(history) < self.HIGH_LOOKBACK:
            return None
        # Exclude today (last row) to check if current price breaks previous 52-week high
        return history['high'].iloc[:-1].max()

    def check_entry_signals(self):
        """Check for 52-week high breakout entries"""
        if self.is_warming_up:
            return

        # Check regime filter
        if self.USE_REGIME_FILTER:
            if not self.spy_sma.is_ready:
                return
            if self.securities[self.spy].price < self.spy_sma.current.value:
                return  # Don't enter new positions in bear market

        num_positions = len(self.positions)
        if num_positions >= self.MAX_POSITIONS:
            return

        # Find breakout candidates
        breakout_candidates = []
        for symbol in self.stocks:
            if symbol in self.positions:
                continue

            week52_high = self.get_52week_high(symbol)
            if week52_high is None:
                continue

            price = self.securities[symbol].price
            if price <= 0:
                continue

            # Check for new 52-week high
            if price > week52_high:
                breakout_pct = (price - week52_high) / week52_high
                breakout_candidates.append((symbol, breakout_pct, week52_high))

        # Sort by breakout strength
        breakout_candidates.sort(key=lambda x: x[1], reverse=True)

        # Enter positions
        positions_to_add = self.MAX_POSITIONS - num_positions
        for symbol, _, week52_high in breakout_candidates[:positions_to_add]:
            self.enter_position(symbol, week52_high)

    def enter_position(self, symbol, week52_high: float):
        """Enter long position with ATR-based stop"""
        price = self.securities[symbol].price
        atr = self.atr_indicators[symbol].current.value if self.atr_indicators[symbol].is_ready else price * 0.02

        # Calculate initial stop
        initial_stop = price - (self.ATR_MULTIPLIER * atr)

        # Equal weight allocation
        weight = 0.99 / self.MAX_POSITIONS
        self.set_holdings(symbol, weight)

        self.positions[symbol] = {
            'entry_price': price,
            'entry_date': self.time,
            'week52_high': week52_high,
            'initial_stop': initial_stop,
            'trailing_stop': initial_stop,
            'highest_price': price,
        }

        self.log(f"ENTRY: {symbol} @ ${price:.2f} (>52wk high ${week52_high:.2f}) Stop=${initial_stop:.2f}")

    def check_stops(self):
        """Check and update trailing stops"""
        if self.is_warming_up:
            return

        for symbol in list(self.positions.keys()):
            pos = self.positions[symbol]
            price = self.securities[symbol].price
            atr = self.atr_indicators[symbol].current.value if self.atr_indicators[symbol].is_ready else price * 0.02

            # Update highest price
            if price > pos['highest_price']:
                pos['highest_price'] = price
                # Trail stop up
                new_stop = price - (self.ATR_MULTIPLIER * atr)
                if new_stop > pos['trailing_stop']:
                    pos['trailing_stop'] = new_stop

            # Check if stopped out
            if price < pos['trailing_stop']:
                self.exit_position(symbol, f"Trailing stop @ ${pos['trailing_stop']:.2f}")

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
            'max_gain': (pos['highest_price'] - pos['entry_price']) / pos['entry_price'],
        })

        self.log(f"EXIT: {symbol} | {reason} | P&L={pnl_pct*100:.1f}% | Days={days_held}")

        del self.positions[symbol]

    def on_end_of_algorithm(self):
        """Log summary at end of backtest"""
        self.log("=" * 60)
        self.log("52-WEEK HIGH BREAKOUT - TRADE SUMMARY")
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

        # Track which stocks were most selected
        stock_counts = {}
        for t in self.completed_trades:
            ticker = t['symbol'].split()[0]
            stock_counts[ticker] = stock_counts.get(ticker, 0) + 1

        self.log("\nMost Traded Stocks:")
        for ticker, count in sorted(stock_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
            self.log(f"  {ticker}: {count} trades")

        self.log("=" * 60)

    def on_data(self, data):
        """Required method - signals checked via scheduled events"""
        pass
