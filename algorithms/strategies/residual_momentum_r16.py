# region imports
from AlgorithmImports import *
import numpy as np
# endregion

class ResidualMomentumR16(QCAlgorithm):
    """
    Round 16 Strategy 6: Residual/Alpha Momentum

    Academic research shows ranking stocks on RESIDUAL returns (alpha)
    instead of raw returns produces ~2x risk-adjusted returns.

    Alpha = Stock Return - (Beta * Market Return)
    This isolates firm-specific momentum from market momentum.

    Source: Blitz et al. (2018), Hühn & Scholz (2018)
    "Alpha momentum dominates regular momentum in the US market"
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Parameters
        self.lookback = 63  # 3-month for momentum
        self.beta_lookback = 252  # 1 year for beta calculation

        self.tickers = [
            "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN", "TSLA",
            "AMD", "NFLX", "CRM", "ADBE", "AVGO",
            "JPM", "GS", "V", "MA",
            "UNH", "LLY", "JNJ",
            "CAT", "GE", "HON",
        ]

        self.symbols = {}
        self.return_history = {}
        self.entry_prices = {}
        self.entry_dates = {}

        for ticker in self.tickers:
            equity = self.add_equity(ticker, Resolution.DAILY)
            equity.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
            sym = equity.symbol
            self.symbols[ticker] = sym
            self.return_history[ticker] = []

        # Market benchmark for beta calculation
        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)
        self.spy_returns = []

        self.max_positions = 6

        # Weekly rebalance
        self.schedule.on(
            self.date_rules.every([DayOfWeek.MONDAY]),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )

        # Daily exit check
        self.schedule.on(
            self.date_rules.every_day("SPY"),
            self.time_rules.after_market_open("SPY", 31),
            self.check_exits
        )

        self.set_benchmark("SPY")
        self.set_warm_up(300, Resolution.DAILY)

        self.prev_prices = {}

    def on_data(self, data):
        """Collect daily returns"""
        if self.is_warming_up:
            return

        # SPY return
        if self.spy in data and data[self.spy] is not None:
            spy_price = data[self.spy].close
            if self.spy in self.prev_prices:
                spy_ret = (spy_price - self.prev_prices[self.spy]) / self.prev_prices[self.spy]
                self.spy_returns.append(spy_ret)
                if len(self.spy_returns) > self.beta_lookback + 50:
                    self.spy_returns = self.spy_returns[-(self.beta_lookback + 50):]
            self.prev_prices[self.spy] = spy_price

        # Stock returns
        for ticker in self.tickers:
            symbol = self.symbols[ticker]
            if symbol in data and data[symbol] is not None:
                price = data[symbol].close
                if symbol in self.prev_prices:
                    ret = (price - self.prev_prices[symbol]) / self.prev_prices[symbol]
                    self.return_history[ticker].append(ret)
                    if len(self.return_history[ticker]) > self.beta_lookback + 50:
                        self.return_history[ticker] = self.return_history[ticker][-(self.beta_lookback + 50):]
                self.prev_prices[symbol] = price

    def calculate_beta(self, stock_returns, market_returns):
        """Calculate beta using regression"""
        if len(stock_returns) < 60 or len(market_returns) < 60:
            return 1.0  # Default beta

        # Use last beta_lookback days
        n = min(len(stock_returns), len(market_returns), self.beta_lookback)
        stock = stock_returns[-n:]
        market = market_returns[-n:]

        # Simple beta = Cov(stock, market) / Var(market)
        mean_stock = sum(stock) / len(stock)
        mean_market = sum(market) / len(market)

        cov = sum((s - mean_stock) * (m - mean_market) for s, m in zip(stock, market)) / len(stock)
        var_market = sum((m - mean_market) ** 2 for m in market) / len(market)

        if var_market == 0:
            return 1.0

        return cov / var_market

    def calculate_residual_momentum(self, ticker):
        """Calculate alpha/residual momentum"""
        stock_rets = self.return_history[ticker]
        if len(stock_rets) < self.lookback or len(self.spy_returns) < self.lookback:
            return None

        # Calculate beta
        beta = self.calculate_beta(stock_rets, self.spy_returns)

        # Calculate residuals over lookback period
        residuals = []
        n = min(len(stock_rets), len(self.spy_returns), self.lookback)
        for i in range(-n, 0):
            stock_ret = stock_rets[i]
            market_ret = self.spy_returns[i]
            residual = stock_ret - beta * market_ret
            residuals.append(residual)

        # Residual momentum = cumulative residual return
        residual_momentum = sum(residuals)

        return residual_momentum, beta

    def check_exits(self):
        """Daily exit check"""
        if self.is_warming_up:
            return

        for ticker in list(self.entry_prices.keys()):
            symbol = self.symbols[ticker]
            if not self.portfolio[symbol].invested:
                self._cleanup(ticker)
                continue

            price = self.securities[symbol].price
            entry = self.entry_prices[ticker]
            pnl = (price - entry) / entry

            should_exit = False
            reason = ""

            # Stop loss
            if pnl <= -0.08:
                should_exit = True
                reason = f"STOP({pnl:.1%})"

            # Profit taking
            if pnl >= 0.20:
                should_exit = True
                reason = f"PROFIT(+{pnl:.1%})"

            if should_exit:
                self.liquidate(symbol)
                self.debug(f"{self.time.date()}: EXIT {ticker} {reason}")
                self._cleanup(ticker)

    def _cleanup(self, ticker):
        if ticker in self.entry_prices:
            del self.entry_prices[ticker]
        if ticker in self.entry_dates:
            del self.entry_dates[ticker]

    def rebalance(self):
        """Weekly rebalance based on residual momentum"""
        if self.is_warming_up:
            return

        # Market regime filter
        spy_price = self.securities[self.spy].price
        if not self.spy_sma_200.is_ready or spy_price < self.spy_sma_200.current.value:
            return

        # Calculate residual momentum for all stocks
        scores = []
        for ticker in self.tickers:
            if ticker in self.entry_prices:
                continue  # Already holding

            result = self.calculate_residual_momentum(ticker)
            if result is None:
                continue

            residual_mom, beta = result

            # Only consider positive residual momentum
            if residual_mom > 0:
                scores.append({
                    "ticker": ticker,
                    "symbol": self.symbols[ticker],
                    "residual_mom": residual_mom,
                    "beta": beta
                })

        # Rank by residual momentum
        scores.sort(key=lambda x: x["residual_mom"], reverse=True)

        # Enter top stocks
        current_positions = len(self.entry_prices)
        slots = self.max_positions - current_positions

        for s in scores[:slots]:
            ticker = s["ticker"]
            symbol = s["symbol"]
            price = self.securities[symbol].price

            weight = 1.0 / self.max_positions
            self.set_holdings(symbol, weight)
            self.entry_prices[ticker] = price
            self.entry_dates[ticker] = self.time
            self.debug(f"{self.time.date()}: ENTER {ticker} @ ${price:.2f} ResidMom={s['residual_mom']:.3f} Beta={s['beta']:.2f}")
