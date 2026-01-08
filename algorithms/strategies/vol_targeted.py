# region imports
from AlgorithmImports import *
# endregion

class VolTargetedStrategy(QCAlgorithm):
    """
    Round 10 Strategy 4: Volatility-Targeted Position Sizing

    Key idea: Scale positions inversely to volatility to maintain constant risk.
    - High volatility stock = smaller position
    - Low volatility stock = larger position
    - Target: ~15% annualized portfolio volatility

    Hypothesis: Reduces drawdowns by cutting exposure during volatile periods.
    Based on academic research showing vol-targeting improves Sharpe.
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.target_vol = 0.15  # 15% annualized volatility target

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
        self.std_ind = {}  # For volatility calculation

        for ticker in self.tickers.keys():
            equity = self.add_equity(ticker, Resolution.DAILY)
            equity.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
            sym = equity.symbol
            self.symbols[ticker] = sym

            self.momp_ind[ticker] = self.momp(sym, 126, Resolution.DAILY)
            self.adx_ind[ticker] = self.adx(sym, 14, Resolution.DAILY)
            self.std_ind[ticker] = self.std(sym, 20, Resolution.DAILY)  # 20-day volatility

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

    def calculate_vol_weights(self, selected):
        """
        Calculate position weights based on inverse volatility.
        Target constant portfolio volatility.
        """
        if not selected:
            return {}

        # Calculate annualized volatility for each stock
        vols = {}
        for s in selected:
            ticker = s["ticker"]
            price = self.securities[s["symbol"]].price
            daily_std = self.std_ind[ticker].current.value
            # Annualized volatility as percentage
            ann_vol = (daily_std / price) * (252 ** 0.5) if price > 0 else 0.30
            ann_vol = max(ann_vol, 0.10)  # Floor at 10% vol
            vols[ticker] = ann_vol

        # Inverse volatility weights
        inv_vols = {t: 1.0 / v for t, v in vols.items()}
        total_inv_vol = sum(inv_vols.values())

        # Normalize to sum to 1
        raw_weights = {t: iv / total_inv_vol for t, iv in inv_vols.items()}

        # Scale to target portfolio volatility
        # Simple approximation: avg_vol * sqrt(n) for n equal positions
        avg_vol = sum(vols.values()) / len(vols)
        n_positions = len(selected)

        # Portfolio vol ~= avg_stock_vol / sqrt(n) for uncorrelated
        # Assume correlation ~0.3 for stocks in same market
        correlation = 0.3
        portfolio_vol = avg_vol * ((1 + correlation * (n_positions - 1)) / n_positions) ** 0.5

        # Scale factor to hit target vol
        scale = self.target_vol / portfolio_vol if portfolio_vol > 0 else 1.0
        scale = min(scale, 1.5)  # Cap at 150% exposure
        scale = max(scale, 0.3)  # Floor at 30% exposure

        # Final weights
        weights = {t: w * scale for t, w in raw_weights.items()}

        return weights

    def rebalance(self):
        if self.is_warming_up:
            return

        # Market regime filter
        spy_price = self.securities[self.spy].price
        if not self.spy_sma_200.is_ready or spy_price < self.spy_sma_200.current.value:
            self.liquidate()
            self.debug(f"{self.time.date()}: Bear market - all cash")
            return

        # Calculate scores with ADX filter
        scores = []
        for ticker, sector in self.tickers.items():
            symbol = self.symbols[ticker]

            if not self.securities[symbol].has_data:
                continue
            if not self.momp_ind[ticker].is_ready:
                continue
            if not self.adx_ind[ticker].is_ready:
                continue
            if not self.std_ind[ticker].is_ready:
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

            # Composite score
            trend_strength = (adx_val / 100) * (positive_di / (positive_di + negative_di + 0.001))
            score = mom * (1 + trend_strength)

            scores.append({
                "ticker": ticker,
                "symbol": symbol,
                "sector": sector,
                "score": score
            })

        # Sort by score
        scores.sort(key=lambda x: x["score"], reverse=True)

        # Select top 10 with sector constraints (more positions for diversification)
        target_positions = 10
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

        # Calculate volatility-targeted weights
        weights = self.calculate_vol_weights(selected)

        # Liquidate old
        selected_symbols = {s["symbol"] for s in selected}
        for holding in self.portfolio.values():
            if holding.invested and holding.symbol not in selected_symbols:
                self.liquidate(holding.symbol)

        # Allocate with vol-targeted weights
        total_weight = sum(weights.values())
        for s in selected:
            ticker = s["ticker"]
            weight = weights.get(ticker, 0.1)
            self.set_holdings(s["symbol"], weight)

        top3 = ", ".join([f"{s['ticker']}({weights[s['ticker']]:.1%})" for s in selected[:3]])
        self.debug(f"{self.time.date()}: {len(selected)} positions, total={total_weight:.1%}. Top3: {top3}")
