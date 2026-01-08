# region imports
from AlgorithmImports import *
# endregion

class VolRegimeStrategicStrategy(QCAlgorithm):
    """
    Round 9 Strategy 4: Volatility Regime Strategic

    Key insight: Different strategies work in different volatility regimes.

    - Low vol (VIX < 18): Concentrated momentum (6 positions, high conviction)
    - Normal vol (VIX 18-25): Balanced approach (8 positions)
    - High vol (VIX > 25): Defensive posture (reduce exposure, add quality filter)
    - Very high vol (VIX > 35): Go to cash

    Also adjusts rebalancing frequency based on regime.
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # VIX for volatility regime
        self.vix = self.add_data(CBOE, "VIX", Resolution.DAILY).symbol

        # Trading universe with quality flags
        self.tickers = {
            # High quality (profitable, stable) - use in high vol
            "AAPL": {"sector": "Tech", "quality": True},
            "MSFT": {"sector": "Tech", "quality": True},
            "GOOGL": {"sector": "Tech", "quality": True},
            "AVGO": {"sector": "Tech", "quality": True},
            "V": {"sector": "Finance", "quality": True},
            "JPM": {"sector": "Finance", "quality": True},
            "UNH": {"sector": "Health", "quality": True},
            "JNJ": {"sector": "Health", "quality": True},
            "COST": {"sector": "Staples", "quality": True},
            "PG": {"sector": "Staples", "quality": True},
            "HD": {"sector": "ConsDisc", "quality": True},

            # Growth/momentum (volatile) - use in low vol only
            "NVDA": {"sector": "Tech", "quality": False},
            "META": {"sector": "Tech", "quality": False},
            "CRM": {"sector": "Tech", "quality": False},
            "TSLA": {"sector": "ConsDisc", "quality": False},
            "AMZN": {"sector": "ConsDisc", "quality": False},
            "NFLX": {"sector": "Comm", "quality": False},
            "GS": {"sector": "Finance", "quality": False},
            "BLK": {"sector": "Finance", "quality": False},
            "LLY": {"sector": "Health", "quality": False},
            "ABBV": {"sector": "Health", "quality": False},
            "CAT": {"sector": "Industrial", "quality": False},
            "GE": {"sector": "Industrial", "quality": False},
            "HON": {"sector": "Industrial", "quality": False},
        }

        self.symbols = {}
        self.momp_ind = {}
        self.sma_50 = {}

        for ticker in self.tickers.keys():
            equity = self.add_equity(ticker, Resolution.DAILY)
            equity.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
            sym = equity.symbol
            self.symbols[ticker] = sym
            self.momp_ind[ticker] = self.momp(sym, 126, Resolution.DAILY)
            self.sma_50[ticker] = self.sma(sym, 50, Resolution.DAILY)

        # SPY for regime
        spy = self.add_equity("SPY", Resolution.DAILY)
        spy.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
        self.spy = spy.symbol
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)

        # Last rebalance date for frequency control
        self.last_rebalance = None

        # Weekly check
        self.schedule.on(
            self.date_rules.every_day("SPY"),
            self.time_rules.after_market_open("SPY", 30),
            self.check_rebalance
        )

        self.set_benchmark("SPY")
        self.set_warm_up(150, Resolution.DAILY)

    def get_regime(self, vix_value):
        """Determine volatility regime from VIX."""
        if vix_value < 18:
            return "LOW_VOL", 6, True, 21   # positions, include_growth, min_days
        elif vix_value < 25:
            return "NORMAL_VOL", 8, True, 21
        elif vix_value < 35:
            return "HIGH_VOL", 6, False, 14  # quality only, more frequent rebalance
        else:
            return "EXTREME_VOL", 0, False, 7

    def should_rebalance(self, min_days):
        """Check if enough days have passed since last rebalance."""
        if self.last_rebalance is None:
            return True
        days_since = (self.time - self.last_rebalance).days
        return days_since >= min_days

    def check_rebalance(self):
        if self.is_warming_up:
            return

        # Get VIX
        vix_value = 20
        if self.securities.contains_key(self.vix):
            vix_value = self.securities[self.vix].price

        regime, target_positions, include_growth, min_days = self.get_regime(vix_value)

        # Check if we need to rebalance
        # Force rebalance if regime changed to extreme
        force_rebalance = regime == "EXTREME_VOL" and self.portfolio.invested

        if not force_rebalance and not self.should_rebalance(min_days):
            return

        self.rebalance_portfolio(vix_value, regime, target_positions, include_growth)
        self.last_rebalance = self.time

    def rebalance_portfolio(self, vix_value, regime, target_positions, include_growth):
        # Market regime filter
        spy_price = self.securities[self.spy].price
        if not self.spy_sma_200.is_ready or spy_price < self.spy_sma_200.current.value:
            self.liquidate()
            self.debug(f"{self.time.date()}: Bear market - all cash")
            return

        # Extreme vol - go to cash
        if target_positions == 0:
            self.liquidate()
            self.debug(f"{self.time.date()}: VIX={vix_value:.1f} EXTREME - all cash")
            return

        # Calculate scores
        scores = []
        for ticker, info in self.tickers.items():
            symbol = self.symbols[ticker]

            # Skip growth stocks in high vol
            if not include_growth and not info["quality"]:
                continue

            if not self.securities[symbol].has_data:
                continue
            if not self.momp_ind[ticker].is_ready or not self.sma_50[ticker].is_ready:
                continue

            price = self.securities[symbol].price

            # Price > 50 SMA
            if price < self.sma_50[ticker].current.value:
                continue

            # Positive momentum
            mom = self.momp_ind[ticker].current.value
            if mom <= 0:
                continue

            scores.append({
                "ticker": ticker,
                "symbol": symbol,
                "sector": info["sector"],
                "quality": info["quality"],
                "momentum": mom
            })

        # Sort by momentum
        scores.sort(key=lambda x: x["momentum"], reverse=True)

        # Select with sector constraints
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
            if holding.invested and holding.symbol not in selected_symbols and holding.symbol != self.vix:
                self.liquidate(holding.symbol)

        # Allocate
        for s in selected:
            self.set_holdings(s["symbol"], weight)

        quality_count = sum(1 for s in selected if s["quality"])
        self.debug(f"{self.time.date()}: VIX={vix_value:.1f} ({regime}), {len(selected)} positions, {quality_count} quality")
