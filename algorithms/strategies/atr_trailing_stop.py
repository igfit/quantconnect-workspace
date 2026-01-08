# region imports
from AlgorithmImports import *
# endregion

class ATRTrailingStopStrategy(QCAlgorithm):
    """
    Round 10 Strategy 2: ADX Entry + ATR Trailing Stop

    Key idea: Use ATR-based trailing stops for drawdown control.
    - Entry: Same as TrendStrengthMom (ADX > 20, +DI > -DI)
    - Exit: Price drops below (High - 2*ATR) trailing stop

    Hypothesis: Trailing stops lock in profits and limit drawdowns.
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
        self.atr_ind = {}
        self.trailing_stops = {}  # Track trailing stop levels
        self.highest_since_entry = {}  # Track highest price since entry

        for ticker in self.tickers.keys():
            equity = self.add_equity(ticker, Resolution.DAILY)
            equity.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
            sym = equity.symbol
            self.symbols[ticker] = sym

            self.momp_ind[ticker] = self.momp(sym, 126, Resolution.DAILY)
            self.adx_ind[ticker] = self.adx(sym, 14, Resolution.DAILY)
            self.atr_ind[ticker] = self.atr(sym, 14, MovingAverageType.SIMPLE, Resolution.DAILY)

        # SPY for regime
        spy = self.add_equity("SPY", Resolution.DAILY)
        spy.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
        self.spy = spy.symbol
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)

        # Monthly rebalance for entries
        self.schedule.on(
            self.date_rules.month_start("SPY"),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )

        # Daily trailing stop check
        self.schedule.on(
            self.date_rules.every_day("SPY"),
            self.time_rules.after_market_open("SPY", 31),
            self.check_trailing_stops
        )

        self.set_benchmark("SPY")
        self.set_warm_up(150, Resolution.DAILY)

    def check_trailing_stops(self):
        """Daily check and update trailing stops."""
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

            price = self.securities[holding.symbol].price
            atr_val = self.atr_ind[ticker].current.value if self.atr_ind[ticker].is_ready else 0

            if atr_val == 0:
                continue

            # Update highest price since entry
            if ticker not in self.highest_since_entry:
                self.highest_since_entry[ticker] = price
            else:
                self.highest_since_entry[ticker] = max(self.highest_since_entry[ticker], price)

            # Calculate trailing stop: highest - 2*ATR
            new_stop = self.highest_since_entry[ticker] - (2.0 * atr_val)

            # Only move stop up, never down
            if ticker not in self.trailing_stops:
                self.trailing_stops[ticker] = new_stop
            else:
                self.trailing_stops[ticker] = max(self.trailing_stops[ticker], new_stop)

            # Check if price hit trailing stop
            if price < self.trailing_stops[ticker]:
                self.liquidate(holding.symbol)
                self.debug(f"{self.time.date()}: TRAILING STOP {ticker} @ {price:.2f} (stop={self.trailing_stops[ticker]:.2f})")
                # Clear tracking
                if ticker in self.trailing_stops:
                    del self.trailing_stops[ticker]
                if ticker in self.highest_since_entry:
                    del self.highest_since_entry[ticker]

    def rebalance(self):
        if self.is_warming_up:
            return

        # Market regime filter
        spy_price = self.securities[self.spy].price
        if not self.spy_sma_200.is_ready or spy_price < self.spy_sma_200.current.value:
            self.liquidate()
            self.trailing_stops.clear()
            self.highest_since_entry.clear()
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

            # ADX filter - strong trend only
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
            self.trailing_stops.clear()
            self.highest_since_entry.clear()
            return

        # Equal weight
        weight = 1.0 / len(selected)

        # Liquidate old positions
        selected_symbols = {s["symbol"] for s in selected}
        for holding in self.portfolio.values():
            if holding.invested and holding.symbol not in selected_symbols:
                self.liquidate(holding.symbol)
                # Clear tracking for liquidated positions
                for t, sym in self.symbols.items():
                    if sym == holding.symbol:
                        if t in self.trailing_stops:
                            del self.trailing_stops[t]
                        if t in self.highest_since_entry:
                            del self.highest_since_entry[t]
                        break

        # Allocate new positions
        for s in selected:
            ticker = s["ticker"]
            symbol = s["symbol"]

            # Initialize tracking for new positions
            if not self.portfolio[symbol].invested:
                price = self.securities[symbol].price
                atr_val = self.atr_ind[ticker].current.value if self.atr_ind[ticker].is_ready else price * 0.03
                self.highest_since_entry[ticker] = price
                self.trailing_stops[ticker] = price - (2.0 * atr_val)

            self.set_holdings(symbol, weight)

        top3 = ", ".join([f"{s['ticker']}({s['score']:.1f})" for s in selected[:3]])
        self.debug(f"{self.time.date()}: {len(selected)} positions. Top3: {top3}")
