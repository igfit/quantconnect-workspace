# region imports
from AlgorithmImports import *
# endregion

class AccelMomentumStrategy(QCAlgorithm):
    """
    Round 10 Strategy 3: Accelerating Momentum Only

    Key idea: Only enter when momentum is ACCELERATING, not just positive.
    - Entry: 1-month mom > 3-month mom (acceleration) AND ADX > 20
    - Exit: When acceleration reverses

    Hypothesis: Catches trends early, exits before reversals.
    Based on academic research showing accelerating momentum outperforms.
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

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
        self.momp_1m = {}  # 21-day momentum
        self.momp_3m = {}  # 63-day momentum
        self.momp_6m = {}  # 126-day momentum
        self.adx_ind = {}

        for ticker in self.tickers.keys():
            equity = self.add_equity(ticker, Resolution.DAILY)
            equity.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
            sym = equity.symbol
            self.symbols[ticker] = sym

            self.momp_1m[ticker] = self.momp(sym, 21, Resolution.DAILY)
            self.momp_3m[ticker] = self.momp(sym, 63, Resolution.DAILY)
            self.momp_6m[ticker] = self.momp(sym, 126, Resolution.DAILY)
            self.adx_ind[ticker] = self.adx(sym, 14, Resolution.DAILY)

        # SPY for regime
        spy = self.add_equity("SPY", Resolution.DAILY)
        spy.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
        self.spy = spy.symbol
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)

        # Bi-weekly rebalance (faster reaction to acceleration changes)
        self.schedule.on(
            self.date_rules.every([DayOfWeek.MONDAY]),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )

        self.last_rebalance = None

        self.set_benchmark("SPY")
        self.set_warm_up(150, Resolution.DAILY)

    def rebalance(self):
        if self.is_warming_up:
            return

        # Rebalance every 2 weeks
        if self.last_rebalance and (self.time - self.last_rebalance).days < 14:
            return
        self.last_rebalance = self.time

        # Market regime filter
        spy_price = self.securities[self.spy].price
        if not self.spy_sma_200.is_ready or spy_price < self.spy_sma_200.current.value:
            self.liquidate()
            self.debug(f"{self.time.date()}: Bear market - all cash")
            return

        # Calculate acceleration scores
        scores = []
        for ticker, sector in self.tickers.items():
            symbol = self.symbols[ticker]

            if not self.securities[symbol].has_data:
                continue
            if not self.momp_1m[ticker].is_ready:
                continue
            if not self.momp_3m[ticker].is_ready:
                continue
            if not self.momp_6m[ticker].is_ready:
                continue
            if not self.adx_ind[ticker].is_ready:
                continue

            mom_1m = self.momp_1m[ticker].current.value
            mom_3m = self.momp_3m[ticker].current.value
            mom_6m = self.momp_6m[ticker].current.value

            # All momentum must be positive
            if mom_6m <= 0:
                continue

            # ACCELERATION CHECK: Short-term > Long-term
            # This means momentum is speeding up
            is_accelerating = mom_1m > mom_3m

            if not is_accelerating:
                continue

            # ADX filter for trending
            adx_val = self.adx_ind[ticker].current.value
            positive_di = self.adx_ind[ticker].positive_directional_index.current.value
            negative_di = self.adx_ind[ticker].negative_directional_index.current.value

            if adx_val < 15:  # Slightly lower threshold since acceleration is strong signal
                continue
            if positive_di <= negative_di:
                continue

            # Acceleration score: How much faster is 1m vs 3m?
            acceleration = mom_1m - mom_3m
            # Weighted momentum for ranking
            weighted_mom = (mom_1m * 0.5) + (mom_3m * 0.3) + (mom_6m * 0.2)

            # Final score combines acceleration and momentum
            score = weighted_mom * (1 + acceleration / 100)

            scores.append({
                "ticker": ticker,
                "symbol": symbol,
                "sector": sector,
                "score": score,
                "acceleration": acceleration,
                "mom_1m": mom_1m,
                "mom_3m": mom_3m
            })

        # Sort by score
        scores.sort(key=lambda x: x["score"], reverse=True)

        # Select top 8 with sector constraints
        target_positions = 8
        selected = []
        sector_count = {}
        max_per_sector = 3

        for s in scores:
            sector = s["sector"]
            sector_count[sector] = sector_count.get(sector, 0)

            if sector_count[sector] < max_per_sector:
                selected.append(s)
                sector_count[sector] += 1

            if len(selected) >= target_positions:
                break

        if not selected:
            self.liquidate()
            return

        # Equal weight
        weight = 1.0 / len(selected)

        # Liquidate old
        selected_symbols = {s["symbol"] for s in selected}
        for holding in self.portfolio.values():
            if holding.invested and holding.symbol not in selected_symbols:
                self.liquidate(holding.symbol)

        # Allocate
        for s in selected:
            self.set_holdings(s["symbol"], weight)

        top3 = ", ".join([f"{s['ticker']}(accel={s['acceleration']:.1f})" for s in selected[:3]])
        self.debug(f"{self.time.date()}: {len(selected)} accelerating positions. Top3: {top3}")
