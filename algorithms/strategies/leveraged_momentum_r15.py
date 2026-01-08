# region imports
from AlgorithmImports import *
# endregion

class LeveragedMomentumR15(QCAlgorithm):
    """
    Round 15 Strategy 2: 1.5x Leveraged Momentum

    Target: 30-50% CAGR via leverage on proven momentum strategy

    Approach:
    - Same momentum strategy as RobustMomentum
    - 1.5x leverage (150% exposure)
    - Tighter stops to manage leveraged risk
    - VIX-based deleveraging in high vol

    Risk: ~1.5x returns AND drawdowns
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.leverage = 1.5  # 150% exposure
        self.profit_target = 0.05  # Tighter 5% target with leverage
        self.stop_loss = -0.035    # Tighter 3.5% stop with leverage
        self.max_hold_days = 12

        self.entry_dates = {}
        self.entry_prices = {}
        self.highest_prices = {}

        self.tickers = {
            "AAPL": "Tech", "MSFT": "Tech", "NVDA": "Tech", "GOOGL": "Tech",
            "META": "Tech", "AVGO": "Tech", "CRM": "Tech", "AMD": "Tech",
            "AMZN": "ConsDisc", "TSLA": "ConsDisc", "HD": "ConsDisc", "NKE": "ConsDisc",
            "UNH": "Health", "LLY": "Health", "ABBV": "Health", "JNJ": "Health",
            "JPM": "Finance", "GS": "Finance", "BLK": "Finance", "V": "Finance",
            "CAT": "Industrial", "HON": "Industrial", "GE": "Industrial", "UPS": "Industrial",
            "NFLX": "Comm", "DIS": "Comm",
            "COST": "Staples", "PG": "Staples",
        }

        self.symbols = {}
        self.momp_20d = {}
        self.momp_63d = {}
        self.adx_ind = {}

        for ticker in self.tickers.keys():
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

    def get_current_leverage(self):
        """Adjust leverage based on VIX."""
        vix = self.get_vix_level()
        if vix > 30:
            return 1.0  # No leverage in high vol
        elif vix > 25:
            return 1.25
        else:
            return self.leverage  # Full 1.5x

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
            days_held = (self.time - self.entry_dates[ticker]).days

            if ticker not in self.highest_prices:
                self.highest_prices[ticker] = entry_price
            self.highest_prices[ticker] = max(self.highest_prices[ticker], current_price)

            should_exit = False
            reason = ""

            if pnl_pct >= self.profit_target:
                should_exit = True
                reason = f"PROFIT(+{pnl_pct:.1%})"
            elif pnl_pct <= self.stop_loss:
                should_exit = True
                reason = f"STOP({pnl_pct:.1%})"
            elif self.highest_prices[ticker] > entry_price * 1.02:
                drawdown = (current_price - self.highest_prices[ticker]) / self.highest_prices[ticker]
                if drawdown < -0.025:  # Tighter 2.5% trail with leverage
                    should_exit = True
                    reason = f"TRAIL({pnl_pct:+.1%})"
            elif days_held >= self.max_hold_days:
                should_exit = True
                reason = f"TIME({days_held}d)"

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
            self.liquidate()
            for t in list(self.entry_dates.keys()):
                self._cleanup(t)
            return

        current_leverage = self.get_current_leverage()

        scores = []
        for ticker, sector in self.tickers.items():
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

            if adx_val < 20 or positive_di <= negative_di:
                continue

            mom_short = self.momp_20d[ticker].current.value
            mom_long = self.momp_63d[ticker].current.value

            if mom_short <= 0 or mom_long <= 0:
                continue

            score = (mom_short * 0.6 + mom_long * 0.4) * (adx_val / 100)
            scores.append({"ticker": ticker, "symbol": symbol, "sector": sector, "score": score})

        scores.sort(key=lambda x: x["score"], reverse=True)

        max_positions = 8
        current_count = len(self.entry_dates)
        slots = max_positions - current_count

        selected = []
        sector_count = {}
        for s in scores:
            sector = s["sector"]
            sector_count[sector] = sector_count.get(sector, 0)
            if sector_count[sector] < 2:
                selected.append(s)
                sector_count[sector] += 1
            if len(selected) >= slots:
                break

        # Leveraged weight
        weight = (current_leverage / max_positions)
        for s in selected:
            ticker = s["ticker"]
            symbol = s["symbol"]
            price = self.securities[symbol].price

            self.set_holdings(symbol, weight)
            self.entry_dates[ticker] = self.time
            self.entry_prices[ticker] = price
            self.highest_prices[ticker] = price
            self.debug(f"{self.time.date()}: ENTER {ticker} @ ${price:.2f} (lev={current_leverage:.1f}x)")
