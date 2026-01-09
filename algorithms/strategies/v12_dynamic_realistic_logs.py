"""
v12 Dynamic Universe - REALISTIC VERSION WITH DETAILED LOGS

Logs every trade decision to understand differences from original.
"""

from AlgorithmImports import *


class V12DynamicRealisticLogs(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2026, 1, 1)
        self.set_cash(100000)

        # MORE REALISTIC: Higher slippage (0.2%)
        self.set_security_initializer(lambda security: security.set_slippage_model(
            ConstantSlippageModel(0.002)
        ))
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        # Strategy parameters
        self.lookback_days = 126
        self.accel_period = 21
        self.top_n = 8
        # MORE REALISTIC: Higher min dollar volume for liquidity
        self.min_dollar_volume = 10_000_000

        # Universe selection parameters
        self.universe_size = 50
        self.min_market_cap = 2e9
        self.max_market_cap = 500e9
        # MORE REALISTIC: Higher min price
        self.min_price = 15
        # MORE REALISTIC: Higher volume requirement
        self.min_avg_dollar_volume = 30e6

        self.last_universe_refresh = None

        self.prev_short_mom = {}
        self.rebalance_week = 0
        self.active_symbols = []
        self.momentum = {}
        self.short_mom = {}
        self.volume_sma = {}

        # Pending trades for next-day execution
        self.pending_trades = {}

        # Track yearly performance
        self.year_start_equity = 100000
        self.current_year = 2015

        # Regime filters
        self.qqq = self.add_equity("QQQ", Resolution.DAILY).symbol
        self.qqq_sma_10 = self.sma(self.qqq, 10, Resolution.DAILY)
        self.qqq_sma_20 = self.sma(self.qqq, 20, Resolution.DAILY)
        self.qqq_sma_50 = self.sma(self.qqq, 50, Resolution.DAILY)
        self.qqq_mom = self.roc(self.qqq, 63, Resolution.DAILY)

        self.add_universe(self.coarse_filter, self.fine_filter)
        self.set_warm_up(self.lookback_days + 10, Resolution.DAILY)

        # Generate signals end of day Monday
        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.before_market_close("QQQ", 5),
            self.generate_signals
        )

        # Execute trades NEXT DAY at open
        self.schedule.on(
            self.date_rules.every(DayOfWeek.TUESDAY),
            self.time_rules.after_market_open("QQQ", 1),
            self.execute_pending_trades
        )

        # Log yearly returns
        self.schedule.on(
            self.date_rules.month_start(),
            self.time_rules.after_market_open("QQQ", 5),
            self.check_year_change
        )

        self.set_benchmark("SPY")

    def check_year_change(self):
        if self.time.year != self.current_year:
            equity = self.portfolio.total_portfolio_value
            year_return = (equity / self.year_start_equity - 1) * 100
            self.log(f"YEAR {self.current_year}: Return = {year_return:.2f}%, Equity = ${equity:,.0f}")
            self.year_start_equity = equity
            self.current_year = self.time.year

    def should_refresh(self):
        if self.last_universe_refresh is None:
            return True
        return (self.time - self.last_universe_refresh).days >= 365

    def coarse_filter(self, coarse):
        if not self.should_refresh():
            return Universe.UNCHANGED

        filtered = [x for x in coarse
                   if x.has_fundamental_data
                   and x.price > self.min_price
                   and x.dollar_volume > self.min_avg_dollar_volume]

        sorted_by_volume = sorted(filtered, key=lambda x: x.dollar_volume, reverse=True)
        return [x.symbol for x in sorted_by_volume[:500]]

    def fine_filter(self, fine):
        if not self.should_refresh():
            return Universe.UNCHANGED

        filtered = [x for x in fine
                   if x.market_cap > self.min_market_cap
                   and x.market_cap < self.max_market_cap]

        growth_sectors = [
            MorningstarSectorCode.TECHNOLOGY,
            MorningstarSectorCode.CONSUMER_CYCLICAL,
            MorningstarSectorCode.HEALTHCARE,
            MorningstarSectorCode.COMMUNICATION_SERVICES
        ]

        sector_filtered = [x for x in filtered
                         if x.asset_classification.morningstar_sector_code in growth_sectors]

        sorted_stocks = sorted(sector_filtered, key=lambda x: x.dollar_volume, reverse=True)
        selected = [x.symbol for x in sorted_stocks[:self.universe_size]]

        self.last_universe_refresh = self.time
        self.log(f"Universe refreshed: {len(selected)} stocks at {self.time.date()}")

        return selected

    def on_securities_changed(self, changes):
        for security in changes.added_securities:
            symbol = security.symbol
            if symbol == self.qqq:
                continue
            if symbol not in self.active_symbols:
                self.active_symbols.append(symbol)
            if symbol not in self.momentum:
                self.momentum[symbol] = self.roc(symbol, self.lookback_days, Resolution.DAILY)
                self.short_mom[symbol] = self.roc(symbol, self.accel_period, Resolution.DAILY)
                self.volume_sma[symbol] = self.sma(symbol, 20, Resolution.DAILY, Field.VOLUME)

        for security in changes.removed_securities:
            symbol = security.symbol
            if symbol in self.active_symbols:
                self.active_symbols.remove(symbol)
            if self.portfolio[symbol].invested:
                self.liquidate(symbol)

    def generate_signals(self):
        """Generate trading signals at end of day, execute next day"""
        self.rebalance_week += 1
        if self.rebalance_week % 2 != 0:
            return

        if self.is_warming_up:
            return
        if len(self.active_symbols) == 0:
            return

        qqq_price = self.securities[self.qqq].price
        if not self.qqq_sma_10.is_ready or not self.qqq_sma_20.is_ready or not self.qqq_sma_50.is_ready:
            return

        above_10 = qqq_price > self.qqq_sma_10.current.value
        above_20 = qqq_price > self.qqq_sma_20.current.value
        above_50 = qqq_price > self.qqq_sma_50.current.value
        qqq_mom_positive = self.qqq_mom.is_ready and self.qqq_mom.current.value > 0

        # Log regime state
        regime = "BULL" if above_10 and above_20 and above_50 else ("CAUTION" if above_10 else "BEAR")
        self.log(f"SIGNAL {self.time.date()}: QQQ={qqq_price:.2f} SMA10={self.qqq_sma_10.current.value:.2f} SMA20={self.qqq_sma_20.current.value:.2f} SMA50={self.qqq_sma_50.current.value:.2f} Regime={regime}")

        # Clear pending trades
        self.pending_trades = {}

        if not above_10:
            # Signal to liquidate everything
            self.pending_trades = {"LIQUIDATE_ALL": True}
            self.log(f"SIGNAL {self.time.date()}: LIQUIDATE ALL - QQQ below SMA10")
            return

        # Check for stocks to exit due to momentum crash
        exit_symbols = []
        for holding in list(self.portfolio.values()):
            if holding.invested and holding.symbol in self.active_symbols:
                if holding.symbol in self.short_mom and self.short_mom[holding.symbol].is_ready:
                    if self.short_mom[holding.symbol].current.value < -15:
                        exit_symbols.append(holding.symbol)
                        self.log(f"SIGNAL {self.time.date()}: EXIT {holding.symbol.value} - momentum crash ({self.short_mom[holding.symbol].current.value:.1f}%)")

        if above_10 and above_20 and above_50 and qqq_mom_positive:
            leverage = 1.0
        elif above_10 and above_20:
            leverage = 1.0
        else:
            leverage = 0.8

        scores = {}
        for symbol in self.active_symbols:
            if symbol not in self.momentum or not self.momentum[symbol].is_ready:
                continue
            if symbol not in self.short_mom or not self.short_mom[symbol].is_ready:
                continue
            if not self.securities[symbol].has_data:
                continue

            price = self.securities[symbol].price
            if price < 5:
                continue
            if symbol in self.volume_sma and self.volume_sma[symbol].is_ready:
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
            self.log(f"SIGNAL {self.time.date()}: NO TRADES - only {len(scores)} candidates")
            return

        actual_n = min(self.top_n, len(scores))
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_symbols = [s for s, _ in ranked[:actual_n]]

        total_score = sum(scores[s] for s in top_symbols)
        weights = {s: (scores[s] / total_score) * leverage for s in top_symbols}

        # Log selected stocks
        self.log(f"SIGNAL {self.time.date()}: TOP {actual_n} stocks (leverage={leverage}):")
        for s in top_symbols:
            self.log(f"  - {s.value}: mom={self.momentum[s].current.value:.1f}%, weight={weights[s]*100:.1f}%")

        # Store pending trades for next-day execution
        self.pending_trades = {
            "exit_symbols": exit_symbols,
            "target_weights": weights,
            "top_symbols": top_symbols
        }

    def execute_pending_trades(self):
        """Execute trades at market open (next day after signal)"""
        if not self.pending_trades:
            return

        self.log(f"EXECUTE {self.time.date()}: Processing pending trades")

        if self.pending_trades.get("LIQUIDATE_ALL"):
            self.log(f"EXECUTE {self.time.date()}: Liquidating all positions")
            self.liquidate()
            self.pending_trades = {}
            return

        exit_symbols = self.pending_trades.get("exit_symbols", [])
        target_weights = self.pending_trades.get("target_weights", {})
        top_symbols = self.pending_trades.get("top_symbols", [])

        # Exit momentum crash stocks
        for symbol in exit_symbols:
            if self.portfolio[symbol].invested:
                self.log(f"EXECUTE {self.time.date()}: Selling {symbol.value} (momentum crash)")
                self.liquidate(symbol)

        # Exit positions not in top symbols
        for holding in self.portfolio.values():
            if holding.invested and holding.symbol not in top_symbols:
                self.log(f"EXECUTE {self.time.date()}: Selling {holding.symbol.value} (not in top)")
                self.liquidate(holding.symbol)

        # Enter/adjust positions
        for symbol in top_symbols:
            if symbol in target_weights:
                current_weight = self.portfolio[symbol].holdings_value / self.portfolio.total_portfolio_value if self.portfolio.total_portfolio_value > 0 else 0
                target_weight = target_weights[symbol]
                if abs(current_weight - target_weight) > 0.02:  # Only log significant changes
                    self.log(f"EXECUTE {self.time.date()}: {symbol.value} {current_weight*100:.1f}% -> {target_weight*100:.1f}%")
                self.set_holdings(symbol, target_weights[symbol])

        self.pending_trades = {}

    def on_end_of_algorithm(self):
        # Log final year
        equity = self.portfolio.total_portfolio_value
        year_return = (equity / self.year_start_equity - 1) * 100
        self.log(f"YEAR {self.current_year}: Return = {year_return:.2f}%, Equity = ${equity:,.0f}")
        self.log(f"TOTAL: ${100000:,} -> ${equity:,.0f} = {(equity/100000-1)*100:.1f}%")
