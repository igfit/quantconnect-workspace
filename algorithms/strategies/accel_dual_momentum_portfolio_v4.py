from AlgorithmImports import *

class AccelDualMomentumPortfolioV4(QCAlgorithm):
    """
    Accelerating Dual Momentum Portfolio Strategy - V4 (Lower Risk)

    Changes:
    - Focus on larger, more stable stocks (no high-volatility names)
    - Expanded universe with more stable names
    - Same signal logic as V3 (simpler 6-month momentum)

    This version sacrifices some upside for lower drawdowns.
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # === PARAMETERS ===
        self.max_position_pct = 0.10
        self.max_positions = 12
        self.lookback = 126  # 6 months
        self.sma_period = 50

        # === UNIVERSE (More Stable, Less Volatile) ===
        # Quality Large-Caps with lower volatility
        self.universe_tickers = [
            # Tech Leaders (stable mega-caps)
            "AAPL", "MSFT", "GOOGL", "META", "AMZN",
            # Semiconductors (quality names only)
            "NVDA", "AVGO", "AMD",
            # Enterprise Software
            "CRM", "ADBE", "NOW", "ORCL",
            # Payments/Fintech
            "V", "MA", "PYPL",
            # Consumer/Retail
            "COST", "HD", "NFLX",
            # Healthcare
            "UNH", "JNJ", "LLY",
            # Industrial
            "CAT", "DE",
            # Remove: TSLA (too volatile), COIN/HOOD (crypto exposure), MRVL, ENPH, FSLR (volatile)
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

        for ticker, symbol in self.symbols.items():
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
        symbol = self.symbols.get(ticker)
        sma = self.sma_indicators.get(ticker)

        if window is None or not window.is_ready:
            return False, 0, "No data"

        if sma is None or not sma.is_ready:
            return False, 0, "SMA not ready"

        current_price = window[0]
        stock_return = self.calculate_return(window)
        spy_return = self.calculate_return(self.spy_prices)

        if stock_return is None or spy_return is None:
            return False, 0, "Return calc failed"

        abs_momentum = stock_return > 0
        rel_momentum = stock_return > spy_return
        trend_confirm = current_price > sma.current.value

        if not abs_momentum:
            return False, 0, "Abs Mom < 0"
        if not rel_momentum:
            return False, 0, "Rel Mom < SPY"
        if not trend_confirm:
            return False, 0, "Below 50 SMA"

        return True, stock_return, f"6mo={stock_return*100:.1f}%"

    def rebalance(self):
        if self.is_warming_up:
            return

        signals = []

        for ticker in self.universe_tickers:
            passes, score, reason = self.get_signal_score(ticker)
            if passes:
                signals.append({
                    'ticker': ticker,
                    'symbol': self.symbols[ticker],
                    'score': score,
                    'reason': reason
                })

        signals.sort(key=lambda x: x['score'], reverse=True)
        top_signals = signals[:self.max_positions]

        self.debug(f"=== REBALANCE {self.time.strftime('%Y-%m-%d')} ===")
        self.debug(f"Signals: {len(signals)} passed, taking top {len(top_signals)}")

        target_tickers = {s['ticker'] for s in top_signals}

        for ticker, symbol in self.symbols.items():
            if self.portfolio[symbol].invested and ticker not in target_tickers:
                self.liquidate(symbol)

        if len(top_signals) == 0:
            return

        num_positions = len(top_signals)
        position_size = min(1.0 / num_positions, self.max_position_pct)

        for sig in top_signals:
            ticker = sig['ticker']
            symbol = sig['symbol']
            current_pct = self.portfolio[symbol].holdings_value / self.portfolio.total_portfolio_value

            if abs(current_pct - position_size) > 0.01:
                self.set_holdings(symbol, position_size)

        invested = sum(1 for s in self.symbols.values() if self.portfolio[s].invested)
        self.debug(f"  Portfolio: {invested} positions")
