from AlgorithmImports import *

class ConcentratedMomentum(QCAlgorithm):
    """
    Concentrated Momentum Strategy

    Hypothesis: Holding only top 3-5 momentum stocks will capture more upside
    than diversified portfolios, at the cost of higher volatility.

    Signal: 6-month return > SPY, Price > 50 SMA
    Positions: Top 3 stocks only (33% each)
    Rebalance: Monthly
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # === PARAMETERS ===
        self.num_positions = 3  # CONCENTRATED
        self.lookback = 126  # 6 months
        self.sma_period = 50

        # === UNIVERSE - High momentum potential ===
        self.universe_tickers = [
            # Tech Leaders
            "NVDA", "TSLA", "AMD", "META", "AVGO", "AAPL", "MSFT", "GOOGL", "AMZN",
            # Growth
            "CRM", "NOW", "ADBE", "PANW", "CRWD", "NFLX",
            # Semiconductors
            "AMAT", "LRCX", "MRVL",
            # High Beta
            "COIN", "HOOD", "UBER", "ABNB",
            # Energy
            "FSLR", "ENPH",
            # Stable
            "V", "MA", "UNH"
        ]

        # === ADD SECURITIES ===
        self.symbols = {}
        for ticker in self.universe_tickers:
            equity = self.add_equity(ticker, Resolution.DAILY)
            self.symbols[ticker] = equity.symbol

        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.set_benchmark("SPY")

        # === DATA STRUCTURES ===
        self.price_windows = {}
        window_size = self.lookback + 10

        for ticker in self.universe_tickers:
            self.price_windows[ticker] = RollingWindow[float](window_size)

        self.spy_prices = RollingWindow[float](window_size)

        # === INDICATORS ===
        self.sma_indicators = {}
        for ticker, symbol in self.symbols.items():
            self.sma_indicators[ticker] = self.sma(symbol, self.sma_period, Resolution.DAILY)

        # === WARMUP ===
        self.set_warm_up(self.lookback + 20)

        # === MONTHLY REBALANCING ===
        self.schedule.on(
            self.date_rules.month_start(self.spy),
            self.time_rules.after_market_open(self.spy, 30),
            self.rebalance
        )

    def on_data(self, data):
        if self.is_warming_up:
            return

        for ticker, symbol in self.symbols.items():
            if data.bars.contains_key(symbol):
                self.price_windows[ticker].add(data.bars[symbol].close)

        if data.bars.contains_key(self.spy):
            self.spy_prices.add(data.bars[self.spy].close)

    def calculate_return(self, window):
        if not window.is_ready or window.count < self.lookback + 1:
            return None
        current = window[0]
        past = window[self.lookback]
        if past == 0:
            return None
        return (current - past) / past

    def get_signal_score(self, ticker):
        window = self.price_windows.get(ticker)
        sma = self.sma_indicators.get(ticker)

        if window is None or not window.is_ready:
            return False, 0

        if sma is None or not sma.is_ready:
            return False, 0

        current_price = window[0]
        stock_return = self.calculate_return(window)
        spy_return = self.calculate_return(self.spy_prices)

        if stock_return is None or spy_return is None:
            return False, 0

        # Must beat SPY and be above SMA
        if stock_return <= spy_return:
            return False, 0
        if current_price <= sma.current.value:
            return False, 0

        return True, stock_return

    def rebalance(self):
        if self.is_warming_up:
            return

        # Collect signals
        signals = []
        for ticker in self.universe_tickers:
            passes, score = self.get_signal_score(ticker)
            if passes:
                signals.append({'ticker': ticker, 'symbol': self.symbols[ticker], 'score': score})

        # Sort by momentum (highest first)
        signals.sort(key=lambda x: x['score'], reverse=True)

        # Take top N
        top_signals = signals[:self.num_positions]

        self.debug(f"=== REBALANCE {self.time.strftime('%Y-%m-%d')} ===")
        self.debug(f"Signals: {len(signals)}, Taking top {len(top_signals)}")
        for s in top_signals:
            self.debug(f"  {s['ticker']}: {s['score']*100:.1f}%")

        target_tickers = {s['ticker'] for s in top_signals}

        # Exit positions not in top
        for ticker, symbol in self.symbols.items():
            if self.portfolio[symbol].invested and ticker not in target_tickers:
                self.liquidate(symbol)

        if len(top_signals) == 0:
            return

        # Equal weight across top positions
        position_size = 1.0 / len(top_signals)

        for sig in top_signals:
            symbol = sig['symbol']
            current_pct = self.portfolio[symbol].holdings_value / self.portfolio.total_portfolio_value
            if abs(current_pct - position_size) > 0.02:
                self.set_holdings(symbol, position_size)
