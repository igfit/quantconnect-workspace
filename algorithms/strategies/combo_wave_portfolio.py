"""
Creative Combo #1: Wave-EWO Portfolio Strategy

Apply Wave-EWO (5/34 SMA) to No Top3 universe as a portfolio strategy.
Instead of single stock, trade top N stocks with bullish EWO signals.

Entry: EWO > 0 AND accelerating (EWO > prev EWO) AND RSI > 45
Exit: EWO < 0 OR RSI < 30
Rank: By EWO strength (higher = stronger trend)

Hypothesis: Wave-EWO works great on TSLA (858% return), might work
on a diversified basket with proper ranking.
"""

from AlgorithmImports import *


class WaveEWOPortfolio(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.set_security_initializer(lambda security: security.set_slippage_model(
            ConstantSlippageModel(0.001)
        ))
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        # EWO parameters (can be tuned)
        self.fast_period = 5
        self.slow_period = 34
        self.rsi_period = 14
        self.rsi_entry = 45
        self.rsi_exit = 30
        self.top_n = 10
        self.use_regime_filter = True

        # NO TOP3 UNIVERSE
        self.universe_tickers = [
            "AMD", "AVGO", "QCOM", "MU", "AMAT", "LRCX", "KLAC", "MRVL", "ON",
            "TXN", "ADI", "SNPS", "CDNS", "ASML",
            "CRM", "ADBE", "NOW", "INTU", "PANW", "VEEV", "WDAY",
            "V", "MA", "PYPL", "SQ",
            "AMZN", "SHOP",
            "BKNG", "RCL", "CCL", "MAR", "HLT", "WYNN",
            "XOM", "CVX", "OXY", "DVN", "SLB", "COP",
            "CAT", "DE", "URI", "BA",
            "NKE", "LULU", "CMG", "DECK",
            "GS", "MS",
            "NFLX", "ROKU",
        ]

        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.spy_sma = self.sma(self.spy, 200, Resolution.DAILY)

        self.symbols = []
        for ticker in self.universe_tickers:
            try:
                equity = self.add_equity(ticker, Resolution.DAILY)
                self.symbols.append(equity.symbol)
            except:
                pass

        # Indicators for each symbol
        self.sma_fast = {}
        self.sma_slow = {}
        self.rsi_ind = {}
        self.prev_ewo = {}

        for symbol in self.symbols:
            self.sma_fast[symbol] = self.sma(symbol, self.fast_period, Resolution.DAILY)
            self.sma_slow[symbol] = self.sma(symbol, self.slow_period, Resolution.DAILY)
            self.rsi_ind[symbol] = self.rsi(symbol, self.rsi_period, MovingAverageType.WILDERS, Resolution.DAILY)
            self.prev_ewo[symbol] = None

        self.set_warm_up(self.slow_period + 20, Resolution.DAILY)

        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )
        self.set_benchmark("SPY")

    def get_ewo(self, symbol):
        """Calculate Elliott Wave Oscillator"""
        if not self.sma_fast[symbol].is_ready or not self.sma_slow[symbol].is_ready:
            return None
        return self.sma_fast[symbol].current.value - self.sma_slow[symbol].current.value

    def rebalance(self):
        if self.is_warming_up:
            return

        # Regime filter
        if self.use_regime_filter:
            if not self.spy_sma.is_ready:
                return
            if self.securities[self.spy].price < self.spy_sma.current.value:
                self.liquidate()
                return

        scores = {}

        for symbol in self.symbols:
            ewo = self.get_ewo(symbol)
            if ewo is None:
                continue
            if not self.rsi_ind[symbol].is_ready:
                continue
            if not self.securities[symbol].has_data:
                continue

            price = self.securities[symbol].price
            if price < 5:
                continue

            rsi_val = self.rsi_ind[symbol].current.value
            prev = self.prev_ewo.get(symbol)

            # Entry conditions: EWO > 0, accelerating, RSI confirms
            if ewo > 0 and rsi_val >= self.rsi_entry:
                # Bonus for acceleration (EWO increasing)
                accel_bonus = 1.5 if (prev is not None and ewo > prev) else 1.0
                # Score by EWO strength normalized by price
                scores[symbol] = (ewo / price) * 100 * accel_bonus

            # Update prev EWO
            self.prev_ewo[symbol] = ewo

        # Exit positions with negative EWO or failing RSI
        for holding in list(self.portfolio.values()):
            if holding.invested and holding.symbol in self.symbols:
                ewo = self.get_ewo(holding.symbol)
                rsi_val = self.rsi_ind[holding.symbol].current.value if self.rsi_ind[holding.symbol].is_ready else 50

                if ewo is not None and (ewo < 0 or rsi_val < self.rsi_exit):
                    self.liquidate(holding.symbol)

        if len(scores) < 3:
            return

        actual_n = min(self.top_n, len(scores))
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_symbols = [s for s, _ in ranked[:actual_n]]

        # Equal weight
        weight = 1.0 / actual_n

        for holding in self.portfolio.values():
            if holding.invested and holding.symbol not in top_symbols and holding.symbol != self.spy:
                self.liquidate(holding.symbol)

        for symbol in top_symbols:
            self.set_holdings(symbol, weight)
