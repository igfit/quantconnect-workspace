"""
Indicator Strategy: Mean Reversion RSI

SIGNAL: Buy oversold (RSI < 30) stocks that are bouncing
- Entry: RSI < 35 AND RSI rising (today > yesterday)
- Exit: RSI > 65 (overbought)
- Counter-trend strategy
- Uses No Top3 universe
"""

from AlgorithmImports import *


class MeanReversionRSI(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.set_security_initializer(lambda security: security.set_slippage_model(
            ConstantSlippageModel(0.001)
        ))
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        self.rsi_period = 14
        self.rsi_oversold = 35
        self.rsi_overbought = 65
        self.top_n = 10
        self.use_regime_filter = True
        self.min_dollar_volume = 5_000_000

        self.prev_rsi = {}

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

        self.rsi_ind = {}
        self.volume_sma = {}
        for symbol in self.symbols:
            self.rsi_ind[symbol] = self.rsi(symbol, self.rsi_period, MovingAverageType.WILDERS, Resolution.DAILY)
            self.volume_sma[symbol] = self.sma(symbol, 20, Resolution.DAILY, Field.VOLUME)

        self.set_warm_up(self.rsi_period + 10, Resolution.DAILY)

        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )
        self.set_benchmark("SPY")

    def rebalance(self):
        if self.is_warming_up:
            return

        if self.use_regime_filter:
            if not self.spy_sma.is_ready:
                return
            if self.securities[self.spy].price < self.spy_sma.current.value:
                self.liquidate()
                self.prev_rsi.clear()
                return

        # Exit overbought positions
        for holding in list(self.portfolio.values()):
            if holding.invested and holding.symbol in self.rsi_ind:
                if self.rsi_ind[holding.symbol].is_ready:
                    if self.rsi_ind[holding.symbol].current.value > self.rsi_overbought:
                        self.liquidate(holding.symbol)

        scores = {}

        for symbol in self.symbols:
            if not self.rsi_ind[symbol].is_ready:
                continue
            if not self.securities[symbol].has_data:
                continue

            price = self.securities[symbol].price
            if price < 5:
                continue
            if self.volume_sma[symbol].is_ready:
                if self.volume_sma[symbol].current.value * price < self.min_dollar_volume:
                    continue

            rsi_val = self.rsi_ind[symbol].current.value
            prev_rsi_val = self.prev_rsi.get(symbol, rsi_val)

            # Entry: RSI oversold AND bouncing (rising)
            if rsi_val < self.rsi_oversold and rsi_val > prev_rsi_val:
                # Score by how oversold (lower = more oversold = higher score)
                scores[symbol] = (self.rsi_oversold - rsi_val)

            self.prev_rsi[symbol] = rsi_val

        if len(scores) < 3:
            return

        actual_n = min(self.top_n, len(scores))
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_symbols = [s for s, _ in ranked[:actual_n]]

        weight = 1.0 / max(actual_n, 5)  # Don't over-concentrate

        for symbol in top_symbols:
            if not self.portfolio[symbol].invested:
                self.set_holdings(symbol, weight)
