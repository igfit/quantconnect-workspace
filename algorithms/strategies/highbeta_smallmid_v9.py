"""
High-Beta Small/Mid Cap v9 - ULTRA-TIGHT REGIME

Target: 30% CAGR with 20-30% DD

Key changes:
- No leverage (1.0x only)
- Ultra-tight regime: Exit if QQQ < 10 SMA (very fast)
- Only enter if QQQ > 20 AND 50 SMA
- Equal weight (less concentration risk)
"""

from AlgorithmImports import *


class HighBetaSmallMidV9(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.set_security_initializer(lambda security: security.set_slippage_model(
            ConstantSlippageModel(0.001)
        ))
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        # Parameters - ULTRA-TIGHT REGIME
        self.lookback_days = 126
        self.accel_period = 21
        self.top_n = 10
        self.min_dollar_volume = 5_000_000

        self.prev_short_mom = {}

        # Universe - 32 high-beta stocks
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

        # Ultra-tight regime filters
        self.qqq = self.add_equity("QQQ", Resolution.DAILY).symbol
        self.qqq_sma_10 = self.sma(self.qqq, 10, Resolution.DAILY)  # ULTRA FAST exit
        self.qqq_sma_20 = self.sma(self.qqq, 20, Resolution.DAILY)
        self.qqq_sma_50 = self.sma(self.qqq, 50, Resolution.DAILY)

        self.symbols = []
        for ticker in self.universe_tickers:
            try:
                equity = self.add_equity(ticker, Resolution.DAILY)
                self.symbols.append(equity.symbol)
            except:
                pass

        self.log(f"Universe size: {len(self.symbols)} stocks")

        self.momentum = {}
        self.short_mom = {}
        self.volume_sma = {}
        for symbol in self.symbols:
            self.momentum[symbol] = self.roc(symbol, self.lookback_days, Resolution.DAILY)
            self.short_mom[symbol] = self.roc(symbol, self.accel_period, Resolution.DAILY)
            self.volume_sma[symbol] = self.sma(symbol, 20, Resolution.DAILY, Field.VOLUME)

        self.set_warm_up(self.lookback_days + 10, Resolution.DAILY)

        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.after_market_open("QQQ", 30),
            self.rebalance
        )
        self.set_benchmark("QQQ")

    def rebalance(self):
        if self.is_warming_up:
            return

        qqq_price = self.securities[self.qqq].price

        if not self.qqq_sma_10.is_ready or not self.qqq_sma_20.is_ready or not self.qqq_sma_50.is_ready:
            return

        above_10 = qqq_price > self.qqq_sma_10.current.value
        above_20 = qqq_price > self.qqq_sma_20.current.value
        above_50 = qqq_price > self.qqq_sma_50.current.value

        # ULTRA-FAST EXIT: if below 10 SMA, exit immediately
        if not above_10:
            self.liquidate()
            return

        # Only enter new positions if above both 20 and 50 SMA
        can_enter = above_20 and above_50

        scores = {}

        for symbol in self.symbols:
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
            prev_mom = self.prev_short_mom.get(symbol, 0)
            acceleration = short_mom - prev_mom
            self.prev_short_mom[symbol] = short_mom

            if mom > 0:
                accel_bonus = 1.3 if acceleration > 0 else 1.0
                scores[symbol] = mom * accel_bonus

        if len(scores) < 3:
            if not can_enter:
                self.liquidate()
            return

        # If can't enter, only keep existing positions that still have positive momentum
        if not can_enter:
            current_holdings = [h.symbol for h in self.portfolio.values() if h.invested]
            for holding in list(self.portfolio.values()):
                if holding.invested and holding.symbol not in scores:
                    self.liquidate(holding.symbol)
            return

        actual_n = min(self.top_n, len(scores))
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_symbols = [s for s, _ in ranked[:actual_n]]

        # EQUAL WEIGHT (less concentration risk)
        weight = 1.0 / len(top_symbols)

        for holding in self.portfolio.values():
            if holding.invested and holding.symbol not in top_symbols:
                self.liquidate(holding.symbol)

        for symbol in top_symbols:
            self.set_holdings(symbol, weight)
