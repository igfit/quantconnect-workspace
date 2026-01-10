"""
Dual Momentum Systematic v3 - High Beta Focus

Improvement over v2: Focus on high-beta stocks only (the ones that
actually have momentum edge). Instead of 40 random large caps,
use only high-volatility/high-beta stocks.

Theory: Momentum works best on high-beta stocks because:
1. They overshoot more (stronger momentum signals)
2. They're more responsive to market trends
3. More institutional flow = momentum persistence

Universe: High-beta tech/growth stocks only (~15-20 stocks)
"""

from AlgorithmImports import *

class DualMomentumSystematicV3(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2018, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # HIGH-BETA UNIVERSE ONLY
        # These are stocks known for high volatility/beta
        # Selected based on sector (tech/growth) not performance
        self.universe_tickers = [
            # High-beta semiconductors
            "NVDA", "AMD", "MU", "MRVL", "ON", "AMAT", "LRCX", "KLAC",
            # High-beta EV/Auto
            "TSLA", "RIVN", "LCID",
            # High-beta software/cloud
            "SNOW", "DDOG", "NET", "CRWD", "ZS", "OKTA", "MDB",
            # High-beta fintech
            "SQ", "PYPL", "AFRM", "SOFI",
            # High-beta consumer tech
            "META", "NFLX", "ROKU", "SPOT",
            # High-beta biotech
            "MRNA", "BNTX",
        ]

        # Parameters
        self.lookback = 63
        self.rsi_period = 14
        self.rsi_threshold = 50
        self.trailing_stop_pct = 0.10
        self.base_risk_per_trade = 1500
        self.max_positions = 6

        # State
        self.symbols = {}
        self.highest_prices = {}
        self.entry_prices = {}

        # Indicators
        self.mom_indicators = {}
        self.rsi_indicators = {}
        self.atr_indicators = {}

        # Add SPY
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.spy_sma = self.sma(self.spy, 200, Resolution.DAILY)
        self.spy_roc = self.rocp(self.spy, self.lookback, Resolution.DAILY)

        # Add universe stocks
        for ticker in self.universe_tickers:
            try:
                equity = self.add_equity(ticker, Resolution.DAILY)
                symbol = equity.symbol
                self.symbols[ticker] = symbol

                self.mom_indicators[symbol] = self.rocp(symbol, self.lookback, Resolution.DAILY)
                self.rsi_indicators[symbol] = self.rsi(symbol, self.rsi_period, MovingAverageType.WILDERS, Resolution.DAILY)
                self.atr_indicators[symbol] = self.atr(symbol, 14, MovingAverageType.WILDERS, Resolution.DAILY)
            except Exception as e:
                self.debug(f"Could not add {ticker}: {e}")

        self.set_warm_up(210, Resolution.DAILY)
        self.set_benchmark("SPY")

    def on_data(self, data):
        if self.is_warming_up:
            return

        if not self.spy_sma.is_ready or not self.spy_roc.is_ready:
            return

        if self.spy not in data or data[self.spy] is None:
            return

        spy_price = data[self.spy].close
        spy_mom = self.spy_roc.current.value
        in_bull_market = spy_price > self.spy_sma.current.value

        if not in_bull_market:
            for symbol in list(self.highest_prices.keys()):
                if self.portfolio[symbol].invested:
                    self.liquidate(symbol, "Bear market")
            self.highest_prices.clear()
            self.entry_prices.clear()
            return

        # Check exits
        for symbol in list(self.highest_prices.keys()):
            if not self.portfolio[symbol].invested:
                if symbol in self.highest_prices:
                    del self.highest_prices[symbol]
                continue

            if symbol not in data or data[symbol] is None:
                continue

            current_price = data[symbol].close
            self.highest_prices[symbol] = max(self.highest_prices[symbol], current_price)

            should_exit = False

            # Trailing stop
            stop_price = self.highest_prices[symbol] * (1 - self.trailing_stop_pct)
            if current_price < stop_price:
                should_exit = True

            # Lost momentum
            if symbol in self.mom_indicators and self.mom_indicators[symbol].is_ready:
                if self.mom_indicators[symbol].current.value < 0:
                    should_exit = True

            if should_exit:
                self.liquidate(symbol)
                del self.highest_prices[symbol]
                if symbol in self.entry_prices:
                    del self.entry_prices[symbol]

        # Count positions
        current_positions = len([s for s in self.highest_prices if self.portfolio[s].invested])

        # Rank and enter
        candidates = []
        for ticker, symbol in self.symbols.items():
            if symbol not in self.mom_indicators or not self.mom_indicators[symbol].is_ready:
                continue
            if symbol not in self.rsi_indicators or not self.rsi_indicators[symbol].is_ready:
                continue
            if symbol not in self.atr_indicators or not self.atr_indicators[symbol].is_ready:
                continue
            if symbol not in data or data[symbol] is None:
                continue

            mom = self.mom_indicators[symbol].current.value
            rsi = self.rsi_indicators[symbol].current.value
            atr_val = self.atr_indicators[symbol].current.value
            price = data[symbol].close

            # Dual momentum filter
            if mom > 0 and mom > spy_mom and rsi > self.rsi_threshold:
                candidates.append((symbol, mom, price, atr_val))

        # Sort by momentum descending - take ONLY top candidates
        candidates.sort(key=lambda x: x[1], reverse=True)

        for symbol, mom, price, atr_val in candidates:
            if current_positions >= self.max_positions:
                break

            if self.portfolio[symbol].invested:
                continue

            shares = self.calculate_position_size(price, atr_val)
            if shares > 0:
                self.market_order(symbol, shares)
                self.highest_prices[symbol] = price
                self.entry_prices[symbol] = price
                current_positions += 1

    def calculate_position_size(self, price, atr_value):
        if atr_value <= 0 or price <= 0:
            return 0

        risk_per_share = 2 * atr_value
        shares = int(self.base_risk_per_trade / risk_per_share)
        max_value = self.portfolio.total_portfolio_value * 0.15
        max_shares = int(max_value / price)

        return min(shares, max_shares)
