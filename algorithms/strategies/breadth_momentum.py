# region imports
from AlgorithmImports import *
# endregion

class BreadthMomentumStrategy(QCAlgorithm):
    """
    Round 9 Strategy 2: Breadth + Momentum

    Key insight: Market breadth (% of stocks above 200 SMA) is a leading indicator.
    When breadth is high (>60%), market is healthy - be aggressive.
    When breadth is low (<40%), risk is high - be defensive.

    Uses SPY constituents proxy via sector ETFs.
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Breadth proxy: Sector ETFs for breadth calculation
        self.sector_etfs = ["XLK", "XLY", "XLV", "XLF", "XLI", "XLC", "XLE", "XLB", "XLRE", "XLU", "XLP"]
        self.etf_symbols = {}
        self.etf_sma_200 = {}

        for etf in self.sector_etfs:
            equity = self.add_equity(etf, Resolution.DAILY)
            equity.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
            self.etf_symbols[etf] = equity.symbol
            self.etf_sma_200[etf] = self.sma(equity.symbol, 200, Resolution.DAILY)

        # Trading universe (same proven universe)
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
        self.spy = spy.symbol
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)

        # Monthly rebalance
        self.schedule.on(
            self.date_rules.month_start("SPY"),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )

        self.set_benchmark("SPY")
        self.set_warm_up(220, Resolution.DAILY)

    def calculate_breadth(self):
        """Calculate market breadth as % of sector ETFs above 200 SMA."""
        above_count = 0
        total_count = 0

        for etf in self.sector_etfs:
            if not self.etf_sma_200[etf].is_ready:
                continue
            if not self.securities[self.etf_symbols[etf]].has_data:
                continue

            total_count += 1
            price = self.securities[self.etf_symbols[etf]].price
            sma_val = self.etf_sma_200[etf].current.value

            if price > sma_val:
                above_count += 1

        if total_count == 0:
            return 0.5
        return above_count / total_count

    def get_allocation_from_breadth(self, breadth):
        """Determine allocation based on breadth."""
        if breadth >= 0.7:
            return 8, 1.0, "STRONG BREADTH"
        elif breadth >= 0.5:
            return 6, 0.9, "MODERATE BREADTH"
        elif breadth >= 0.35:
            return 4, 0.7, "WEAK BREADTH"
        else:
            return 3, 0.5, "POOR BREADTH"

    def rebalance(self):
        if self.is_warming_up:
            return

        # Market regime filter
        spy_price = self.securities[self.spy].price
        if not self.spy_sma_200.is_ready or spy_price < self.spy_sma_200.current.value:
            self.liquidate()
            self.debug(f"{self.time.date()}: Bear market - all cash")
            return

        # Calculate breadth
        breadth = self.calculate_breadth()
        target_positions, allocation_mult, breadth_desc = self.get_allocation_from_breadth(breadth)

        # Calculate momentum scores
        scores = []
        for ticker, sector in self.tickers.items():
            symbol = self.symbols[ticker]

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
                "sector": sector,
                "momentum": mom
            })

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

        # Weight based on breadth (more aggressive in strong breadth)
        total_weight = allocation_mult
        weight_per = total_weight / len(selected)

        # Liquidate old
        selected_symbols = {s["symbol"] for s in selected}
        for holding in self.portfolio.values():
            if holding.invested and holding.symbol not in selected_symbols:
                self.liquidate(holding.symbol)

        # Allocate
        for s in selected:
            self.set_holdings(s["symbol"], weight_per)

        self.debug(f"{self.time.date()}: Breadth={breadth:.0%} ({breadth_desc}), {len(selected)} positions @ {weight_per:.1%}")
