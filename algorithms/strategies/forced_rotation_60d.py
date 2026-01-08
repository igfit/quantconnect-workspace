# region imports
from AlgorithmImports import *
# endregion

class ForcedRotation60DStrategy(QCAlgorithm):
    """
    Round 11 Strategy 3: Forced Rotation Every 60 Days

    Key idea: Sell any position held > 60 days regardless of signal.
    - Forces strategy to re-evaluate and re-enter if still strong
    - Prevents riding winners forever
    - Alpha comes from repeated entry timing, not holding

    Same entry logic as TrendStrengthMom, but with forced exits.
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.max_hold_days = 60  # Forced exit after 60 days
        self.entry_dates = {}    # Track when each position was entered

        # Trading universe
        self.tickers = {
            "AAPL": "Tech", "MSFT": "Tech", "NVDA": "Tech", "GOOGL": "Tech",
            "META": "Tech", "AVGO": "Tech", "CRM": "Tech",
            "AMZN": "ConsDisc", "TSLA": "ConsDisc", "HD": "ConsDisc", "NKE": "ConsDisc",
            "UNH": "Health", "LLY": "Health", "ABBV": "Health", "JNJ": "Health", "PFE": "Health",
            "JPM": "Finance", "GS": "Finance", "BLK": "Finance", "V": "Finance",
            "CAT": "Industrial", "HON": "Industrial", "GE": "Industrial", "UPS": "Industrial",
            "NFLX": "Comm", "CMCSA": "Comm", "DIS": "Comm",
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

            self.momp_ind[ticker] = self.momp(sym, 126, Resolution.DAILY)
            self.adx_ind[ticker] = self.adx(sym, 14, Resolution.DAILY)

        # SPY for regime
        spy = self.add_equity("SPY", Resolution.DAILY)
        spy.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
        self.spy = spy.symbol
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)

        # Monthly rebalance for new entries
        self.schedule.on(
            self.date_rules.month_start("SPY"),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )

        # Daily check for forced rotation
        self.schedule.on(
            self.date_rules.every_day("SPY"),
            self.time_rules.after_market_open("SPY", 31),
            self.check_rotation
        )

        self.set_benchmark("SPY")
        self.set_warm_up(150, Resolution.DAILY)

    def check_rotation(self):
        """Force exit any position held > 60 days."""
        if self.is_warming_up:
            return

        for ticker, entry_date in list(self.entry_dates.items()):
            days_held = (self.time - entry_date).days
            if days_held > self.max_hold_days:
                symbol = self.symbols[ticker]
                if self.portfolio[symbol].invested:
                    self.liquidate(symbol)
                    self.debug(f"{self.time.date()}: FORCED EXIT {ticker} after {days_held} days")
                del self.entry_dates[ticker]

    def rebalance(self):
        if self.is_warming_up:
            return

        # Market regime filter
        spy_price = self.securities[self.spy].price
        if not self.spy_sma_200.is_ready or spy_price < self.spy_sma_200.current.value:
            self.liquidate()
            self.entry_dates.clear()
            self.debug(f"{self.time.date()}: Bear market - all cash")
            return

        # Calculate scores
        scores = []
        for ticker, sector in self.tickers.items():
            symbol = self.symbols[ticker]

            if not self.securities[symbol].has_data:
                continue
            if not self.momp_ind[ticker].is_ready:
                continue
            if not self.adx_ind[ticker].is_ready:
                continue

            adx_val = self.adx_ind[ticker].current.value
            positive_di = self.adx_ind[ticker].positive_directional_index.current.value
            negative_di = self.adx_ind[ticker].negative_directional_index.current.value

            if adx_val < 20:
                continue
            if positive_di <= negative_di:
                continue

            mom = self.momp_ind[ticker].current.value
            if mom <= 0:
                continue

            trend_strength = (adx_val / 100) * (positive_di / (positive_di + negative_di + 0.001))
            score = mom * (1 + trend_strength)

            scores.append({
                "ticker": ticker,
                "symbol": symbol,
                "sector": sector,
                "score": score
            })

        scores.sort(key=lambda x: x["score"], reverse=True)

        # Select top 8 with sector constraints
        selected = []
        sector_count = {}
        max_per_sector = 3

        for s in scores:
            sector = s["sector"]
            sector_count[sector] = sector_count.get(sector, 0)

            if sector_count[sector] < max_per_sector:
                selected.append(s)
                sector_count[sector] += 1

            if len(selected) >= 8:
                break

        if not selected:
            self.liquidate()
            self.entry_dates.clear()
            return

        weight = 1.0 / len(selected)

        # Liquidate positions not in selected
        selected_symbols = {s["symbol"] for s in selected}
        for holding in self.portfolio.values():
            if holding.invested and holding.symbol not in selected_symbols:
                self.liquidate(holding.symbol)
                # Clean up entry date
                for t, sym in self.symbols.items():
                    if sym == holding.symbol and t in self.entry_dates:
                        del self.entry_dates[t]
                        break

        # Allocate and track entry dates
        for s in selected:
            ticker = s["ticker"]
            symbol = s["symbol"]

            if not self.portfolio[symbol].invested:
                # New position - record entry date
                self.entry_dates[ticker] = self.time

            self.set_holdings(symbol, weight)

        self.debug(f"{self.time.date()}: {len(selected)} positions")
