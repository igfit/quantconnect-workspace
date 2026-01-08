# region imports
from AlgorithmImports import *
# endregion

class AntiConcentrationStrategy(QCAlgorithm):
    """
    Round 11 Strategy 5: Anti-Concentration Filter

    Key idea: Exclude stocks that have already run up >50% in past 6 months.
    - Prevents buying into extended stocks (like NVDA at the top)
    - Forces the strategy to find NEW opportunities
    - Alpha comes from finding emerging momentum, not chasing

    Uses ROC filter to identify extended stocks.
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.max_6m_gain = 0.50  # Exclude stocks up >50% in 6 months

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
        self.roc_6m = {}  # 6-month rate of change

        for ticker in self.tickers.keys():
            equity = self.add_equity(ticker, Resolution.DAILY)
            equity.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
            sym = equity.symbol
            self.symbols[ticker] = sym

            self.momp_ind[ticker] = self.momp(sym, 63, Resolution.DAILY)  # 3-month momentum for scoring
            self.adx_ind[ticker] = self.adx(sym, 14, Resolution.DAILY)
            self.roc_6m[ticker] = self.rocp(sym, 126, Resolution.DAILY)  # 6-month ROC for filtering

        # SPY for regime
        spy = self.add_equity("SPY", Resolution.DAILY)
        spy.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
        self.spy = spy.symbol
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)

        # Monthly rebalance
        self.schedule.on(
            self.date_rules.month_start("SPY"),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )

        self.set_benchmark("SPY")
        self.set_warm_up(150, Resolution.DAILY)

    def rebalance(self):
        if self.is_warming_up:
            return

        # Market regime filter
        spy_price = self.securities[self.spy].price
        if not self.spy_sma_200.is_ready or spy_price < self.spy_sma_200.current.value:
            self.liquidate()
            self.debug(f"{self.time.date()}: Bear market - all cash")
            return

        # Calculate scores with anti-concentration filter
        scores = []
        excluded = []

        for ticker, sector in self.tickers.items():
            symbol = self.symbols[ticker]

            if not self.securities[symbol].has_data:
                continue
            if not self.momp_ind[ticker].is_ready:
                continue
            if not self.adx_ind[ticker].is_ready:
                continue
            if not self.roc_6m[ticker].is_ready:
                continue

            # ANTI-CONCENTRATION: Exclude stocks up >50% in 6 months
            roc_6m_val = self.roc_6m[ticker].current.value
            if roc_6m_val > self.max_6m_gain:
                excluded.append(f"{ticker}(+{roc_6m_val:.0%})")
                continue

            # ADX filter
            adx_val = self.adx_ind[ticker].current.value
            positive_di = self.adx_ind[ticker].positive_directional_index.current.value
            negative_di = self.adx_ind[ticker].negative_directional_index.current.value

            if adx_val < 20:
                continue
            if positive_di <= negative_di:
                continue

            # Positive momentum (using 3-month, not 6-month to catch earlier)
            mom = self.momp_ind[ticker].current.value
            if mom <= 0:
                continue

            trend_strength = (adx_val / 100) * (positive_di / (positive_di + negative_di + 0.001))
            score = mom * (1 + trend_strength)

            scores.append({
                "ticker": ticker,
                "symbol": symbol,
                "sector": sector,
                "score": score,
                "roc_6m": roc_6m_val
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
            return

        weight = 1.0 / len(selected)

        # Liquidate old
        selected_symbols = {s["symbol"] for s in selected}
        for holding in self.portfolio.values():
            if holding.invested and holding.symbol not in selected_symbols:
                self.liquidate(holding.symbol)

        # Allocate
        for s in selected:
            self.set_holdings(s["symbol"], weight)

        if excluded:
            self.debug(f"{self.time.date()}: Excluded extended: {', '.join(excluded[:3])}")
        top3 = ", ".join([f"{s['ticker']}(+{s['roc_6m']:.0%})" for s in selected[:3]])
        self.debug(f"{self.time.date()}: {len(selected)} positions: {top3}")
