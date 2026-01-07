from AlgorithmImports import *
import numpy as np

class VolatilityAdjustedMomentum(QCAlgorithm):
    """
    Volatility-Adjusted Momentum Strategy

    Hypothesis: Risk-parity approach - size positions inversely
    to volatility. Higher momentum stocks get allocated more,
    but scaled down if too volatile.

    Signal: 6-month return > SPY, Price > 50 SMA
    Position sizing: Momentum * (1/Volatility) - risk-adjusted
    Positions: Top 5 stocks, volatility-weighted
    Rebalance: Monthly
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # === PARAMETERS ===
        self.num_positions = 5
        self.lookback = 126  # 6 months
        self.vol_lookback = 21  # 1 month volatility
        self.sma_period = 50

        # === UNIVERSE ===
        self.universe_tickers = [
            "NVDA", "TSLA", "AMD", "META", "AVGO", "AAPL", "MSFT", "GOOGL", "AMZN",
            "CRM", "NOW", "ADBE", "PANW", "CRWD", "NFLX",
            "AMAT", "LRCX", "MRVL",
            "V", "MA", "UNH", "JPM", "HD", "COST"
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

    def calculate_volatility(self, window):
        """Calculate annualized volatility from daily returns"""
        if not window.is_ready or window.count < self.vol_lookback + 1:
            return None

        prices = [window[i] for i in range(self.vol_lookback + 1)]
        returns = []
        for i in range(len(prices) - 1):
            if prices[i + 1] > 0:
                ret = (prices[i] - prices[i + 1]) / prices[i + 1]
                returns.append(ret)

        if len(returns) < 5:
            return None

        return np.std(returns) * np.sqrt(252)  # Annualized

    def get_signal_score(self, ticker):
        window = self.price_windows.get(ticker)
        sma = self.sma_indicators.get(ticker)

        if window is None or not window.is_ready:
            return False, 0, 0

        if sma is None or not sma.is_ready:
            return False, 0, 0

        current_price = window[0]
        stock_return = self.calculate_return(window)
        spy_return = self.calculate_return(self.spy_prices)
        volatility = self.calculate_volatility(window)

        if stock_return is None or spy_return is None or volatility is None:
            return False, 0, 0

        # Must beat SPY and be above SMA
        if stock_return <= spy_return:
            return False, 0, 0
        if current_price <= sma.current.value:
            return False, 0, 0

        # Risk-adjusted score: momentum / volatility
        risk_adj_score = stock_return / max(volatility, 0.1)

        return True, risk_adj_score, volatility

    def rebalance(self):
        if self.is_warming_up:
            return

        # Collect signals
        signals = []
        for ticker in self.universe_tickers:
            passes, score, vol = self.get_signal_score(ticker)
            if passes:
                signals.append({
                    'ticker': ticker,
                    'symbol': self.symbols[ticker],
                    'score': score,
                    'volatility': vol
                })

        # Sort by risk-adjusted score
        signals.sort(key=lambda x: x['score'], reverse=True)
        top_signals = signals[:self.num_positions]

        self.debug(f"=== REBALANCE {self.time.strftime('%Y-%m-%d')} ===")
        self.debug(f"Vol-adjusted signals: {len(signals)}, Taking top {len(top_signals)}")

        target_tickers = {s['ticker'] for s in top_signals}

        # Exit positions not in top
        for ticker, symbol in self.symbols.items():
            if self.portfolio[symbol].invested and ticker not in target_tickers:
                self.liquidate(symbol)

        if len(top_signals) == 0:
            return

        # Inverse volatility weighting
        total_inv_vol = sum(1 / s['volatility'] for s in top_signals)

        for sig in top_signals:
            inv_vol = 1 / sig['volatility']
            position_size = inv_vol / total_inv_vol
            position_size = min(position_size, 0.4)  # Cap at 40%

            symbol = sig['symbol']
            self.debug(f"  {sig['ticker']}: score={sig['score']:.2f}, vol={sig['volatility']*100:.1f}%, weight={position_size*100:.1f}%")

            current_pct = self.portfolio[symbol].holdings_value / self.portfolio.total_portfolio_value
            if abs(current_pct - position_size) > 0.02:
                self.set_holdings(symbol, position_size)
