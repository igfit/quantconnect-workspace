# region imports
from AlgorithmImports import *
# endregion

class TakeProfit8PctStrategy(QCAlgorithm):
    """
    Round 12 Strategy 2: Take Profit at 8%

    TRUE SIGNAL ALPHA: Entry timing only, no letting winners run.

    Rules:
    - Same ADX entry as before (proven to work)
    - ALWAYS exit at 8% profit - no exceptions
    - Exit at -5% stop loss
    - Max hold 20 days even if neither target hit
    - Alpha = entry timing, not riding winners
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.profit_target = 0.08  # 8% take profit
        self.stop_loss = -0.05     # 5% stop loss
        self.max_hold_days = 20    # Max 20 days hold
        self.entry_dates = {}
        self.entry_prices = {}

        self.tickers = {
            "AAPL": "Tech", "MSFT": "Tech", "NVDA": "Tech", "GOOGL": "Tech",
            "META": "Tech", "AVGO": "Tech", "CRM": "Tech",
            "AMZN": "ConsDisc", "TSLA": "ConsDisc", "HD": "ConsDisc", "NKE": "ConsDisc",
            "UNH": "Health", "LLY": "Health", "ABBV": "Health", "JNJ": "Health",
            "JPM": "Finance", "GS": "Finance", "BLK": "Finance", "V": "Finance",
            "CAT": "Industrial", "HON": "Industrial", "GE": "Industrial", "UPS": "Industrial",
            "NFLX": "Comm", "DIS": "Comm",
            "COST": "Staples", "PG": "Staples",
        }

        self.symbols = {}
        self.momp_ind = {}
        self.adx_ind = {}

        for ticker in self.tickers.keys():
            equity = self.add_equity(ticker, Resolution.DAILY)
            equity.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
            sym = equity.symbol
            self.symbols[ticker] = sym

            self.momp_ind[ticker] = self.momp(sym, 63, Resolution.DAILY)
            self.adx_ind[ticker] = self.adx(sym, 14, Resolution.DAILY)

        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)

        # Daily check for exits
        self.schedule.on(
            self.date_rules.every_day("SPY"),
            self.time_rules.after_market_open("SPY", 30),
            self.check_exits
        )

        # Weekly rebalance for entries
        self.schedule.on(
            self.date_rules.every([DayOfWeek.MONDAY]),
            self.time_rules.after_market_open("SPY", 31),
            self.rebalance
        )

        self.set_benchmark("SPY")
        self.set_warm_up(100, Resolution.DAILY)

    def check_exits(self):
        """Daily check for profit target, stop loss, or time exit."""
        if self.is_warming_up:
            return

        for ticker in list(self.entry_dates.keys()):
            symbol = self.symbols[ticker]
            if not self.portfolio[symbol].invested:
                if ticker in self.entry_dates:
                    del self.entry_dates[ticker]
                if ticker in self.entry_prices:
                    del self.entry_prices[ticker]
                continue

            days_held = (self.time - self.entry_dates[ticker]).days
            current_price = self.securities[symbol].price
            entry_price = self.entry_prices[ticker]
            pnl_pct = (current_price - entry_price) / entry_price

            should_exit = False
            reason = ""

            # Profit target - ALWAYS take profits at 8%
            if pnl_pct >= self.profit_target:
                should_exit = True
                reason = f"PROFIT(+{pnl_pct:.1%})"

            # Stop loss
            elif pnl_pct <= self.stop_loss:
                should_exit = True
                reason = f"STOP({pnl_pct:.1%})"

            # Time exit
            elif days_held >= self.max_hold_days:
                should_exit = True
                reason = f"TIME({days_held}d, {pnl_pct:+.1%})"

            if should_exit:
                self.liquidate(symbol)
                self.debug(f"{self.time.date()}: EXIT {ticker} {reason}")
                del self.entry_dates[ticker]
                del self.entry_prices[ticker]

    def rebalance(self):
        """Weekly check for new entries."""
        if self.is_warming_up:
            return

        # Market regime
        spy_price = self.securities[self.spy].price
        if not self.spy_sma_200.is_ready or spy_price < self.spy_sma_200.current.value:
            return

        # Score stocks
        scores = []
        for ticker, sector in self.tickers.items():
            symbol = self.symbols[ticker]

            # Skip if already holding
            if ticker in self.entry_dates:
                continue

            if not self.momp_ind[ticker].is_ready or not self.adx_ind[ticker].is_ready:
                continue

            adx_val = self.adx_ind[ticker].current.value
            positive_di = self.adx_ind[ticker].positive_directional_index.current.value
            negative_di = self.adx_ind[ticker].negative_directional_index.current.value

            if adx_val < 20 or positive_di <= negative_di:
                continue

            mom = self.momp_ind[ticker].current.value
            if mom <= 0:
                continue

            score = mom * (adx_val / 100)
            scores.append({"ticker": ticker, "symbol": symbol, "sector": sector, "score": score})

        scores.sort(key=lambda x: x["score"], reverse=True)

        # Fill up to 8 positions
        current_count = len(self.entry_dates)
        slots = 8 - current_count

        selected = []
        sector_count = {}
        for s in scores:
            sector = s["sector"]
            sector_count[sector] = sector_count.get(sector, 0)
            if sector_count[sector] < 2:  # Max 2 per sector
                selected.append(s)
                sector_count[sector] += 1
            if len(selected) >= slots:
                break

        # Enter new positions
        weight = 0.12  # ~12% each
        for s in selected:
            ticker = s["ticker"]
            symbol = s["symbol"]
            price = self.securities[symbol].price

            self.set_holdings(symbol, weight)
            self.entry_dates[ticker] = self.time
            self.entry_prices[ticker] = price
            self.debug(f"{self.time.date()}: ENTER {ticker} @ ${price:.2f}")
