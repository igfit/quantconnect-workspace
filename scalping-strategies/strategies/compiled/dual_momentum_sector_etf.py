"""
Dual Momentum Sector ETF Rotation

ELIMINATES HINDSIGHT BIAS COMPLETELY by using sector ETFs instead of
individual stocks. No stock-picking whatsoever.

Universe: 11 SPDR Sector ETFs (existed since 1998)
Strategy: Apply same dual momentum rules to rotate between sectors

Pros:
- Zero single-stock selection bias
- Diversified within each sector
- Lower volatility than individual stocks
- Liquid, low-cost instruments

Cons:
- Lower absolute returns (ETFs dampen momentum)
- Sector concentration risk
"""

from AlgorithmImports import *

class DualMomentumSectorETF(QCAlgorithm):
    """
    Sector ETF Rotation with Dual Momentum

    Universe: SPDR Sector ETFs
    - XLK: Technology
    - XLY: Consumer Discretionary
    - XLC: Communication Services
    - XLF: Financials
    - XLV: Healthcare
    - XLI: Industrials
    - XLE: Energy
    - XLB: Materials
    - XLU: Utilities
    - XLRE: Real Estate
    - XLP: Consumer Staples

    Entry:
    1. SPY > 200 SMA (bull market)
    2. Sector 3-month return > 0 (absolute momentum)
    3. Sector 3-month return > SPY (relative momentum)
    4. RSI > 50

    Exit:
    1. Momentum turns negative
    2. OR trailing stop hit (8% - tighter for ETFs)

    Position Sizing: Equal weight among selected sectors
    """

    def initialize(self):
        self.set_start_date(2018, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Sector ETFs - all have long history, no selection bias
        self.sector_etfs = [
            "XLK",   # Technology
            "XLY",   # Consumer Discretionary
            "XLC",   # Communication Services (started 2018)
            "XLF",   # Financials
            "XLV",   # Healthcare
            "XLI",   # Industrials
            "XLE",   # Energy
            "XLB",   # Materials
            "XLU",   # Utilities
            "XLRE",  # Real Estate
            "XLP",   # Consumer Staples
        ]

        # Parameters - adjusted for ETF characteristics
        self.lookback = 63  # 3-month momentum
        self.rsi_period = 14
        self.rsi_threshold = 50
        self.trailing_stop_pct = 0.08  # Tighter for ETFs (less volatile)
        self.max_positions = 4  # Concentrate in top sectors

        # State
        self.symbols = {}
        self.spy = None
        self.spy_sma = None
        self.highest_prices = {}

        # Indicators - use unique names
        self.mom_indicators = {}
        self.rsi_indicators = {}

        # Add SPY
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.spy_sma = self.sma(self.spy, 200, Resolution.DAILY)
        self.spy_roc = self.rocp(self.spy, self.lookback, Resolution.DAILY)

        # Add sector ETFs
        for ticker in self.sector_etfs:
            try:
                equity = self.add_equity(ticker, Resolution.DAILY)
                symbol = equity.symbol
                self.symbols[ticker] = symbol

                self.mom_indicators[symbol] = self.rocp(symbol, self.lookback, Resolution.DAILY)
                self.rsi_indicators[symbol] = self.rsi(symbol, self.rsi_period, MovingAverageType.WILDERS, Resolution.DAILY)
            except:
                self.debug(f"Could not add {ticker}")

        # Warmup
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

        # Bear market - exit all
        if not in_bull_market:
            for symbol in list(self.portfolio.keys()):
                if self.portfolio[symbol].invested:
                    self.liquidate(symbol, "Bear market")
            self.highest_prices.clear()
            return

        # Update trailing stops and check exits
        for symbol in list(self.portfolio.keys()):
            if not self.portfolio[symbol].invested:
                continue

            if symbol not in data or data[symbol] is None:
                continue

            current_price = data[symbol].close

            # Update highest price
            if symbol in self.highest_prices:
                self.highest_prices[symbol] = max(self.highest_prices[symbol], current_price)

            should_exit = False
            exit_reason = ""

            # Trailing stop
            if symbol in self.highest_prices:
                stop_price = self.highest_prices[symbol] * (1 - self.trailing_stop_pct)
                if current_price < stop_price:
                    should_exit = True
                    exit_reason = "Trailing stop"

            # Lost momentum
            if symbol in self.mom_indicators and self.mom_indicators[symbol].is_ready:
                if self.mom_indicators[symbol].current.value < 0:
                    should_exit = True
                    exit_reason = "Lost momentum"

            if should_exit:
                self.liquidate(symbol, exit_reason)
                if symbol in self.highest_prices:
                    del self.highest_prices[symbol]

        # Rank sectors by momentum
        candidates = []
        for ticker, symbol in self.symbols.items():
            if symbol not in self.mom_indicators or not self.mom_indicators[symbol].is_ready:
                continue
            if symbol not in self.rsi_indicators or not self.rsi_indicators[symbol].is_ready:
                continue
            if symbol not in data or data[symbol] is None:
                continue

            mom = self.mom_indicators[symbol].current.value
            rsi = self.rsi_indicators[symbol].current.value

            # Dual momentum filter
            if mom > 0 and mom > spy_mom and rsi > self.rsi_threshold:
                candidates.append((symbol, mom))

        # Sort by momentum
        candidates.sort(key=lambda x: x[1], reverse=True)
        target_symbols = [c[0] for c in candidates[:self.max_positions]]

        # Exit sectors no longer in top N
        for symbol in list(self.portfolio.keys()):
            if self.portfolio[symbol].invested and symbol not in target_symbols:
                self.liquidate(symbol, "No longer top momentum")
                if symbol in self.highest_prices:
                    del self.highest_prices[symbol]

        # Calculate position size (equal weight)
        if len(target_symbols) > 0:
            position_value = self.portfolio.total_portfolio_value * 0.9 / self.max_positions
        else:
            return

        # Enter new positions
        for symbol in target_symbols:
            if self.portfolio[symbol].invested:
                continue

            if symbol not in data or data[symbol] is None:
                continue

            price = data[symbol].close
            shares = int(position_value / price)

            if shares > 0:
                self.market_order(symbol, shares)
                self.highest_prices[symbol] = price
                self.debug(f"BUY {symbol}: shares={shares}")
