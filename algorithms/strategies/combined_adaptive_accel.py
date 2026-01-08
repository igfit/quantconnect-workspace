# region imports
from AlgorithmImports import *
# endregion

class CombinedAdaptiveAccelMomentum(QCAlgorithm):
    """
    Round 9 Strategy 1: Combined Adaptive + Accelerating Momentum

    Combines best elements from Round 8:
    - AdaptivePositions: VIX-based position count (best Sharpe 0.967)
    - AccelMomSectors: Multi-lookback momentum (best diversification)

    Key improvements:
    - Adaptive position sizing based on VIX
    - Multi-lookback momentum for better timing
    - Sector diversification constraints
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # VIX for adaptive position sizing
        self.vix = self.add_data(CBOE, "VIX", Resolution.DAILY).symbol

        # Multi-sector universe (25 stocks across 5+ sectors)
        self.tickers = {
            # Tech (max 35%)
            "AAPL": "Tech", "MSFT": "Tech", "NVDA": "Tech", "GOOGL": "Tech",
            "META": "Tech", "AVGO": "Tech", "CRM": "Tech",
            # Consumer Discretionary
            "AMZN": "ConsDisc", "TSLA": "ConsDisc", "HD": "ConsDisc",
            "NKE": "ConsDisc", "DIS": "ConsDisc",
            # Healthcare
            "UNH": "Health", "LLY": "Health", "JNJ": "Health",
            "PFE": "Health", "ABBV": "Health",
            # Financials
            "JPM": "Finance", "GS": "Finance", "BLK": "Finance", "V": "Finance",
            # Industrials
            "CAT": "Industrial", "HON": "Industrial", "GE": "Industrial", "UPS": "Industrial",
            # Comm Services
            "NFLX": "Comm", "CMCSA": "Comm",
            # Consumer Staples
            "COST": "Staples", "PG": "Staples",
        }

        # Add equities and indicators
        self.symbols = {}
        self.roc_21 = {}   # 1-month momentum
        self.roc_63 = {}   # 3-month momentum
        self.roc_126 = {}  # 6-month momentum
        self.sma_50 = {}

        for ticker in self.tickers.keys():
            equity = self.add_equity(ticker, Resolution.DAILY)
            equity.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
            sym = equity.symbol
            self.symbols[ticker] = sym

            # Multi-lookback momentum
            self.roc_21[ticker] = self.roc(sym, 21, Resolution.DAILY)
            self.roc_63[ticker] = self.roc(sym, 63, Resolution.DAILY)
            self.roc_126[ticker] = self.roc(sym, 126, Resolution.DAILY)
            self.sma_50[ticker] = self.sma(sym, 50, Resolution.DAILY)

        # SPY for regime filter
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

    def get_target_positions(self, vix_value):
        """Determine number of positions based on VIX."""
        if vix_value < 18:
            return 5, "VERY LOW VIX"
        elif vix_value < 22:
            return 7, "LOW VIX"
        elif vix_value < 28:
            return 9, "MEDIUM VIX"
        else:
            return 11, "HIGH VIX"

    def calculate_accel_momentum(self, ticker):
        """Calculate accelerating momentum as weighted average of lookbacks."""
        if not (self.roc_21[ticker].is_ready and
                self.roc_63[ticker].is_ready and
                self.roc_126[ticker].is_ready):
            return None

        roc1 = self.roc_21[ticker].current.value
        roc3 = self.roc_63[ticker].current.value
        roc6 = self.roc_126[ticker].current.value

        # Weight recent momentum more heavily (50/30/20)
        return (roc1 * 0.50 + roc3 * 0.30 + roc6 * 0.20)

    def rebalance(self):
        if self.is_warming_up:
            return

        # Market regime filter
        spy_price = self.securities[self.spy].price
        if not self.spy_sma_200.is_ready or spy_price < self.spy_sma_200.current.value:
            self.liquidate()
            self.debug(f"{self.time.date()}: Bear market - all cash")
            return

        # Get VIX for position count
        vix_value = 20  # default
        if self.securities.contains_key(self.vix):
            vix_value = self.securities[self.vix].price

        target_positions, regime = self.get_target_positions(vix_value)

        # Calculate momentum scores
        scores = []
        for ticker, sector in self.tickers.items():
            symbol = self.symbols[ticker]

            if not self.securities[symbol].has_data:
                continue
            if not self.sma_50[ticker].is_ready:
                continue

            price = self.securities[symbol].price

            # Price > 50 SMA filter
            if price < self.sma_50[ticker].current.value:
                continue

            # Positive momentum filter
            accel_mom = self.calculate_accel_momentum(ticker)
            if accel_mom is None or accel_mom <= 0:
                continue

            scores.append({
                "ticker": ticker,
                "symbol": symbol,
                "sector": sector,
                "momentum": accel_mom
            })

        # Sort by momentum
        scores.sort(key=lambda x: x["momentum"], reverse=True)

        # Select top positions with sector constraints
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

        # Equal weight among selected
        weight = 1.0 / len(selected)

        # Liquidate positions not in selection
        selected_symbols = {s["symbol"] for s in selected}
        for holding in self.portfolio.values():
            if holding.invested and holding.symbol not in selected_symbols and holding.symbol != self.vix:
                self.liquidate(holding.symbol)

        # Allocate
        for s in selected:
            self.set_holdings(s["symbol"], weight)

        self.debug(f"{self.time.date()}: VIX={vix_value:.1f} ({regime}), {len(selected)} positions")
