from AlgorithmImports import *
from collections import defaultdict

class AntiConcentrationMomentum(QCAlgorithm):
    """
    Anti-Concentration Momentum Strategy

    THESIS: Explicitly limit concentration by forcing rotation.
    Stocks held for too long get skipped, forcing diversification.

    WHY THIS WORKS:
    - Prevents single stock (NVDA) from dominating returns
    - Forces profit-taking on extended winners
    - Rotates into next-best opportunities
    - Reduces single-stock drawdown risk
    - Captures fresh momentum rather than stale trends

    RULES:
    - Universe: 20 mega-caps
    - Track: How many months each stock has been held
    - Skip rule: If held 6+ of last 8 months, skip for 2 months
    - This forces rotation even for consistent performers
    - Standard momentum filters apply
    - Hold: Top 8 stocks
    - Rebalance: Monthly

    EDGE: Rotation reduces concentration risk while still
    capturing momentum in other strong performers.
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Mega-cap universe
        self.tickers = [
            "AAPL", "MSFT", "GOOGL", "AMZN", "META",
            "NVDA", "TSLA", "AVGO", "CRM", "ORCL",
            "ADBE", "NFLX", "AMD", "QCOM", "TXN",
            "UNH", "JNJ", "JPM", "V", "HD"
        ]

        # Add equities
        self.symbols = {}
        for ticker in self.tickers:
            equity = self.add_equity(ticker, Resolution.DAILY)
            equity.set_leverage(1.0)
            self.symbols[ticker] = equity.symbol

        # SPY for regime
        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.set_benchmark("SPY")

        # Indicators
        self.momentum = {}
        self.sma50 = {}

        for ticker, symbol in self.symbols.items():
            self.momentum[ticker] = self.momp(symbol, 126)
            self.sma50[ticker] = self.sma(symbol, 50)

        # Market regime
        self.spy_sma200 = self.sma(self.spy, 200)

        # Holding history: track when each stock was held
        self.holding_history = defaultdict(list)  # ticker -> list of months held
        self.cooldown = defaultdict(int)  # ticker -> months remaining in cooldown

        # Settings
        self.max_consecutive_months = 6  # Max times held in last 8 months
        self.lookback_months = 8
        self.cooldown_months = 2
        self.target_positions = 8
        self.max_weight = 0.125  # 12.5% max per position

        # Monthly rebalance
        self.schedule.on(
            self.date_rules.month_start(5),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )

        # Warmup
        self.set_warm_up(timedelta(days=210))

    def rebalance(self):
        if self.is_warming_up:
            return

        current_month = self.time.year * 12 + self.time.month

        # Decrement cooldowns
        for ticker in list(self.cooldown.keys()):
            self.cooldown[ticker] -= 1
            if self.cooldown[ticker] <= 0:
                del self.cooldown[ticker]

        # Check market regime
        if not self.spy_sma200.is_ready:
            return

        spy_price = self.securities[self.spy].price
        spy_sma = self.spy_sma200.current.value

        if spy_price < spy_sma:
            self.log(f"BEAR MARKET: Cash.")
            self.liquidate()
            # Don't update holding history when in cash
            return

        # Calculate momentum scores
        candidates = []

        for ticker, symbol in self.symbols.items():
            if not self.securities[symbol].is_tradable:
                continue
            if not self.momentum[ticker].is_ready or not self.sma50[ticker].is_ready:
                continue

            # Check if in cooldown
            if ticker in self.cooldown:
                self.log(f"  {ticker}: In cooldown ({self.cooldown[ticker]} months left)")
                continue

            price = self.securities[symbol].price
            sma_value = self.sma50[ticker].current.value
            mom_value = self.momentum[ticker].current.value

            # Filter: uptrend and positive momentum
            if price > sma_value and mom_value > 0:
                candidates.append({
                    'ticker': ticker,
                    'symbol': symbol,
                    'momentum': mom_value
                })

        if len(candidates) < 4:
            self.log(f"Only {len(candidates)} candidates. Cash.")
            self.liquidate()
            return

        # Sort by momentum, take top N
        sorted_candidates = sorted(candidates, key=lambda x: x['momentum'], reverse=True)
        selected = sorted_candidates[:self.target_positions]
        selected_tickers = set(s['ticker'] for s in selected)

        # Update holding history for selected stocks
        for ticker in self.tickers:
            # Add current month to history if selected
            if ticker in selected_tickers:
                self.holding_history[ticker].append(current_month)

            # Trim history to lookback window
            self.holding_history[ticker] = [
                m for m in self.holding_history[ticker]
                if current_month - m < self.lookback_months
            ]

            # Check if stock should enter cooldown
            if len(self.holding_history[ticker]) >= self.max_consecutive_months:
                if ticker in selected_tickers:
                    self.log(f"  {ticker}: Held {len(self.holding_history[ticker])} of last {self.lookback_months} months. Entering cooldown.")
                    self.cooldown[ticker] = self.cooldown_months
                    # Remove from selected
                    selected = [s for s in selected if s['ticker'] != ticker]

        # Reselect if we lost stocks to cooldown
        if len(selected) < self.target_positions:
            additional_needed = self.target_positions - len(selected)
            remaining = [c for c in sorted_candidates if c['ticker'] not in selected_tickers and c['ticker'] not in self.cooldown]
            selected.extend(remaining[:additional_needed])

        if len(selected) == 0:
            self.log("No stocks available. Cash.")
            self.liquidate()
            return

        # Equal weight with cap
        weight = min(self.max_weight, 0.95 / len(selected))

        # Log selection
        self.log(f"Selected {len(selected)} stocks:")
        for stock in selected:
            history_count = len(self.holding_history[stock['ticker']])
            self.log(f"  {stock['ticker']}: {stock['momentum']:.1f}% (held {history_count}/{self.lookback_months} months)")

        # Liquidate non-selected
        selected_set = set(s['ticker'] for s in selected)
        for ticker, symbol in self.symbols.items():
            if ticker not in selected_set and self.portfolio[symbol].invested:
                self.liquidate(symbol)

        # Allocate
        for stock in selected:
            self.set_holdings(stock['symbol'], weight)

    def on_data(self, data):
        pass
