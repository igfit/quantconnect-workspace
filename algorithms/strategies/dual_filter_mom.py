# region imports
from AlgorithmImports import *
# endregion

class DualFilterMomStrategy(QCAlgorithm):
    """
    Round 10 Strategy 5: Dual Filter Momentum (ADX + RSI)

    Key idea: Use BOTH ADX and RSI for entry AND exit filtering.
    - Entry: ADX > 20, +DI > -DI, RSI 40-70 (not overbought)
    - Exit: ADX < 15 (no trend) OR RSI > 75 (overbought) OR RSI < 30 (oversold)

    Hypothesis: Dual confirmation reduces false signals, improves timing.
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
        self.momp_ind = {}
        self.adx_ind = {}
        self.rsi_ind = {}

        for ticker in self.tickers.keys():
            equity = self.add_equity(ticker, Resolution.DAILY)
            equity.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
            sym = equity.symbol
            self.symbols[ticker] = sym

            self.momp_ind[ticker] = self.momp(sym, 126, Resolution.DAILY)
            self.adx_ind[ticker] = self.adx(sym, 14, Resolution.DAILY)
            self.rsi_ind[ticker] = self.rsi(sym, 14, MovingAverageType.WILDERS, Resolution.DAILY)

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

        # Daily exit checks
        self.schedule.on(
            self.date_rules.every_day("SPY"),
            self.time_rules.after_market_open("SPY", 31),
            self.check_exits
        )

        self.set_benchmark("SPY")
        self.set_warm_up(150, Resolution.DAILY)

    def check_exits(self):
        """Daily check for ADX/RSI-based exits."""
        if self.is_warming_up:
            return

        for holding in self.portfolio.values():
            if not holding.invested or holding.symbol == self.spy:
                continue

            # Find ticker
            ticker = None
            for t, s in self.symbols.items():
                if s == holding.symbol:
                    ticker = t
                    break

            if ticker is None:
                continue

            if not self.adx_ind[ticker].is_ready or not self.rsi_ind[ticker].is_ready:
                continue

            adx_val = self.adx_ind[ticker].current.value
            positive_di = self.adx_ind[ticker].positive_directional_index.current.value
            negative_di = self.adx_ind[ticker].negative_directional_index.current.value
            rsi_val = self.rsi_ind[ticker].current.value

            should_exit = False
            exit_reason = ""

            # Exit conditions:
            # 1. Trend died (ADX < 15)
            if adx_val < 15:
                should_exit = True
                exit_reason = f"ADX_LOW({adx_val:.1f})"

            # 2. Trend reversed (-DI > +DI)
            elif negative_di > positive_di:
                should_exit = True
                exit_reason = f"TREND_REV"

            # 3. Overbought (RSI > 75) - take profits
            elif rsi_val > 75:
                should_exit = True
                exit_reason = f"OVERBOUGHT({rsi_val:.1f})"

            # 4. Oversold (RSI < 30) - momentum collapsed
            elif rsi_val < 30:
                should_exit = True
                exit_reason = f"OVERSOLD({rsi_val:.1f})"

            if should_exit:
                self.liquidate(holding.symbol)
                self.debug(f"{self.time.date()}: EXIT {ticker} - {exit_reason}")

    def rebalance(self):
        if self.is_warming_up:
            return

        # Market regime filter
        spy_price = self.securities[self.spy].price
        if not self.spy_sma_200.is_ready or spy_price < self.spy_sma_200.current.value:
            self.liquidate()
            self.debug(f"{self.time.date()}: Bear market - all cash")
            return

        # Calculate scores with dual ADX + RSI filter
        scores = []
        for ticker, sector in self.tickers.items():
            symbol = self.symbols[ticker]

            if not self.securities[symbol].has_data:
                continue
            if not self.momp_ind[ticker].is_ready:
                continue
            if not self.adx_ind[ticker].is_ready:
                continue
            if not self.rsi_ind[ticker].is_ready:
                continue

            # ADX filter
            adx_val = self.adx_ind[ticker].current.value
            positive_di = self.adx_ind[ticker].positive_directional_index.current.value
            negative_di = self.adx_ind[ticker].negative_directional_index.current.value

            if adx_val < 20:
                continue
            if positive_di <= negative_di:
                continue

            # RSI filter - not overbought on entry
            rsi_val = self.rsi_ind[ticker].current.value
            if rsi_val > 70:  # Don't enter overbought
                continue
            if rsi_val < 40:  # Don't enter if no momentum
                continue

            # Positive momentum
            mom = self.momp_ind[ticker].current.value
            if mom <= 0:
                continue

            # Composite score: momentum * trend_strength * RSI_quality
            trend_strength = (adx_val / 100) * (positive_di / (positive_di + negative_di + 0.001))
            # RSI quality: best around 50-60 (room to run)
            rsi_quality = 1.0 - abs(rsi_val - 55) / 55
            score = mom * (1 + trend_strength) * (1 + rsi_quality * 0.3)

            scores.append({
                "ticker": ticker,
                "symbol": symbol,
                "sector": sector,
                "score": score,
                "adx": adx_val,
                "rsi": rsi_val
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

        top3 = ", ".join([f"{s['ticker']}(ADX={s['adx']:.0f},RSI={s['rsi']:.0f})" for s in selected[:3]])
        self.debug(f"{self.time.date()}: {len(selected)} positions. Top3: {top3}")
