# region imports
from AlgorithmImports import *
# endregion

class LetWinnersRunOOS(QCAlgorithm):
    """
    Out-of-Sample Test: Let Winners Run on 2015-2020

    NO LEVERAGE - testing pure signal alpha on different period.
    Same logic as R15 Let Winners Run but with adjusted universe.
    """

    def initialize(self):
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2020, 1, 1)
        self.set_cash(100000)

        self.stop_loss = -0.07
        self.trailing_pct = 0.12
        self.trailing_activation = 0.08

        self.entry_dates = {}
        self.entry_prices = {}
        self.highest_prices = {}

        # Adjusted universe for 2015-2020
        self.tickers = {
            "AAPL": "Tech", "MSFT": "Tech", "NVDA": "Tech", "GOOGL": "Tech",
            "CRM": "Tech", "ADBE": "Tech", "INTC": "Tech",
            "AMZN": "ConsDisc", "HD": "ConsDisc", "NKE": "ConsDisc", "SBUX": "ConsDisc",
            "UNH": "Health", "ABBV": "Health", "JNJ": "Health", "PFE": "Health",
            "JPM": "Finance", "GS": "Finance", "BLK": "Finance", "V": "Finance",
            "CAT": "Industrial", "HON": "Industrial", "GE": "Industrial", "UPS": "Industrial",
            "NFLX": "Comm", "DIS": "Comm", "CMCSA": "Comm",
            "COST": "Staples", "PG": "Staples", "KO": "Staples",
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

            if ticker not in self.highest_prices:
                self.highest_prices[ticker] = entry_price
            self.highest_prices[ticker] = max(self.highest_prices[ticker], current_price)

            should_exit = False
            reason = ""

            if pnl_pct <= self.stop_loss:
                should_exit = True
                reason = f"STOP({pnl_pct:.1%})"
            elif pnl_pct >= self.trailing_activation:
                drawdown = (current_price - self.highest_prices[ticker]) / self.highest_prices[ticker]
                if drawdown < -self.trailing_pct:
                    peak_gain = (self.highest_prices[ticker] / entry_price - 1)
                    should_exit = True
                    reason = f"TRAIL({pnl_pct:+.1%}, peak+{peak_gain:.1%})"

            if not should_exit and ticker in self.adx_ind:
                adx = self.adx_ind[ticker]
                if adx.is_ready:
                    pos_di = adx.positive_directional_index.current.value
                    neg_di = adx.negative_directional_index.current.value
                    if neg_di > pos_di + 10:
                        should_exit = True
                        reason = f"TREND_REV"

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

        vix_level = self.get_vix_level()
        if vix_level > 30:
            return

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

        weight = 1.0 / max_positions
        for s in selected:
            ticker = s["ticker"]
            symbol = s["symbol"]
            price = self.securities[symbol].price

            self.set_holdings(symbol, weight)
            self.entry_dates[ticker] = self.time
            self.entry_prices[ticker] = price
            self.highest_prices[ticker] = price
            self.debug(f"{self.time.date()}: ENTER {ticker} @ ${price:.2f}")
