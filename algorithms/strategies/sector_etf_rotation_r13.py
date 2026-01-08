# region imports
from AlgorithmImports import *
# endregion

class SectorETFRotationR13(QCAlgorithm):
    """
    Round 13 Strategy 1: Sector ETF Rotation

    SIGNAL ALPHA via sector timing, not stock picking.

    Thesis:
    - Rotate between sector ETFs based on momentum
    - No single-stock concentration possible
    - Alpha comes from sector timing decisions

    Rules:
    - Universe: 11 sector ETFs (SPDRs)
    - Weekly rotation to top 3 momentum sectors
    - Equal weight allocation
    - Market regime filter (SPY > 200 SMA)
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Sector ETFs (SPDR sectors)
        self.sectors = {
            "XLK": "Technology",
            "XLF": "Financials",
            "XLE": "Energy",
            "XLV": "Healthcare",
            "XLI": "Industrials",
            "XLY": "Consumer Discretionary",
            "XLP": "Consumer Staples",
            "XLU": "Utilities",
            "XLB": "Materials",
            "XLRE": "Real Estate",
            "XLC": "Communication Services",
        }

        self.symbols = {}
        self.mom_20d = {}  # 20-day momentum (1 month)
        self.mom_60d = {}  # 60-day momentum (3 months)

        for ticker in self.sectors.keys():
            equity = self.add_equity(ticker, Resolution.DAILY)
            equity.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
            sym = equity.symbol
            self.symbols[ticker] = sym

            self.mom_20d[ticker] = self.momp(sym, 20, Resolution.DAILY)
            self.mom_60d[ticker] = self.momp(sym, 60, Resolution.DAILY)

        # Market regime
        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma_100 = self.sma(self.spy, 100, Resolution.DAILY)  # Shorter SMA

        # Weekly rotation on Monday
        self.schedule.on(
            self.date_rules.every([DayOfWeek.MONDAY]),
            self.time_rules.after_market_open("SPY", 30),
            self.rotate_sectors
        )

        self.set_benchmark("SPY")
        self.set_warm_up(70, Resolution.DAILY)  # Reduced from 200

    def rotate_sectors(self):
        """Weekly sector rotation."""
        if self.is_warming_up:
            return

        # Market regime filter
        spy_price = self.securities[self.spy].price
        if not self.spy_sma_100.is_ready or spy_price < self.spy_sma_100.current.value:
            self.liquidate()
            self.debug(f"{self.time.date()}: Bear regime - cash")
            return

        # Score sectors by combined momentum
        scores = []
        for ticker, sector_name in self.sectors.items():
            symbol = self.symbols[ticker]

            if not self.mom_20d[ticker].is_ready:
                continue
            if not self.mom_60d[ticker].is_ready:
                continue

            mom_short = self.mom_20d[ticker].current.value
            mom_long = self.mom_60d[ticker].current.value

            # Combined score: short-term + long-term momentum
            # Favor sectors with both recent AND sustained momentum
            score = mom_short * 0.6 + mom_long * 0.4

            if score > 0:  # Only positive momentum
                scores.append({
                    "ticker": ticker,
                    "symbol": symbol,
                    "sector": sector_name,
                    "score": score,
                    "mom_20d": mom_short,
                    "mom_60d": mom_long
                })

        scores.sort(key=lambda x: x["score"], reverse=True)

        # Select top 3 sectors
        selected = scores[:3]

        if not selected:
            self.liquidate()
            return

        # Liquidate sectors not in top 3
        current_holdings = [s.ticker for s in self.portfolio.keys() if self.portfolio[s].invested]
        selected_tickers = [s["ticker"] for s in selected]

        for ticker in self.sectors.keys():
            if ticker not in selected_tickers:
                symbol = self.symbols[ticker]
                if self.portfolio[symbol].invested:
                    self.liquidate(symbol)

        # Equal weight top 3
        weight = 1.0 / len(selected)

        for s in selected:
            self.set_holdings(s["symbol"], weight)

        tickers = ", ".join([f"{s['ticker']}({s['sector'][:4]})" for s in selected])
        self.debug(f"{self.time.date()}: SECTORS: {tickers}")
