# region imports
from AlgorithmImports import *
# endregion

class ConcentratedHighBetaR15(QCAlgorithm):
    """
    Round 15 Strategy 1: Concentrated High-Beta Momentum

    Target: 30-50% CAGR via concentration in highest-beta stocks

    Approach:
    - Only trade the 10 highest-beta stocks (TSLA, NVDA, AMD, etc.)
    - Max 4 positions (25% each) for concentration
    - Let winners run with trailing stop (no profit cap)
    - Aggressive entry: momentum + ADX

    Risk: Higher volatility, larger drawdowns expected
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # HIGH-BETA stocks only (beta > 1.3 historically)
        self.tickers = [
            "TSLA",   # ~2.0 beta
            "NVDA",   # ~1.8 beta
            "AMD",    # ~1.7 beta
            "META",   # ~1.4 beta
            "NFLX",   # ~1.5 beta
            "CRM",    # ~1.3 beta
            "AMZN",   # ~1.3 beta
            "AVGO",   # ~1.4 beta
            "GS",     # ~1.4 beta
            "CAT",    # ~1.3 beta
        ]

        self.symbols = {}
        self.momp_20d = {}
        self.momp_63d = {}
        self.adx_ind = {}

        for ticker in self.tickers:
            equity = self.add_equity(ticker, Resolution.DAILY)
            equity.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
            sym = equity.symbol
            self.symbols[ticker] = sym

            self.momp_20d[ticker] = self.momp(sym, 20, Resolution.DAILY)
            self.momp_63d[ticker] = self.momp(sym, 63, Resolution.DAILY)
            self.adx_ind[ticker] = self.adx(sym, 14, Resolution.DAILY)

        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)

        vix = self.add_data(CBOE, "VIX", Resolution.DAILY)
        self.vix = vix.symbol

        self.entry_dates = {}
        self.entry_prices = {}
        self.highest_prices = {}
        self.max_positions = 4  # Concentrated: 25% each
        self.trailing_pct = 0.08  # 8% trailing stop from high

        self.schedule.on(
            self.date_rules.every_day("SPY"),
            self.time_rules.after_market_open("SPY", 30),
            self.check_exits
        )

        self.schedule.on(
            self.date_rules.every([DayOfWeek.MONDAY]),
            self.time_rules.after_market_open("SPY", 31),
            self.rebalance
        )

        self.set_benchmark("SPY")
        self.set_warm_up(100, Resolution.DAILY)

    def get_vix_level(self):
        if self.vix in self.securities and self.securities[self.vix].price > 0:
            return self.securities[self.vix].price
        return 20

    def check_exits(self):
        if self.is_warming_up:
            return

        for ticker in list(self.entry_dates.keys()):
            symbol = self.symbols[ticker]
            if not self.portfolio[symbol].invested:
                self._cleanup(ticker)
                continue

            current_price = self.securities[symbol].price
            entry_price = self.entry_prices[ticker]
            pnl_pct = (current_price - entry_price) / entry_price

            # Update high
            if ticker not in self.highest_prices:
                self.highest_prices[ticker] = entry_price
            self.highest_prices[ticker] = max(self.highest_prices[ticker], current_price)

            should_exit = False
            reason = ""

            # Hard stop: -10% from entry
            if pnl_pct <= -0.10:
                should_exit = True
                reason = f"STOP({pnl_pct:.1%})"

            # Trailing stop: 8% from high (only after 5% gain)
            elif pnl_pct > 0.05:
                drawdown = (current_price - self.highest_prices[ticker]) / self.highest_prices[ticker]
                if drawdown < -self.trailing_pct:
                    should_exit = True
                    reason = f"TRAIL({pnl_pct:+.1%}, peak+{(self.highest_prices[ticker]/entry_price-1):.1%})"

            if should_exit:
                self.liquidate(symbol)
                self.debug(f"{self.time.date()}: EXIT {ticker} {reason}")
                self._cleanup(ticker)

    def _cleanup(self, ticker):
        if ticker in self.entry_dates:
            del self.entry_dates[ticker]
        if ticker in self.entry_prices:
            del self.entry_prices[ticker]
        if ticker in self.highest_prices:
            del self.highest_prices[ticker]

    def rebalance(self):
        if self.is_warming_up:
            return

        spy_price = self.securities[self.spy].price
        if not self.spy_sma_200.is_ready or spy_price < self.spy_sma_200.current.value:
            # Bear market: liquidate all
            self.liquidate()
            for t in list(self.entry_dates.keys()):
                self._cleanup(t)
            return

        vix_level = self.get_vix_level()
        if vix_level > 35:
            return  # No new entries in extreme vol

        scores = []
        for ticker in self.tickers:
            symbol = self.symbols[ticker]

            if ticker in self.entry_dates:
                continue

            if not all([
                self.momp_20d[ticker].is_ready,
                self.momp_63d[ticker].is_ready,
                self.adx_ind[ticker].is_ready
            ]):
                continue

            adx_val = self.adx_ind[ticker].current.value
            positive_di = self.adx_ind[ticker].positive_directional_index.current.value
            negative_di = self.adx_ind[ticker].negative_directional_index.current.value

            if adx_val < 25 or positive_di <= negative_di:  # Higher ADX threshold
                continue

            mom_short = self.momp_20d[ticker].current.value
            mom_long = self.momp_63d[ticker].current.value

            if mom_short <= 0 or mom_long <= 0:
                continue

            # Score combines momentum and trend strength
            score = (mom_short * 0.5 + mom_long * 0.5) * (adx_val / 100)
            scores.append({"ticker": ticker, "symbol": symbol, "score": score})

        scores.sort(key=lambda x: x["score"], reverse=True)

        current_count = len(self.entry_dates)
        slots = self.max_positions - current_count

        for s in scores[:slots]:
            ticker = s["ticker"]
            symbol = s["symbol"]
            price = self.securities[symbol].price

            weight = 1.0 / self.max_positions  # 25% each
            self.set_holdings(symbol, weight)
            self.entry_dates[ticker] = self.time
            self.entry_prices[ticker] = price
            self.highest_prices[ticker] = price
            self.debug(f"{self.time.date()}: ENTER {ticker} @ ${price:.2f}")
