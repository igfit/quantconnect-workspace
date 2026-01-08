"""
Base Swing Strategy for Strategy Factory

This is the foundation class for all swing trading strategies (days-weeks holding).
Provides common functionality:
- Standard initialization (dates, capital, slippage, commission)
- Regime filtering (SPY > 200 SMA for bull market detection)
- Position tracking and trade logging
- Risk management (stop loss, take profit, max holding)
- Next-day execution (no look-ahead bias)

Usage:
    class MyStrategy(BaseSwingStrategy):
        def initialize(self):
            super().initialize()
            # Add your indicators and symbols

        def check_entry_signal(self, symbol) -> bool:
            # Return True if entry conditions are met
            pass

        def check_exit_signal(self, symbol) -> bool:
            # Return True if exit conditions are met
            pass
"""

from AlgorithmImports import *
from datetime import timedelta
from typing import List, Dict, Optional
import json


class BaseSwingStrategy(QCAlgorithm):
    """
    Base class for swing trading strategies.

    Subclasses must implement:
        - get_symbols() -> List[str]: Return list of symbols to trade
        - setup_indicators(symbol): Initialize indicators for a symbol
        - check_entry_signal(symbol) -> bool: Entry logic
        - check_exit_signal(symbol) -> bool: Exit logic
    """

    # =========================================================================
    # CONFIGURATION - Override in subclass if needed
    # =========================================================================
    START_DATE = (2015, 1, 1)
    END_DATE = (2024, 12, 31)
    INITIAL_CAPITAL = 100000
    POSITION_SIZE_DOLLARS = 10000  # $ per position (10% of capital)
    MAX_POSITIONS = 10

    # Risk Management
    STOP_LOSS_PCT = None  # e.g., 0.08 for 8% stop loss
    TAKE_PROFIT_PCT = None  # e.g., 0.20 for 20% take profit
    MAX_HOLDING_DAYS = None  # e.g., 30 for max 30 days

    # Regime Filter
    USE_REGIME_FILTER = True  # Only trade when SPY > 200 SMA
    REGIME_SYMBOL = "SPY"
    REGIME_SMA_PERIOD = 200

    # Execution
    SLIPPAGE_PCT = 0.001  # 0.1% slippage
    MIN_PRICE = 5.0  # Minimum stock price
    MIN_DOLLAR_VOLUME = 1000000  # Minimum daily dollar volume

    def initialize(self):
        """
        Standard initialization. Call super().initialize() in subclass.
        """
        # Backtest period
        self.set_start_date(*self.START_DATE)
        self.set_end_date(*self.END_DATE)
        self.set_cash(self.INITIAL_CAPITAL)

        # Execution model
        self.set_security_initializer(self._initialize_security)

        # Symbol tracking
        self.symbols = []
        self._setup_universe()

        # Set benchmark
        if self.symbols:
            self.set_benchmark(self.symbols[0])

        # Regime filter
        if self.USE_REGIME_FILTER:
            self._setup_regime_filter()

        # Indicators dict: {symbol: {name: indicator}}
        self.indicators = {}

        # Setup indicators for each symbol
        for symbol in self.symbols:
            self._init_symbol_indicators(symbol)

        # Position tracking
        self.entry_prices = {}
        self.entry_dates = {}
        self.pending_entries = set()
        self.pending_exits = set()

        # Trade logging
        self.trade_log = []
        self.completed_trades = []

        # Warmup period
        warmup_days = self._calculate_warmup()
        self.set_warmup(timedelta(days=warmup_days))

        # Schedule trading events
        self._schedule_events()

    def _initialize_security(self, security):
        """Set slippage and commission models"""
        security.set_slippage_model(ConstantSlippageModel(self.SLIPPAGE_PCT))
        security.set_fee_model(InteractiveBrokersFeeModel())

    def _setup_universe(self):
        """Add symbols to trade. Override get_symbols() in subclass."""
        symbol_list = self.get_symbols()
        for ticker in symbol_list:
            equity = self.add_equity(ticker, Resolution.DAILY)
            self.symbols.append(equity.symbol)

    def _setup_regime_filter(self):
        """Setup SPY 200 SMA for regime detection"""
        if self.REGIME_SYMBOL not in [str(s) for s in self.symbols]:
            spy = self.add_equity(self.REGIME_SYMBOL, Resolution.DAILY)
            self.regime_symbol = spy.symbol
        else:
            self.regime_symbol = [s for s in self.symbols if str(s) == self.REGIME_SYMBOL][0]

        self.regime_sma = self.sma(self.regime_symbol, self.REGIME_SMA_PERIOD, Resolution.DAILY)

    def _init_symbol_indicators(self, symbol):
        """Initialize indicators for a symbol. Calls setup_indicators()."""
        if symbol not in self.indicators:
            self.indicators[symbol] = {}
        self.setup_indicators(symbol)

    def _calculate_warmup(self) -> int:
        """Calculate warmup period based on longest indicator"""
        max_period = self.REGIME_SMA_PERIOD if self.USE_REGIME_FILTER else 50
        # Subclass should override get_max_indicator_period()
        indicator_period = self.get_max_indicator_period()
        return max(max_period, indicator_period) + 10  # Buffer

    def _schedule_events(self):
        """Schedule signal generation and order execution"""
        ref_symbol = self.symbols[0] if self.symbols else "SPY"

        # Execute pending orders at market open
        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.after_market_open(ref_symbol, 1),
            self._execute_pending_orders
        )

        # Generate signals before close
        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.before_market_close(ref_symbol, 5),
            self._generate_signals
        )

    # =========================================================================
    # REGIME FILTER
    # =========================================================================

    def is_bull_regime(self) -> bool:
        """
        Returns True if in bull market regime (SPY > 200 SMA).
        Override for custom regime logic.
        """
        if not self.USE_REGIME_FILTER:
            return True

        if not self.regime_sma.is_ready:
            return False

        return self.securities[self.regime_symbol].price > self.regime_sma.current.value

    # =========================================================================
    # SIGNAL GENERATION
    # =========================================================================

    def _generate_signals(self):
        """Generate entry/exit signals at market close"""
        if self.is_warming_up:
            return

        for symbol in self.symbols:
            # Skip if data not ready
            if not self._has_valid_data(symbol):
                continue

            # Check existing position
            if self.portfolio[symbol].invested:
                # Check stop loss / take profit / max holding
                if self._check_risk_management(symbol):
                    self.pending_exits.add(symbol)
                    continue

                # Check exit signal
                if self.check_exit_signal(symbol):
                    self.pending_exits.add(symbol)
            else:
                # Check entry signal (only in bull regime)
                if self.is_bull_regime() and self._can_open_position():
                    if self.check_entry_signal(symbol):
                        self.pending_entries.add(symbol)

    def _execute_pending_orders(self):
        """Execute pending orders at market open"""
        if self.is_warming_up:
            return

        # Execute exits first
        for symbol in list(self.pending_exits):
            if self.portfolio[symbol].invested:
                self._close_position(symbol, "Exit Signal")
            self.pending_exits.discard(symbol)

        # Execute entries
        for symbol in list(self.pending_entries):
            if not self.portfolio[symbol].invested:
                if self._passes_filters(symbol):
                    self._open_position(symbol)
            self.pending_entries.discard(symbol)

    # =========================================================================
    # POSITION MANAGEMENT
    # =========================================================================

    def _can_open_position(self) -> bool:
        """Check if we can open a new position"""
        current_positions = sum(1 for s in self.symbols if self.portfolio[s].invested)
        return current_positions < self.MAX_POSITIONS

    def _open_position(self, symbol):
        """Open a new position"""
        price = self.securities[symbol].price
        if price <= 0:
            return

        shares = int(self.POSITION_SIZE_DOLLARS / price)
        if shares <= 0:
            return

        self.market_order(symbol, shares)
        self.entry_prices[symbol] = price
        self.entry_dates[symbol] = self.time

        self.log(f"ENTRY: {symbol} | {shares} shares @ ${price:.2f}")

        # Log trade
        self.trade_log.append({
            "symbol": str(symbol),
            "action": "ENTRY",
            "date": str(self.time.date()),
            "price": price,
            "shares": shares,
        })

    def _close_position(self, symbol, reason: str = ""):
        """Close an existing position"""
        if not self.portfolio[symbol].invested:
            return

        entry_price = self.entry_prices.get(symbol, 0)
        entry_date = self.entry_dates.get(symbol)
        exit_price = self.securities[symbol].price
        shares = self.portfolio[symbol].quantity

        # Calculate P&L
        pnl_dollars = (exit_price - entry_price) * shares
        pnl_pct = (exit_price - entry_price) / entry_price if entry_price > 0 else 0
        bars_held = (self.time - entry_date).days if entry_date else 0

        self.liquidate(symbol, reason)
        self.log(f"EXIT: {symbol} | {reason} | P&L: ${pnl_dollars:.2f} ({pnl_pct*100:.1f}%)")

        # Log completed trade
        self.completed_trades.append({
            "symbol": str(symbol),
            "entry_date": str(entry_date.date()) if entry_date else "",
            "exit_date": str(self.time.date()),
            "entry_price": entry_price,
            "exit_price": exit_price,
            "shares": shares,
            "pnl_dollars": pnl_dollars,
            "pnl_pct": pnl_pct,
            "bars_held": bars_held,
            "reason": reason,
        })

        # Cleanup
        if symbol in self.entry_prices:
            del self.entry_prices[symbol]
        if symbol in self.entry_dates:
            del self.entry_dates[symbol]

    # =========================================================================
    # RISK MANAGEMENT
    # =========================================================================

    def _check_risk_management(self, symbol) -> bool:
        """Check stop loss, take profit, max holding"""
        if self._check_stop_loss(symbol):
            return True
        if self._check_take_profit(symbol):
            return True
        if self._check_max_holding(symbol):
            return True
        return False

    def _check_stop_loss(self, symbol) -> bool:
        """Check if stop loss is triggered"""
        if self.STOP_LOSS_PCT is None:
            return False

        entry_price = self.entry_prices.get(symbol)
        if not entry_price:
            return False

        current_price = self.securities[symbol].price
        loss_pct = (entry_price - current_price) / entry_price

        if loss_pct >= self.STOP_LOSS_PCT:
            self.log(f"STOP LOSS: {symbol} | Loss: {loss_pct*100:.1f}%")
            return True
        return False

    def _check_take_profit(self, symbol) -> bool:
        """Check if take profit is triggered"""
        if self.TAKE_PROFIT_PCT is None:
            return False

        entry_price = self.entry_prices.get(symbol)
        if not entry_price:
            return False

        current_price = self.securities[symbol].price
        gain_pct = (current_price - entry_price) / entry_price

        if gain_pct >= self.TAKE_PROFIT_PCT:
            self.log(f"TAKE PROFIT: {symbol} | Gain: {gain_pct*100:.1f}%")
            return True
        return False

    def _check_max_holding(self, symbol) -> bool:
        """Check if max holding period exceeded"""
        if self.MAX_HOLDING_DAYS is None:
            return False

        entry_date = self.entry_dates.get(symbol)
        if not entry_date:
            return False

        days_held = (self.time - entry_date).days
        if days_held >= self.MAX_HOLDING_DAYS:
            self.log(f"MAX HOLDING: {symbol} | Days: {days_held}")
            return True
        return False

    # =========================================================================
    # FILTERS
    # =========================================================================

    def _passes_filters(self, symbol) -> bool:
        """Check liquidity and price filters"""
        security = self.securities[symbol]

        # Price filter
        if security.price < self.MIN_PRICE:
            return False

        # Volume filter
        history = self.history(symbol, 5, Resolution.DAILY)
        if history.empty:
            return False

        avg_dollar_volume = (history['volume'] * history['close']).mean()
        if avg_dollar_volume < self.MIN_DOLLAR_VOLUME:
            return False

        return True

    def _has_valid_data(self, symbol) -> bool:
        """Check if symbol has valid data and indicators ready"""
        if symbol not in self.securities:
            return False

        if self.securities[symbol].price <= 0:
            return False

        # Check all indicators are ready
        for ind_name, ind in self.indicators.get(symbol, {}).items():
            if hasattr(ind, 'is_ready') and not ind.is_ready:
                return False

        return True

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def get_indicator(self, symbol, name):
        """Get indicator value by name"""
        indicators = self.indicators.get(symbol, {})
        if name in indicators:
            ind = indicators[name]
            if hasattr(ind, 'current'):
                return float(ind.current.value)
        return None

    def on_end_of_algorithm(self):
        """Called at end of backtest - log summary statistics"""
        self._log_trade_summary()

    def _log_trade_summary(self):
        """Log summary of all trades"""
        if not self.completed_trades:
            self.log("No completed trades to summarize")
            return

        total_trades = len(self.completed_trades)
        winners = [t for t in self.completed_trades if t['pnl_dollars'] > 0]
        losers = [t for t in self.completed_trades if t['pnl_dollars'] <= 0]

        win_rate = len(winners) / total_trades if total_trades > 0 else 0
        avg_win = sum(t['pnl_pct'] for t in winners) / len(winners) if winners else 0
        avg_loss = sum(t['pnl_pct'] for t in losers) / len(losers) if losers else 0
        avg_bars = sum(t['bars_held'] for t in self.completed_trades) / total_trades if total_trades > 0 else 0

        self.log("=" * 50)
        self.log("TRADE SUMMARY")
        self.log("=" * 50)
        self.log(f"Total Trades: {total_trades}")
        self.log(f"Winners: {len(winners)} | Losers: {len(losers)}")
        self.log(f"Win Rate: {win_rate*100:.1f}%")
        self.log(f"Avg Win: {avg_win*100:.1f}% | Avg Loss: {avg_loss*100:.1f}%")
        self.log(f"Risk/Reward: {abs(avg_win/avg_loss):.2f}" if avg_loss != 0 else "R/R: N/A")
        self.log(f"Avg Holding Days: {avg_bars:.1f}")
        self.log("=" * 50)

    # =========================================================================
    # METHODS TO OVERRIDE IN SUBCLASS
    # =========================================================================

    def get_symbols(self) -> List[str]:
        """
        Return list of symbols to trade.
        MUST override in subclass.
        """
        raise NotImplementedError("Subclass must implement get_symbols()")

    def setup_indicators(self, symbol):
        """
        Initialize indicators for a symbol.
        Add to self.indicators[symbol] dict.
        MUST override in subclass.
        """
        raise NotImplementedError("Subclass must implement setup_indicators()")

    def get_max_indicator_period(self) -> int:
        """
        Return the longest indicator period for warmup calculation.
        Override if using indicators > 50 period.
        """
        return 50

    def check_entry_signal(self, symbol) -> bool:
        """
        Return True if entry conditions are met for symbol.
        MUST override in subclass.
        """
        raise NotImplementedError("Subclass must implement check_entry_signal()")

    def check_exit_signal(self, symbol) -> bool:
        """
        Return True if exit conditions are met for symbol.
        MUST override in subclass.
        """
        raise NotImplementedError("Subclass must implement check_exit_signal()")

    def on_data(self, data):
        """
        Required method - but we use scheduled events for trading.
        Override only if you need tick-level processing.
        """
        pass
