# region imports
from AlgorithmImports import *
# endregion

class SectorETFRotationStrategy(QCAlgorithm):
    """
    Round 11 Strategy 1: Sector ETF Rotation

    Key idea: Use sector ETFs instead of individual stocks.
    - No single stock can dominate (XLK includes AAPL, MSFT, NVDA, etc.)
    - Alpha must come from timing sector entry/exit, not stock selection
    - Same ADX filter for trending sectors

    Universe: 11 sector ETFs
    Entry: ADX > 20, +DI > -DI, positive momentum
    Exit: ADX < 15 OR -DI > +DI
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Sector ETFs
        self.sectors = {
            "XLK": "Technology",
            "XLF": "Financials",
            "XLV": "Healthcare",
            "XLY": "ConsumerDisc",
            "XLP": "ConsumerStaples",
            "XLI": "Industrials",
            "XLE": "Energy",
            "XLU": "Utilities",
            "XLB": "Materials",
            "XLRE": "RealEstate",
            "XLC": "Communication"
        }

        self.symbols = {}
        self.momp_ind = {}
        self.adx_ind = {}

        for ticker in self.sectors.keys():
            equity = self.add_equity(ticker, Resolution.DAILY)
            equity.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
            sym = equity.symbol
            self.symbols[ticker] = sym

            self.momp_ind[ticker] = self.momp(sym, 63, Resolution.DAILY)  # 3-month momentum
            self.adx_ind[ticker] = self.adx(sym, 14, Resolution.DAILY)

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
        self.set_warm_up(100, Resolution.DAILY)

    def rebalance(self):
        if self.is_warming_up:
            return

        # Market regime filter
        spy_price = self.securities[self.spy].price
        if not self.spy_sma_200.is_ready or spy_price < self.spy_sma_200.current.value:
            self.liquidate()
            self.debug(f"{self.time.date()}: Bear market - all cash")
            return

        # Score sectors
        scores = []
        for ticker in self.sectors.keys():
            symbol = self.symbols[ticker]

            if not self.securities[symbol].has_data:
                continue
            if not self.momp_ind[ticker].is_ready:
                continue
            if not self.adx_ind[ticker].is_ready:
                continue

            # ADX filter
            adx_val = self.adx_ind[ticker].current.value
            positive_di = self.adx_ind[ticker].positive_directional_index.current.value
            negative_di = self.adx_ind[ticker].negative_directional_index.current.value

            if adx_val < 20:
                continue
            if positive_di <= negative_di:
                continue

            # Positive momentum
            mom = self.momp_ind[ticker].current.value
            if mom <= 0:
                continue

            # Score
            trend_strength = (adx_val / 100) * (positive_di / (positive_di + negative_di + 0.001))
            score = mom * (1 + trend_strength)

            scores.append({
                "ticker": ticker,
                "symbol": symbol,
                "score": score
            })

        # Sort by score
        scores.sort(key=lambda x: x["score"], reverse=True)

        # Select top 5 sectors (more diversified)
        selected = scores[:5]

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

        tickers = ", ".join([s["ticker"] for s in selected])
        self.debug(f"{self.time.date()}: Sectors: {tickers}")
