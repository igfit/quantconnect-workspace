# region imports
from AlgorithmImports import *
# endregion

class SmallCapLowDDV3(QCAlgorithm):
    """
    Round 18 DD Reduction V3: Sector Diversification + Cash Buffer

    Changes from ResidualSmallCapR18:
    1. Sector-based position limits (max 2 per sector)
    2. Always hold 20% cash buffer
    3. Tighter VIX filter with graduated response
    4. Max 3 positions total (was 5)
    5. Faster exit on momentum loss
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.lookback = 42
        self.beta_lookback = 126

        # Small/Mid-Cap High-Beta Universe with Sector Tags
        self.ticker_sectors = {
            # Fintech
            "SOFI": "fintech", "UPST": "fintech", "AFRM": "fintech",
            "HOOD": "fintech", "BILL": "fintech",
            # EV / Clean Energy
            "RIVN": "ev", "LCID": "ev", "PLUG": "ev",
            "FCEL": "ev", "CHPT": "ev",
            # Crypto-adjacent
            "RIOT": "crypto", "MARA": "crypto", "COIN": "crypto",
            # Gaming / Entertainment
            "DKNG": "gaming", "RBLX": "gaming", "U": "gaming",
            # Cloud / SaaS
            "NET": "cloud", "DDOG": "cloud", "MDB": "cloud",
            "CRWD": "cloud", "ZS": "cloud", "GTLB": "cloud",
            # Data / AI
            "PLTR": "ai", "PATH": "ai", "SNOW": "ai",
        }

        self.tickers = list(self.ticker_sectors.keys())

        self.symbols = {}
        self.return_history = {}
        self.adx_ind = {}
        self.entry_prices = {}
        self.highest_prices = {}
        self.position_sectors = {}  # Track sector of each position

        for ticker in self.tickers:
            try:
                equity = self.add_equity(ticker, Resolution.DAILY)
                equity.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
                sym = equity.symbol
                self.symbols[ticker] = sym
                self.return_history[ticker] = []
                self.adx_ind[ticker] = self.adx(sym, 14, Resolution.DAILY)
            except:
                self.debug(f"Could not add {ticker}")

        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)
        self.spy_returns = []

        vix = self.add_data(CBOE, "VIX", Resolution.DAILY)
        self.vix = vix.symbol

        # DD Reduction parameters
        self.max_positions = 3           # Fewer positions
        self.max_per_sector = 1          # Max 1 per sector for diversification
        self.cash_buffer = 0.20          # Always hold 20% cash
        self.prev_prices = {}

        self.schedule.on(
            self.date_rules.every([DayOfWeek.MONDAY]),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )

        self.schedule.on(
            self.date_rules.every_day("SPY"),
            self.time_rules.after_market_open("SPY", 31),
            self.check_exits
        )

        self.set_benchmark("SPY")
        self.set_warm_up(200, Resolution.DAILY)

    def get_vix(self):
        if self.vix in self.securities and self.securities[self.vix].price > 0:
            return self.securities[self.vix].price
        return 20

    def get_vix_position_scale(self):
        """Graduated VIX response for position sizing"""
        vix = self.get_vix()
        if vix < 15:
            return 1.0
        elif vix < 20:
            return 0.9
        elif vix < 25:
            return 0.7
        elif vix < 30:
            return 0.5
        else:
            return 0.0  # No new positions

    def on_data(self, data):
        if self.is_warming_up:
            return

        if self.spy in data and data[self.spy] is not None:
            spy_price = data[self.spy].close
            if self.spy in self.prev_prices:
                spy_ret = (spy_price - self.prev_prices[self.spy]) / self.prev_prices[self.spy]
                self.spy_returns.append(spy_ret)
                if len(self.spy_returns) > 300:
                    self.spy_returns = self.spy_returns[-300:]
            self.prev_prices[self.spy] = spy_price

        for ticker in self.symbols.keys():
            symbol = self.symbols[ticker]
            if symbol in data and data[symbol] is not None:
                price = data[symbol].close
                if symbol in self.prev_prices:
                    ret = (price - self.prev_prices[symbol]) / self.prev_prices[symbol]
                    self.return_history[ticker].append(ret)
                    if len(self.return_history[ticker]) > 300:
                        self.return_history[ticker] = self.return_history[ticker][-300:]
                self.prev_prices[symbol] = price

    def calculate_beta(self, stock_returns, market_returns):
        if len(stock_returns) < 60 or len(market_returns) < 60:
            return 1.5

        n = min(len(stock_returns), len(market_returns), self.beta_lookback)
        stock = stock_returns[-n:]
        market = market_returns[-n:]

        mean_stock = sum(stock) / len(stock)
        mean_market = sum(market) / len(market)

        cov = sum((s - mean_stock) * (m - mean_market) for s, m in zip(stock, market)) / len(stock)
        var_market = sum((m - mean_market) ** 2 for m in market) / len(market)

        if var_market == 0:
            return 1.5
        return cov / var_market

    def calculate_residual_momentum(self, ticker):
        if ticker not in self.return_history:
            return None
        stock_rets = self.return_history[ticker]
        if len(stock_rets) < self.lookback or len(self.spy_returns) < self.lookback:
            return None

        beta = self.calculate_beta(stock_rets, self.spy_returns)

        residuals = []
        n = min(len(stock_rets), len(self.spy_returns), self.lookback)
        for i in range(-n, 0):
            residual = stock_rets[i] - beta * self.spy_returns[i]
            residuals.append(residual)

        return sum(residuals), beta

    def get_sector_counts(self):
        """Count positions per sector"""
        counts = {}
        for ticker in self.entry_prices:
            sector = self.ticker_sectors.get(ticker, "other")
            counts[sector] = counts.get(sector, 0) + 1
        return counts

    def check_exits(self):
        if self.is_warming_up:
            return

        for ticker in list(self.entry_prices.keys()):
            if ticker not in self.symbols:
                continue
            symbol = self.symbols[ticker]
            if not self.portfolio[symbol].invested:
                self._cleanup(ticker)
                continue

            price = self.securities[symbol].price
            entry = self.entry_prices[ticker]
            pnl = (price - entry) / entry

            if ticker not in self.highest_prices:
                self.highest_prices[ticker] = price
            self.highest_prices[ticker] = max(self.highest_prices[ticker], price)

            should_exit = False
            reason = ""

            # Stop loss at 8%
            if pnl <= -0.08:
                should_exit = True
                reason = f"STOP({pnl:.1%})"

            # Trailing stop after 10% gain
            if pnl >= 0.10:
                drawdown = (price - self.highest_prices[ticker]) / self.highest_prices[ticker]
                if drawdown < -0.10:
                    should_exit = True
                    reason = f"TRAIL({pnl:+.1%})"

            # Quick exit: Momentum reversal (residual turns negative)
            result = self.calculate_residual_momentum(ticker)
            if result is not None:
                residual_mom, _ = result
                if residual_mom < -0.02:  # Momentum turned negative
                    should_exit = True
                    reason = f"MOM_REV({pnl:+.1%})"

            # ADX trend reversal
            if ticker in self.adx_ind and self.adx_ind[ticker].is_ready:
                neg_di = self.adx_ind[ticker].negative_directional_index.current.value
                pos_di = self.adx_ind[ticker].positive_directional_index.current.value
                if neg_di > pos_di + 8:  # Tighter threshold
                    should_exit = True
                    reason = f"TREND_REV({pnl:+.1%})"

            if should_exit:
                self.liquidate(symbol)
                self.debug(f"{self.time.date()}: EXIT {ticker} {reason}")
                self._cleanup(ticker)

    def _cleanup(self, ticker):
        if ticker in self.entry_prices:
            del self.entry_prices[ticker]
        if ticker in self.highest_prices:
            del self.highest_prices[ticker]
        if ticker in self.position_sectors:
            del self.position_sectors[ticker]

    def rebalance(self):
        if self.is_warming_up:
            return

        spy_price = self.securities[self.spy].price
        if not self.spy_sma_200.is_ready or spy_price < self.spy_sma_200.current.value:
            self.liquidate()
            for t in list(self.entry_prices.keys()):
                self._cleanup(t)
            return

        # VIX-based position scale
        vix_scale = self.get_vix_position_scale()
        if vix_scale <= 0:
            return

        sector_counts = self.get_sector_counts()

        scores = []
        for ticker in self.symbols.keys():
            if ticker in self.entry_prices:
                continue

            # Check sector limit
            sector = self.ticker_sectors.get(ticker, "other")
            if sector_counts.get(sector, 0) >= self.max_per_sector:
                continue

            symbol = self.symbols[ticker]
            if symbol not in self.securities:
                continue
            price = self.securities[symbol].price
            if price <= 0:
                continue

            result = self.calculate_residual_momentum(ticker)
            if result is None:
                continue

            residual_mom, beta = result

            if residual_mom <= 0.04:  # Higher threshold
                continue

            # ADX filter
            if ticker in self.adx_ind and self.adx_ind[ticker].is_ready:
                adx = self.adx_ind[ticker].current.value
                pos_di = self.adx_ind[ticker].positive_directional_index.current.value
                neg_di = self.adx_ind[ticker].negative_directional_index.current.value

                if adx < 22 or pos_di <= neg_di:  # Stronger trend required
                    continue

                score = residual_mom * (adx / 100) * beta
            else:
                continue  # Require ADX for entry

            scores.append({
                "ticker": ticker,
                "symbol": symbol,
                "sector": sector,
                "residual_mom": residual_mom,
                "beta": beta,
                "score": score
            })

        scores.sort(key=lambda x: x["score"], reverse=True)

        current_positions = len(self.entry_prices)
        slots = self.max_positions - current_positions

        # Calculate position size with cash buffer
        available_weight = (1.0 - self.cash_buffer) / self.max_positions
        position_weight = available_weight * vix_scale

        for s in scores[:slots]:
            ticker = s["ticker"]
            symbol = s["symbol"]
            sector = s["sector"]
            price = self.securities[symbol].price

            # Re-check sector limit
            if sector_counts.get(sector, 0) >= self.max_per_sector:
                continue

            self.set_holdings(symbol, position_weight)
            self.entry_prices[ticker] = price
            self.highest_prices[ticker] = price
            self.position_sectors[ticker] = sector
            sector_counts[sector] = sector_counts.get(sector, 0) + 1

            self.debug(f"{self.time.date()}: ENTER {ticker}({sector}) @ ${price:.2f} RM={s['residual_mom']:.3f}")
