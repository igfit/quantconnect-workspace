# region imports
from AlgorithmImports import *
# endregion

class ContrarianMomentumR13(QCAlgorithm):
    """
    Round 13 Strategy 4: Contrarian Momentum

    SIGNAL ALPHA by avoiding crowded winners.

    Thesis:
    - Exclude stocks already up >30% in 3 months (crowded trades)
    - Buy from remaining stocks with positive momentum
    - Forces rotation to emerging leaders, not last year's winners
    - Avoids mean reversion risk on extended stocks

    Rules:
    - Exclude: stocks up >30% in 60 days (extended)
    - Include: stocks with positive 20-day momentum, ADX > 20
    - Select top 8 by momentum from non-excluded pool
    - Weekly rebalance
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.tickers = {
            "AAPL": "Tech", "MSFT": "Tech", "NVDA": "Tech", "GOOGL": "Tech",
            "META": "Tech", "AVGO": "Tech", "CRM": "Tech", "AMD": "Tech",
            "AMZN": "ConsDisc", "TSLA": "ConsDisc", "HD": "ConsDisc", "NKE": "ConsDisc",
            "UNH": "Health", "LLY": "Health", "ABBV": "Health", "JNJ": "Health",
            "JPM": "Finance", "GS": "Finance", "BLK": "Finance", "V": "Finance",
            "CAT": "Industrial", "HON": "Industrial", "GE": "Industrial", "UPS": "Industrial",
            "NFLX": "Comm", "DIS": "Comm", "COST": "Staples", "PG": "Staples"
        }

        self.symbols = {}
        self.mom_20d = {}  # Short-term momentum (entry signal)
        self.mom_60d = {}  # Medium-term (exclusion filter)
        self.adx_ind = {}

        for ticker in self.tickers.keys():
            equity = self.add_equity(ticker, Resolution.DAILY)
            equity.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
            sym = equity.symbol
            self.symbols[ticker] = sym

            self.mom_20d[ticker] = self.momp(sym, 20, Resolution.DAILY)
            self.mom_60d[ticker] = self.momp(sym, 60, Resolution.DAILY)
            self.adx_ind[ticker] = self.adx(sym, 14, Resolution.DAILY)

        # Market regime
        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)

        # Weekly rebalance
        self.schedule.on(
            self.date_rules.every([DayOfWeek.MONDAY]),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )

        self.exclusion_threshold = 0.50  # Exclude if up >50% in 60 days (less restrictive)

        self.set_benchmark("SPY")
        self.set_warm_up(70, Resolution.DAILY)

    def rebalance(self):
        """Weekly rebalance with contrarian filter."""
        if self.is_warming_up:
            return

        # Market regime filter
        spy_price = self.securities[self.spy].price
        if not self.spy_sma_200.is_ready or spy_price < self.spy_sma_200.current.value:
            self.liquidate()
            self.debug(f"{self.time.date()}: Bear regime - cash")
            return

        # Score stocks, excluding extended ones
        scores = []
        excluded = []

        for ticker, sector in self.tickers.items():
            symbol = self.symbols[ticker]

            if not self.mom_20d[ticker].is_ready:
                continue
            if not self.mom_60d[ticker].is_ready:
                continue
            if not self.adx_ind[ticker].is_ready:
                continue

            mom_short = self.mom_20d[ticker].current.value
            mom_medium = self.mom_60d[ticker].current.value
            adx_val = self.adx_ind[ticker].current.value

            # EXCLUSION: Skip stocks already up >30% in 60 days
            if mom_medium > self.exclusion_threshold:
                excluded.append(ticker)
                continue

            # Entry criteria: positive short-term momentum + trending
            if mom_short > 0 and adx_val > 20:
                scores.append({
                    "ticker": ticker,
                    "symbol": symbol,
                    "sector": sector,
                    "mom_20d": mom_short,
                    "mom_60d": mom_medium,
                    "adx": adx_val
                })

        # Sort by 20-day momentum
        scores.sort(key=lambda x: x["mom_20d"], reverse=True)

        # Select top 8 with sector cap
        selected = []
        sector_count = {}
        for s in scores:
            sector = s["sector"]
            sector_count[sector] = sector_count.get(sector, 0)
            if sector_count[sector] < 2:
                selected.append(s)
                sector_count[sector] += 1
            if len(selected) >= 8:
                break

        if not selected:
            self.liquidate()
            return

        # Liquidate positions not selected
        selected_symbols = [s["symbol"] for s in selected]
        for ticker in self.tickers.keys():
            symbol = self.symbols[ticker]
            if symbol not in selected_symbols and self.portfolio[symbol].invested:
                self.liquidate(symbol)

        # Equal weight
        weight = 1.0 / len(selected)

        for s in selected:
            self.set_holdings(s["symbol"], weight)

        tickers = ", ".join([s["ticker"] for s in selected])
        self.debug(f"{self.time.date()}: CONTRARIAN: {tickers} | Excluded: {len(excluded)}")
