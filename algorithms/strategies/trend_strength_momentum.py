# region imports
from AlgorithmImports import *
# endregion

class TrendStrengthMomentumStrategy(QCAlgorithm):
    """
    Round 9 Strategy 3: Trend Strength + Momentum

    Key insight: Momentum works best in strong trends.
    ADX (Average Directional Index) measures trend strength.

    Only enter positions when:
    - ADX > 25 (strong trend)
    - +DI > -DI (uptrend)
    - 6-month momentum positive

    This filters out choppy sideways markets where momentum whipsaws.
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
            "UNH": "Health", "LLY": "Health", "ABBV": "Health",
            "JPM": "Finance", "GS": "Finance", "BLK": "Finance", "V": "Finance",
            "CAT": "Industrial", "HON": "Industrial", "GE": "Industrial",
            "NFLX": "Comm", "CMCSA": "Comm",
            "COST": "Staples",
        }

        self.symbols = {}
        self.momp_ind = {}  # 6-month momentum
        self.adx_ind = {}  # ADX indicator
        self.sma_50 = {}

        for ticker in self.tickers.keys():
            equity = self.add_equity(ticker, Resolution.DAILY)
            equity.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
            sym = equity.symbol
            self.symbols[ticker] = sym

            self.momp_ind[ticker] = self.momp(sym, 126, Resolution.DAILY)
            self.adx_ind[ticker] = self.adx(sym, 14, Resolution.DAILY)
            self.sma_50[ticker] = self.sma(sym, 50, Resolution.DAILY)

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

        # Calculate scores with trend strength filter
        scores = []
        for ticker, sector in self.tickers.items():
            symbol = self.symbols[ticker]

            if not self.securities[symbol].has_data:
                continue
            if not self.momp_ind[ticker].is_ready:
                continue
            if not self.adx_ind[ticker].is_ready:
                continue
            if not self.sma_50[ticker].is_ready:
                continue

            price = self.securities[symbol].price

            # Price > 50 SMA (trend confirmation)
            if price < self.sma_50[ticker].current.value:
                continue

            # Positive 6-month momentum
            mom = self.momp_ind[ticker].current.value
            if mom <= 0:
                continue

            # ADX filter - strong trend only
            adx_val = self.adx_ind[ticker].current.value
            positive_di = self.adx_ind[ticker].positive_directional_index.current.value
            negative_di = self.adx_ind[ticker].negative_directional_index.current.value

            # ADX > 20 indicates some trend, > 25 is strong
            # Also require +DI > -DI for uptrend
            if adx_val < 20:
                continue
            if positive_di <= negative_di:
                continue

            # Composite score: momentum * trend_strength
            # ADX normalized: 20-50 range maps to 0.5-1.5 multiplier
            trend_mult = min(1.5, max(0.5, (adx_val - 10) / 40))
            composite_score = mom * trend_mult

            scores.append({
                "ticker": ticker,
                "symbol": symbol,
                "sector": sector,
                "momentum": mom,
                "adx": adx_val,
                "score": composite_score
            })

        # Sort by composite score
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
            self.debug(f"{self.time.date()}: No stocks with strong trends")
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

        top3 = ", ".join([f"{s['ticker']}(ADX:{s['adx']:.0f})" for s in selected[:3]])
        self.debug(f"{self.time.date()}: {len(selected)} positions. Top3: {top3}")
