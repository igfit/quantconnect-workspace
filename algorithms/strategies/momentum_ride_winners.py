"""
Momentum Strategy: Ride Winners, Cut Losers

SIGNAL ALPHA:
1. Top 5 concentration (more in winners)
2. 10% stop-loss per position (cut losers fast)
3. NO upper limit - let winners run
4. Weekly check for exits only, monthly for new entries
"""

from AlgorithmImports import *


class MomentumRideWinners(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.set_security_initializer(lambda security: security.set_slippage_model(
            ConstantSlippageModel(0.001)
        ))
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        # PARAMETERS
        self.lookback_days = 126
        self.top_n = 5                    # Concentrated
        self.stop_loss_pct = 0.10         # 10% stop loss
        self.use_regime_filter = True
        self.min_dollar_volume = 5_000_000

        # Track entry prices for stop-loss
        self.entry_prices = {}

        # CLAUDE V3 UNIVERSE
        self.universe_tickers = [
            "NVDA", "AMD", "AVGO", "QCOM", "MU", "AMAT", "LRCX", "KLAC", "MRVL", "ON",
            "TXN", "ADI", "SNPS", "CDNS", "ASML",
            "CRM", "ADBE", "NOW", "INTU", "PANW", "VEEV", "WDAY",
            "V", "MA", "PYPL", "SQ",
            "AMZN", "SHOP",
            "BKNG", "RCL", "CCL", "MAR", "HLT", "WYNN",
            "XOM", "CVX", "OXY", "DVN", "SLB", "COP",
            "CAT", "DE", "URI", "BA",
            "TSLA", "NKE", "LULU", "CMG", "DECK",
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

        self.momentum = {}
        self.volume_sma = {}
        for symbol in self.symbols:
            self.momentum[symbol] = self.roc(symbol, self.lookback_days, Resolution.DAILY)
            self.volume_sma[symbol] = self.sma(symbol, 20, Resolution.DAILY, Field.VOLUME)

        self.set_warm_up(self.lookback_days + 10, Resolution.DAILY)

        # Monthly for new entries
        self.schedule.on(
            self.date_rules.month_start("SPY"),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )
        self.set_benchmark("SPY")

    def on_data(self, data):
        """Daily stop-loss check - CUT LOSERS FAST"""
        if self.is_warming_up:
            return

        # Regime check
        if self.use_regime_filter and self.spy_sma.is_ready:
            if self.securities[self.spy].price < self.spy_sma.current.value:
                self.liquidate()
                self.entry_prices.clear()
                return

        for symbol in list(self.entry_prices.keys()):
            if not self.portfolio[symbol].invested:
                if symbol in self.entry_prices:
                    del self.entry_prices[symbol]
                continue

            if symbol not in data or not data[symbol]:
                continue

            price = data[symbol].close
            entry = self.entry_prices[symbol]

            # Stop-loss triggered
            if price < entry * (1 - self.stop_loss_pct):
                self.liquidate(symbol, f"Stop loss: {price:.2f} < {entry * (1 - self.stop_loss_pct):.2f}")
                del self.entry_prices[symbol]

    def rebalance(self):
        if self.is_warming_up:
            return

        if self.use_regime_filter:
            if not self.spy_sma.is_ready:
                return
            if self.securities[self.spy].price < self.spy_sma.current.value:
                self.liquidate()
                self.entry_prices.clear()
                return

        scores = {}
        for symbol in self.symbols:
            if not self.momentum[symbol].is_ready:
                continue
            if not self.securities[symbol].has_data:
                continue
            price = self.securities[symbol].price
            if price < 5:
                continue
            if self.volume_sma[symbol].is_ready:
                if self.volume_sma[symbol].current.value * price < self.min_dollar_volume:
                    continue
            mom = self.momentum[symbol].current.value
            if mom > 0:
                scores[symbol] = mom

        if len(scores) < self.top_n:
            return

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_symbols = [s for s, _ in ranked[:self.top_n]]

        # Momentum-weighted (ride winners more)
        total_mom = sum(scores[s] for s in top_symbols)
        weights = {s: scores[s] / total_mom for s in top_symbols}

        # Sell positions not in top (unless still above stop)
        for holding in self.portfolio.values():
            if holding.invested and holding.symbol not in top_symbols:
                self.liquidate(holding.symbol)
                if holding.symbol in self.entry_prices:
                    del self.entry_prices[holding.symbol]

        # Enter/rebalance
        for symbol in top_symbols:
            target_weight = weights[symbol]
            current_weight = self.portfolio[symbol].holdings_value / self.portfolio.total_portfolio_value if self.portfolio.total_portfolio_value > 0 else 0

            # Only adjust if significant difference or new position
            if abs(target_weight - current_weight) > 0.02 or not self.portfolio[symbol].invested:
                self.set_holdings(symbol, target_weight)
                # Update entry price for new/increased positions
                if target_weight > current_weight:
                    self.entry_prices[symbol] = self.securities[symbol].price
