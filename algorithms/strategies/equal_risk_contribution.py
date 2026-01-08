from AlgorithmImports import *

class EqualRiskContributionMomentum(QCAlgorithm):
    """
    Equal Risk Contribution Momentum Strategy

    THESIS: Weight positions by inverse volatility - volatile stocks
    get smaller allocations, stable stocks get larger allocations.

    WHY THIS WORKS:
    - NVDA (high vol) naturally gets smaller weight
    - Defensive stocks get larger weight for stability
    - Each position contributes similar risk to portfolio
    - Reduces concentration in high-flying momentum leaders
    - Academically proven to improve Sharpe ratio

    RULES:
    - Universe: 20 mega-caps
    - Filter: 6-month momentum > 0, Price > 50 SMA
    - Select: Top 10 by momentum
    - Weighting: Proportional to 1/ATR(20)
    - Position bounds: Min 5%, Max 15%
    - Regime: SPY > 200 SMA
    - Rebalance: Monthly

    EDGE: Risk-weighted positions reduce concentration while
    maintaining momentum exposure.
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
        self.atr = {}

        for ticker, symbol in self.symbols.items():
            self.momentum[ticker] = self.momp(symbol, 126)
            self.sma50[ticker] = self.sma(symbol, 50)
            # Use ATR indicator with explicit naming to avoid conflicts
            self.atr[ticker] = AverageTrueRange(20, MovingAverageType.SIMPLE)
            self.register_indicator(symbol, self.atr[ticker], Resolution.DAILY)

        # Market regime
        self.spy_sma200 = self.sma(self.spy, 200)

        # Settings
        self.min_weight = 0.05  # 5% min
        self.max_weight = 0.15  # 15% max
        self.target_positions = 10

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

        # Check market regime
        if not self.spy_sma200.is_ready:
            return

        spy_price = self.securities[self.spy].price
        spy_sma = self.spy_sma200.current.value

        if spy_price < spy_sma:
            self.log(f"BEAR MARKET: Cash.")
            self.liquidate()
            return

        # Calculate momentum scores and volatility
        candidates = []

        for ticker, symbol in self.symbols.items():
            if not self.securities[symbol].is_tradable:
                continue
            if not self.momentum[ticker].is_ready:
                continue
            if not self.sma50[ticker].is_ready:
                continue
            if not self.atr[ticker].is_ready:
                continue

            price = self.securities[symbol].price
            sma_value = self.sma50[ticker].current.value
            mom_value = self.momentum[ticker].current.value
            atr_value = self.atr[ticker].current.value

            # Filter: uptrend and positive momentum
            if price > sma_value and mom_value > 0 and atr_value > 0:
                # ATR as percentage of price for comparability
                atr_pct = atr_value / price if price > 0 else 0.1
                candidates.append({
                    'ticker': ticker,
                    'symbol': symbol,
                    'momentum': mom_value,
                    'atr_pct': atr_pct,
                    'inverse_vol': 1.0 / atr_pct if atr_pct > 0 else 1.0
                })

        if len(candidates) < 5:
            self.log(f"Only {len(candidates)} candidates. Cash.")
            self.liquidate()
            return

        # Sort by momentum, take top N
        sorted_by_momentum = sorted(candidates, key=lambda x: x['momentum'], reverse=True)
        selected = sorted_by_momentum[:self.target_positions]

        # Calculate risk-weighted allocations
        total_inverse_vol = sum(s['inverse_vol'] for s in selected)

        weights = {}
        for stock in selected:
            # Raw weight based on inverse volatility
            raw_weight = stock['inverse_vol'] / total_inverse_vol

            # Apply bounds
            bounded_weight = max(self.min_weight, min(self.max_weight, raw_weight))
            weights[stock['ticker']] = bounded_weight

        # Normalize to sum to 95%
        total_weight = sum(weights.values())
        scale = 0.95 / total_weight if total_weight > 0 else 0

        for ticker in weights:
            weights[ticker] *= scale

        # Log selection
        self.log(f"Selected {len(selected)} stocks (risk-weighted):")
        for stock in selected:
            w = weights[stock['ticker']]
            self.log(f"  {stock['ticker']}: {w*100:.1f}% (ATR%: {stock['atr_pct']*100:.1f}%)")

        # Liquidate non-selected
        for ticker, symbol in self.symbols.items():
            if ticker not in weights and self.portfolio[symbol].invested:
                self.liquidate(symbol)

        # Allocate
        for stock in selected:
            weight = weights[stock['ticker']]
            self.set_holdings(stock['symbol'], weight)

    def on_data(self, data):
        pass
