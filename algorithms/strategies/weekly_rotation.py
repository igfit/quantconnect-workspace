# region imports
from AlgorithmImports import *
# endregion

class WeeklyRotationStrategy(QCAlgorithm):
    """
    Round 12 Strategy 3: Weekly Rotation (Exactly 5 Days)

    TRUE SIGNAL ALPHA: Hold exactly 5 trading days, then rotate.

    Rules:
    - Every Monday: Liquidate ALL, buy top 8 momentum
    - Hold exactly until next Monday
    - No position can compound beyond 1 week
    - Alpha = weekly momentum timing
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
            "NFLX": "Comm", "DIS": "Comm",
            "COST": "Staples", "PG": "Staples",
        }

        self.symbols = {}
        self.momp_5d = {}  # 5-day momentum for weekly rotation
        self.adx_ind = {}

        for ticker in self.tickers.keys():
            equity = self.add_equity(ticker, Resolution.DAILY)
            equity.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
            sym = equity.symbol
            self.symbols[ticker] = sym

            self.momp_5d[ticker] = self.momp(sym, 5, Resolution.DAILY)  # 1-week momentum
            self.adx_ind[ticker] = self.adx(sym, 14, Resolution.DAILY)

        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma_50 = self.sma(self.spy, 50, Resolution.DAILY)  # Shorter SMA for weekly

        # Weekly rotation on Monday
        self.schedule.on(
            self.date_rules.every([DayOfWeek.MONDAY]),
            self.time_rules.after_market_open("SPY", 30),
            self.weekly_rotate
        )

        self.set_benchmark("SPY")
        self.set_warm_up(30, Resolution.DAILY)

    def weekly_rotate(self):
        """Liquidate everything, buy top weekly momentum."""
        if self.is_warming_up:
            return

        # ALWAYS liquidate first - no positions carry over
        self.liquidate()

        # Market regime (using 50 SMA for faster response)
        spy_price = self.securities[self.spy].price
        if not self.spy_sma_50.is_ready or spy_price < self.spy_sma_50.current.value:
            self.debug(f"{self.time.date()}: Bear regime - staying cash")
            return

        # Score by 5-day momentum
        scores = []
        for ticker, sector in self.tickers.items():
            symbol = self.symbols[ticker]

            if not self.momp_5d[ticker].is_ready:
                continue
            if not self.adx_ind[ticker].is_ready:
                continue

            mom_5d = self.momp_5d[ticker].current.value

            # Only positive short-term momentum
            if mom_5d <= 0:
                continue

            # ADX for trend confirmation
            adx_val = self.adx_ind[ticker].current.value
            if adx_val < 15:  # Lower threshold for weekly
                continue

            scores.append({
                "ticker": ticker,
                "symbol": symbol,
                "sector": sector,
                "score": mom_5d
            })

        scores.sort(key=lambda x: x["score"], reverse=True)

        # Select top 8 with sector constraints
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
            return

        # Equal weight
        weight = 1.0 / len(selected)

        for s in selected:
            self.set_holdings(s["symbol"], weight)

        tickers = ", ".join([s["ticker"] for s in selected])
        self.debug(f"{self.time.date()}: WEEKLY: {tickers}")
