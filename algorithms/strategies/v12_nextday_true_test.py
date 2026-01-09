"""
v12 Next-Day TRUE Test

TRUE isolation of execution timing:
- Generate signals Monday close using Monday's data
- Store the EXACT target weights
- Execute those SAME weights Tuesday open

This ensures we compare the SAME signals, just executed at different prices.
The warmup/counter logic matches the same-day version exactly.
"""

from AlgorithmImports import *


class V12NextDayTrueTest(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Same slippage as original
        self.set_security_initializer(lambda security: security.set_slippage_model(
            ConstantSlippageModel(0.001)
        ))
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        self.lookback_days = 126
        self.accel_period = 21
        self.top_n = 8
        self.max_leverage = 1.0
        self.min_dollar_volume = 5_000_000

        self.prev_short_mom = {}
        self.rebalance_week = 0

        # Queued orders for Tuesday execution
        self.tuesday_orders = None  # Will store (liquidate_all, exit_symbols, target_weights)

        # Original universe
        self.universe_tickers = [
            "TSLA", "NVDA", "AMD",
            "MU", "MRVL", "ON", "SWKS", "AMAT", "LRCX", "KLAC",
            "CRWD", "ZS", "OKTA", "TWLO", "NET", "MDB",
            "SQ", "PYPL",
            "SHOP", "ETSY", "ROKU", "SNAP", "PINS", "TTD",
            "ENPH", "SEDG", "FSLR",
            "UBER", "EXPE",
            "MRNA", "VRTX", "REGN",
        ]

        self.qqq = self.add_equity("QQQ", Resolution.DAILY).symbol
        self.qqq_sma_10 = self.sma(self.qqq, 10, Resolution.DAILY)
        self.qqq_sma_20 = self.sma(self.qqq, 20, Resolution.DAILY)
        self.qqq_sma_50 = self.sma(self.qqq, 50, Resolution.DAILY)
        self.qqq_mom = self.roc(self.qqq, 63, Resolution.DAILY)

        self.symbols = []
        for ticker in self.universe_tickers:
            try:
                equity = self.add_equity(ticker, Resolution.DAILY)
                self.symbols.append(equity.symbol)
            except:
                pass

        self.momentum = {}
        self.short_mom = {}
        self.volume_sma = {}
        for symbol in self.symbols:
            self.momentum[symbol] = self.roc(symbol, self.lookback_days, Resolution.DAILY)
            self.short_mom[symbol] = self.roc(symbol, self.accel_period, Resolution.DAILY)
            self.volume_sma[symbol] = self.sma(symbol, 20, Resolution.DAILY, Field.VOLUME)

        self.set_warm_up(self.lookback_days + 10, Resolution.DAILY)

        # Monday: Generate signals (SAME logic as same-day version)
        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.before_market_close("QQQ", 30),
            self.maybe_rebalance_monday
        )

        # Tuesday: Execute queued orders
        self.schedule.on(
            self.date_rules.every(DayOfWeek.TUESDAY),
            self.time_rules.after_market_open("QQQ", 1),
            self.execute_tuesday
        )

        self.set_benchmark("QQQ")

    def maybe_rebalance_monday(self):
        """SAME biweekly logic as same-day version - counter increments during warmup too."""
        self.rebalance_week += 1
        if self.rebalance_week % 2 == 0:
            self.generate_signals_monday()

    def generate_signals_monday(self):
        """Generate signals Monday close, queue for Tuesday execution."""
        if self.is_warming_up:
            return

        self.tuesday_orders = None  # Reset

        qqq_price = self.securities[self.qqq].price

        if not self.qqq_sma_10.is_ready or not self.qqq_sma_20.is_ready or not self.qqq_sma_50.is_ready:
            return

        above_10 = qqq_price > self.qqq_sma_10.current.value
        above_20 = qqq_price > self.qqq_sma_20.current.value
        above_50 = qqq_price > self.qqq_sma_50.current.value
        qqq_mom_positive = self.qqq_mom.is_ready and self.qqq_mom.current.value > 0

        # Regime filter: liquidate if below 10 SMA
        if not above_10:
            self.tuesday_orders = (True, set(), {})  # (liquidate_all, exit_symbols, weights)
            return

        # Find weak positions to exit
        exit_symbols = set()
        for holding in list(self.portfolio.values()):
            if holding.invested and holding.symbol in self.symbols:
                if self.short_mom[holding.symbol].is_ready:
                    if self.short_mom[holding.symbol].current.value < -15:
                        exit_symbols.add(holding.symbol)

        # Calculate leverage based on regime
        if above_10 and above_20 and above_50 and qqq_mom_positive:
            leverage = 1.0
        elif above_10 and above_20:
            leverage = 1.0
        else:
            leverage = 0.8

        # Calculate momentum scores
        scores = {}
        for symbol in self.symbols:
            if symbol in exit_symbols:
                continue
            if not self.momentum[symbol].is_ready:
                continue
            if not self.short_mom[symbol].is_ready:
                continue
            if not self.securities[symbol].has_data:
                continue

            price = self.securities[symbol].price
            if price < 5:
                continue
            if self.volume_sma[symbol].is_ready:
                if self.volume_sma[symbol].current.value * price < self.min_dollar_volume:
                    continue

            mom = self.momentum[symbol].current.value
            short_mom = self.short_mom[symbol].current.value

            if short_mom < -10:
                continue

            prev_mom = self.prev_short_mom.get(symbol, 0)
            acceleration = short_mom - prev_mom
            self.prev_short_mom[symbol] = short_mom

            if mom > 0:
                accel_bonus = 1.4 if acceleration > 0 else 1.0
                scores[symbol] = mom * accel_bonus

        if len(scores) < 3:
            return

        # Select top N and calculate weights
        actual_n = min(self.top_n, len(scores))
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_symbols = [s for s, _ in ranked[:actual_n]]

        total_score = sum(scores[s] for s in top_symbols)
        weights = {s: (scores[s] / total_score) * leverage for s in top_symbols}

        # Queue for Tuesday
        self.tuesday_orders = (False, exit_symbols, weights)

    def execute_tuesday(self):
        """Execute the signals generated Monday - ONLY if we have queued orders."""
        if self.is_warming_up:
            return

        if self.tuesday_orders is None:
            return  # No signal was generated Monday

        liquidate_all, exit_symbols, weights = self.tuesday_orders
        self.tuesday_orders = None  # Clear after execution

        if liquidate_all:
            self.liquidate()
            return

        # Exit weak positions
        for symbol in exit_symbols:
            self.liquidate(symbol)

        if not weights:
            return

        # Exit positions not in new targets
        for holding in self.portfolio.values():
            if holding.invested and holding.symbol not in weights:
                self.liquidate(holding.symbol)

        # Enter new positions at Tuesday's prices
        for symbol, weight in weights.items():
            self.set_holdings(symbol, weight)
