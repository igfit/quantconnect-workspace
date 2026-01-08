# region imports
from AlgorithmImports import *
# endregion

class MultiFactorRankStrategy(QCAlgorithm):
    """
    Round 9 Strategy 5: Multi-Factor Ranking

    Combines multiple factors into a composite score:
    1. Momentum (6-month ROC) - 50% weight
    2. Trend confirmation (price vs SMA) - 20% weight
    3. Volatility (lower = better for Sharpe) - 30% weight

    Key insight: Pure momentum can pick volatile stocks.
    Adding volatility factor should improve Sharpe ratio.
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
        self.sma_50 = {}
        self.std_ind = {}  # 30-day volatility

        for ticker in self.tickers.keys():
            equity = self.add_equity(ticker, Resolution.DAILY)
            equity.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
            sym = equity.symbol
            self.symbols[ticker] = sym

            self.momp_ind[ticker] = self.momp(sym, 126, Resolution.DAILY)
            self.sma_50[ticker] = self.sma(sym, 50, Resolution.DAILY)
            self.std_ind[ticker] = self.std(sym, 30, Resolution.DAILY)

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

    def calculate_factor_ranks(self, stocks):
        """
        Calculate factor scores and composite rank.

        Returns list of stocks with:
        - mom_rank: higher momentum = higher rank
        - trend_score: 1 if above SMA, 0 otherwise
        - vol_rank: lower volatility = higher rank
        - composite: weighted combination
        """
        n = len(stocks)
        if n == 0:
            return []

        # Sort by momentum (descending) for rank
        sorted_by_mom = sorted(stocks, key=lambda x: x["momentum"], reverse=True)
        for i, s in enumerate(sorted_by_mom):
            s["mom_rank"] = (n - i) / n  # 1.0 = best, 0 = worst

        # Sort by volatility (ascending) - lower vol is better
        sorted_by_vol = sorted(stocks, key=lambda x: x["volatility"])
        for i, s in enumerate(sorted_by_vol):
            s["vol_rank"] = (n - i) / n  # 1.0 = lowest vol

        # Calculate composite score
        # Weights: Momentum 50%, Trend 20%, Volatility 30%
        for s in stocks:
            s["composite"] = (
                s["mom_rank"] * 0.50 +
                s["trend_score"] * 0.20 +
                s["vol_rank"] * 0.30
            )

        return sorted(stocks, key=lambda x: x["composite"], reverse=True)

    def rebalance(self):
        if self.is_warming_up:
            return

        # Market regime filter
        spy_price = self.securities[self.spy].price
        if not self.spy_sma_200.is_ready or spy_price < self.spy_sma_200.current.value:
            self.liquidate()
            self.debug(f"{self.time.date()}: Bear market - all cash")
            return

        # Gather factor data
        stocks = []
        for ticker, sector in self.tickers.items():
            symbol = self.symbols[ticker]

            if not self.securities[symbol].has_data:
                continue
            if not self.momp_ind[ticker].is_ready:
                continue
            if not self.sma_50[ticker].is_ready:
                continue
            if not self.std_ind[ticker].is_ready:
                continue

            price = self.securities[symbol].price

            # Only positive momentum stocks
            mom = self.momp_ind[ticker].current.value
            if mom <= 0:
                continue

            # Trend confirmation score
            trend_score = 1.0 if price > self.sma_50[ticker].current.value else 0.0

            # Volatility (annualized)
            daily_std = self.std_ind[ticker].current.value
            ann_vol = daily_std * (252 ** 0.5) / price * 100  # as percentage

            stocks.append({
                "ticker": ticker,
                "symbol": symbol,
                "sector": sector,
                "momentum": mom,
                "trend_score": trend_score,
                "volatility": ann_vol
            })

        # Calculate composite rankings
        ranked_stocks = self.calculate_factor_ranks(stocks)

        # Select top 8 with sector constraints
        target_positions = 8
        selected = []
        sector_count = {}
        max_per_sector = 3

        for s in ranked_stocks:
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

        top3 = ", ".join([f"{s['ticker']}({s['composite']:.2f})" for s in selected[:3]])
        self.debug(f"{self.time.date()}: {len(selected)} positions. Top3: {top3}")
