"""
SuperTrend Strategy on Sector ETFs

Uses the SuperTrend indicator for trend-following on sector ETFs.
SuperTrend = ATR-based trailing stop that flips long/short.

Universe: Sector SPDRs (Universe B) - Zero survivorship bias
Holding Period: Weeks to months (trend-following)
Trade Frequency: ~2-4 trades per sector per year

WHY THIS WORKS:
- SuperTrend captures medium-term trends using volatility-adjusted bands
- Sectors trend strongly during economic regime shifts
- ATR multiplier provides dynamic stop levels that adapt to volatility
- Trend-following on sectors diversifies the timing signal

KEY PARAMETERS:
- ATR_PERIOD = 10 (10-day ATR)
- ATR_MULTIPLIER = 3.0 (SuperTrend bands)
- MAX_POSITIONS = 4 (max sectors to hold)
- USE_REGIME_FILTER = True

SUPERTREND LOGIC:
- Upper Band = (High + Low) / 2 + ATR * Multiplier
- Lower Band = (High + Low) / 2 - ATR * Multiplier
- Long when price closes above Upper Band
- Short when price closes below Lower Band (we stay flat instead)

EXPECTED CHARACTERISTICS:
- Win rate: 35-45% (trend-following)
- High R:R (big wins, small losses due to ATR stops)
- Works well in trending markets
- Whipsaws in choppy markets
"""

from AlgorithmImports import *
from datetime import timedelta


class SuperTrendSectors(QCAlgorithm):
    """
    SuperTrend Strategy on Sector ETFs

    Rules:
    1. Calculate SuperTrend for each sector
    2. Long when price closes above SuperTrend (bullish)
    3. Exit when price closes below SuperTrend (bearish)
    4. Max 4 positions at a time
    5. Optional regime filter (SPY > 200 SMA)
    """

    # Configuration
    ATR_PERIOD = 10
    ATR_MULTIPLIER = 3.0
    MAX_POSITIONS = 4
    USE_REGIME_FILTER = True

    def initialize(self):
        # Backtest period
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Sector ETFs (original 9)
        sector_tickers = ["XLK", "XLF", "XLV", "XLE", "XLI", "XLP", "XLY", "XLB", "XLU"]

        self.sectors = []
        self.atr_indicators = {}
        self.supertrend_data = {}  # Store SuperTrend calculation data

        for ticker in sector_tickers:
            equity = self.add_equity(ticker, Resolution.DAILY)
            equity.set_slippage_model(ConstantSlippageModel(0.001))
            equity.set_fee_model(InteractiveBrokersFeeModel())
            self.sectors.append(equity.symbol)

            # ATR for each sector (ATR doesn't take resolution parameter)
            self.atr_indicators[equity.symbol] = self.atr(equity.symbol, self.ATR_PERIOD)

            # SuperTrend state tracking
            self.supertrend_data[equity.symbol] = {
                'upper_band': None,
                'lower_band': None,
                'supertrend': None,
                'trend_direction': 0,  # 1 = bullish, -1 = bearish
                'prev_supertrend': None,
            }

        # SPY for regime filter and benchmark
        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.set_benchmark(self.spy)
        self.spy_sma = self.sma(self.spy, 200, Resolution.DAILY)

        # Position tracking
        self.entry_prices = {}
        self.entry_dates = {}

        # Trade log
        self.completed_trades = []

        # Warmup
        self.set_warmup(timedelta(days=50))

        # Check signals daily
        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.before_market_close(self.spy, 5),
            self.check_signals
        )

    def check_signals(self):
        """Check SuperTrend signals for all sectors"""
        if self.is_warming_up:
            return

        # Check regime filter
        if self.USE_REGIME_FILTER and self.spy_sma.is_ready:
            if self.securities[self.spy].price < self.spy_sma.current.value:
                # Bear market - liquidate all
                for symbol in self.sectors:
                    if self.portfolio[symbol].invested:
                        self.exit_position(symbol, "Regime Filter")
                return

        # Update SuperTrend for each sector
        for symbol in self.sectors:
            if not self.atr_indicators[symbol].is_ready:
                continue

            self.update_supertrend(symbol)
            data = self.supertrend_data[symbol]

            if data['supertrend'] is None:
                continue

            price = self.securities[symbol].price

            # Check exit first
            if self.portfolio[symbol].invested:
                if data['trend_direction'] == -1:  # Turned bearish
                    self.exit_position(symbol, "SuperTrend Bearish")

            # Check entry
            elif data['trend_direction'] == 1:  # Bullish
                # Count current positions
                current_positions = sum(1 for s in self.sectors if self.portfolio[s].invested)
                if current_positions < self.MAX_POSITIONS:
                    self.enter_position(symbol)

    def update_supertrend(self, symbol):
        """Calculate SuperTrend for a symbol"""
        history = self.history(symbol, 2, Resolution.DAILY)
        if history.empty or len(history) < 2:
            return

        try:
            # Current bar data
            high = history['high'].iloc[-1]
            low = history['low'].iloc[-1]
            close = history['close'].iloc[-1]

            # Previous close
            prev_close = history['close'].iloc[-2]

            # ATR
            atr_value = self.atr_indicators[symbol].current.value

            # Basic bands
            hl2 = (high + low) / 2
            upper_band = hl2 + (self.ATR_MULTIPLIER * atr_value)
            lower_band = hl2 - (self.ATR_MULTIPLIER * atr_value)

            data = self.supertrend_data[symbol]

            # Final upper band (lower of current and previous if in uptrend)
            if data['upper_band'] is not None:
                if close > data['upper_band']:
                    final_upper = upper_band
                else:
                    final_upper = min(upper_band, data['upper_band'])
            else:
                final_upper = upper_band

            # Final lower band (higher of current and previous if in downtrend)
            if data['lower_band'] is not None:
                if close < data['lower_band']:
                    final_lower = lower_band
                else:
                    final_lower = max(lower_band, data['lower_band'])
            else:
                final_lower = lower_band

            # Determine trend direction
            prev_direction = data['trend_direction']

            if data['supertrend'] is None:
                # Initialize
                if close > final_upper:
                    direction = 1
                else:
                    direction = -1
            else:
                if prev_direction == 1:
                    # Was bullish
                    if close < final_lower:
                        direction = -1  # Flip to bearish
                    else:
                        direction = 1
                else:
                    # Was bearish
                    if close > final_upper:
                        direction = 1  # Flip to bullish
                    else:
                        direction = -1

            # SuperTrend value
            if direction == 1:
                supertrend = final_lower
            else:
                supertrend = final_upper

            # Update state
            data['prev_supertrend'] = data['supertrend']
            data['upper_band'] = final_upper
            data['lower_band'] = final_lower
            data['supertrend'] = supertrend
            data['trend_direction'] = direction

        except Exception as e:
            self.debug(f"SuperTrend error for {symbol}: {e}")

    def enter_position(self, symbol):
        """Enter long position"""
        price = self.securities[symbol].price
        weight = 0.95 / self.MAX_POSITIONS

        self.set_holdings(symbol, weight)
        self.entry_prices[symbol] = price
        self.entry_dates[symbol] = self.time

        st_value = self.supertrend_data[symbol]['supertrend']
        self.log(f"ENTRY: {symbol} @ ${price:.2f} | SuperTrend=${st_value:.2f}")

    def exit_position(self, symbol, reason: str):
        """Exit position"""
        if not self.portfolio[symbol].invested:
            return

        exit_price = self.securities[symbol].price
        entry_price = self.entry_prices.get(symbol, exit_price)
        entry_date = self.entry_dates.get(symbol, self.time)

        pnl_pct = (exit_price - entry_price) / entry_price
        days_held = (self.time - entry_date).days

        self.liquidate(symbol)

        self.completed_trades.append({
            'symbol': str(symbol),
            'entry_date': str(entry_date.date()),
            'exit_date': str(self.time.date()),
            'entry_price': entry_price,
            'exit_price': exit_price,
            'pnl_pct': pnl_pct,
            'days_held': days_held,
            'reason': reason,
        })

        self.log(f"EXIT: {symbol} | {reason} | P&L={pnl_pct*100:.1f}% | Days={days_held}")

        if symbol in self.entry_prices:
            del self.entry_prices[symbol]
        if symbol in self.entry_dates:
            del self.entry_dates[symbol]

    def on_end_of_algorithm(self):
        """Log summary"""
        self.log("=" * 60)
        self.log("SUPERTREND SECTORS - TRADE SUMMARY")
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

        # Trades by sector
        sector_trades = {}
        for t in self.completed_trades:
            s = t['symbol'].split()[0]
            sector_trades[s] = sector_trades.get(s, 0) + 1
        self.log("Trades by Sector: " + ", ".join(f"{k}:{v}" for k, v in sorted(sector_trades.items())))
        self.log("=" * 60)

    def on_data(self, data):
        pass
