# region imports
from AlgorithmImports import *
# endregion

class RelativeStrengthR13(QCAlgorithm):
    """
    Round 13 Strategy 2: Relative Strength (vs Sector)

    SIGNAL ALPHA via relative outperformance, not absolute gains.

    Thesis:
    - Buy stocks outperforming their sector ETF
    - This rotates more than absolute momentum
    - A stock can outperform even if sector is down
    - Different leaders emerge in different market conditions

    Rules:
    - Compare each stock's 20-day return to its sector ETF
    - Buy top 8 with highest relative strength
    - Sector cap of 2 positions
    - Weekly rebalance
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Stocks mapped to sector ETFs
        self.stock_sectors = {
            # Tech -> XLK
            "AAPL": "XLK", "MSFT": "XLK", "NVDA": "XLK", "AVGO": "XLK",
            "CRM": "XLK", "AMD": "XLK",
            # Consumer Discretionary -> XLY
            "AMZN": "XLY", "TSLA": "XLY", "HD": "XLY", "NKE": "XLY",
            # Healthcare -> XLV
            "UNH": "XLV", "LLY": "XLV", "ABBV": "XLV", "JNJ": "XLV",
            # Financials -> XLF
            "JPM": "XLF", "GS": "XLF", "BLK": "XLF", "V": "XLF",
            # Industrials -> XLI
            "CAT": "XLI", "HON": "XLI", "GE": "XLI", "UPS": "XLI",
            # Communication -> XLC
            "GOOGL": "XLC", "META": "XLC", "NFLX": "XLC", "DIS": "XLC",
            # Staples -> XLP
            "COST": "XLP", "PG": "XLP",
        }

        self.sector_etfs = ["XLK", "XLY", "XLV", "XLF", "XLI", "XLC", "XLP"]

        self.symbols = {}
        self.sector_symbols = {}
        self.stock_roc = {}  # 20-day rate of change
        self.sector_roc = {}

        # Add sector ETFs
        for etf in self.sector_etfs:
            equity = self.add_equity(etf, Resolution.DAILY)
            equity.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
            self.sector_symbols[etf] = equity.symbol
            self.sector_roc[etf] = self.rocp(equity.symbol, 20, Resolution.DAILY)

        # Add stocks
        for ticker, sector in self.stock_sectors.items():
            equity = self.add_equity(ticker, Resolution.DAILY)
            equity.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
            self.symbols[ticker] = equity.symbol
            self.stock_roc[ticker] = self.rocp(equity.symbol, 20, Resolution.DAILY)

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

        self.set_benchmark("SPY")
        self.set_warm_up(50, Resolution.DAILY)

    def rebalance(self):
        """Weekly rebalance based on relative strength."""
        if self.is_warming_up:
            return

        # Market regime filter
        spy_price = self.securities[self.spy].price
        if not self.spy_sma_200.is_ready or spy_price < self.spy_sma_200.current.value:
            self.liquidate()
            self.debug(f"{self.time.date()}: Bear regime - cash")
            return

        # Calculate relative strength for each stock
        scores = []
        for ticker, sector_etf in self.stock_sectors.items():
            symbol = self.symbols[ticker]

            if not self.stock_roc[ticker].is_ready:
                continue
            if not self.sector_roc[sector_etf].is_ready:
                continue

            stock_return = self.stock_roc[ticker].current.value
            sector_return = self.sector_roc[sector_etf].current.value

            # Relative strength = stock return - sector return
            rel_strength = stock_return - sector_return

            # Only consider stocks outperforming their sector
            if rel_strength > 0:
                scores.append({
                    "ticker": ticker,
                    "symbol": symbol,
                    "sector": sector_etf,
                    "rel_strength": rel_strength,
                    "stock_return": stock_return,
                    "sector_return": sector_return
                })

        scores.sort(key=lambda x: x["rel_strength"], reverse=True)

        # Select top 8 with sector cap of 2
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
        for ticker in self.stock_sectors.keys():
            symbol = self.symbols[ticker]
            if symbol not in selected_symbols and self.portfolio[symbol].invested:
                self.liquidate(symbol)

        # Equal weight
        weight = 1.0 / len(selected)

        for s in selected:
            self.set_holdings(s["symbol"], weight)

        tickers = ", ".join([f"{s['ticker']}(+{s['rel_strength']:.1%})" for s in selected])
        self.debug(f"{self.time.date()}: REL_STR: {tickers}")
