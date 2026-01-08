from AlgorithmImports import *

class VolatilityManagedMomentum(QCAlgorithm):
    """
    Volatility-Managed Momentum - Scale Exposure Based on Market Vol

    THESIS:
    High volatility periods (VIX > 25) precede large drawdowns. By scaling
    down equity exposure when volatility is elevated, we reduce DD while
    maintaining upside capture in calm markets.

    WHY IT SHOULD WORK:
    1. Vol clustering: High vol today predicts high vol tomorrow
    2. Vol mean-reverts: VIX spikes are temporary, so we wait it out
    3. Momentum still works: We don't exit momentum, just reduce size
    4. Math of compounding: Avoiding -30% (which needs +43% to recover) > capturing +10%

    WHY DD SHOULD BE LOW:
    - When VIX > 25: only 50% invested (half the DD)
    - When VIX > 35: only 25% invested (quarter the DD)
    - March 2020 VIX hit 80 → would be nearly all cash

    POSITION SIZING:
    - VIX < 20: 100% invested (normal)
    - VIX 20-25: 75% invested
    - VIX 25-35: 50% invested
    - VIX > 35: 25% invested

    TARGET: 18-22% CAGR, <22% DD, Sharpe > 0.9

    EXCLUSIONS: No NVDA (robustness test)
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Diversified universe (NO NVDA)
        self.tickers = [
            "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "AMD", "AVGO",
            "CRM", "ORCL", "ADBE", "NFLX", "CSCO", "QCOM", "TXN",
            "NOW", "UBER", "SHOP", "AMAT", "MU",
            "JPM", "V", "MA", "UNH", "LLY",
            "XOM", "CAT", "HD", "COST", "PG"
        ]

        self.symbols = {}
        for ticker in self.tickers:
            try:
                self.symbols[ticker] = self.add_equity(ticker, Resolution.DAILY).symbol
            except:
                pass

        # VIX for volatility management
        self.vix = self.add_data(CBOE, "VIX", Resolution.DAILY).symbol

        # Market regime filter
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.spy_sma200 = self.sma(self.spy, 200, Resolution.DAILY)

        # Momentum indicators
        self.momentum_ind = {}
        for ticker, symbol in self.symbols.items():
            self.momentum_ind[ticker] = self.momp(symbol, 126, Resolution.DAILY)

        # Trend filter
        self.sma50_ind = {}
        for ticker, symbol in self.symbols.items():
            self.sma50_ind[ticker] = self.sma(symbol, 50, Resolution.DAILY)

        # 15 positions for diversification
        self.top_n = 15

        self.set_benchmark("SPY")

        self.schedule.on(
            self.date_rules.month_start(1),
            self.time_rules.after_market_open(self.spy, 30),
            self.rebalance
        )

        self.set_warm_up(210, Resolution.DAILY)

    def get_vol_scalar(self, vix_value):
        """Scale exposure based on VIX level"""
        if vix_value < 20:
            return 1.0    # Full exposure
        elif vix_value < 25:
            return 0.75   # 75% exposure
        elif vix_value < 35:
            return 0.50   # 50% exposure
        else:
            return 0.25   # 25% exposure (crisis mode)

    def rebalance(self):
        if self.is_warming_up:
            return

        if not self.spy_sma200.is_ready:
            return

        # Get VIX for vol scaling
        vix_value = self.securities[self.vix].price if self.securities[self.vix].price > 0 else 20
        vol_scalar = self.get_vol_scalar(vix_value)

        # Regime filter
        spy_price = self.securities[self.spy].price
        bull_market = spy_price > self.spy_sma200.current.value

        if not bull_market:
            self.liquidate()
            self.debug(f"{self.time.date()}: BEAR MARKET - Going to cash")
            return

        # Select candidates
        candidates = []
        for ticker, symbol in self.symbols.items():
            if ticker not in self.momentum_ind or ticker not in self.sma50_ind:
                continue
            if not self.momentum_ind[ticker].is_ready or not self.sma50_ind[ticker].is_ready:
                continue

            price = self.securities[symbol].price
            sma50 = self.sma50_ind[ticker].current.value
            momentum = self.momentum_ind[ticker].current.value

            if momentum > 0 and price > sma50:
                candidates.append({
                    'ticker': ticker,
                    'symbol': symbol,
                    'momentum': momentum
                })

        if len(candidates) < 5:
            self.liquidate()
            return

        sorted_candidates = sorted(candidates, key=lambda x: x['momentum'], reverse=True)
        top_stocks = sorted_candidates[:min(self.top_n, len(sorted_candidates))]

        # Liquidate positions not in top stocks
        top_tickers = [s['ticker'] for s in top_stocks]
        for ticker, symbol in self.symbols.items():
            if ticker not in top_tickers and self.portfolio[symbol].invested:
                self.liquidate(symbol)

        # VOLATILITY-SCALED position sizing
        base_weight = 0.95 / len(top_stocks)
        scaled_weight = base_weight * vol_scalar

        for stock in top_stocks:
            self.set_holdings(stock['symbol'], scaled_weight)

        total_exposure = scaled_weight * len(top_stocks)
        self.debug(f"{self.time.date()}: VIX={vix_value:.1f}, Scalar={vol_scalar:.0%}, Total Exposure={total_exposure:.0%}")

    def on_data(self, data):
        pass
