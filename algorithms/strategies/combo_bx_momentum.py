"""
Creative Combo #2: BX Trender + Momentum Selection

Use 6-month momentum to SELECT which stocks to trade,
then use BX Trender for TIMING of entries/exits.

Stock Selection: Top 15 by 6-month momentum (from No Top3 universe)
Entry Timing: BX crosses above 0 (turns bullish)
Exit: BX crosses below 0 OR drops out of top momentum

Hypothesis: Momentum selects winners, BX optimizes entry timing
to avoid buying at peaks. Should reduce drawdowns.
"""

from AlgorithmImports import *
import numpy as np


class BXMomentumCombo(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.set_security_initializer(lambda security: security.set_slippage_model(
            ConstantSlippageModel(0.001)
        ))
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        # BX parameters
        self.bx_l1 = 5    # Fast EMA
        self.bx_l2 = 20   # Slow EMA
        self.bx_l3 = 15   # RSI period

        # Momentum parameters
        self.lookback_days = 126  # 6 months
        self.top_n = 15
        self.use_regime_filter = True

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

        # Indicators
        self.momentum = {}
        self.ema_fast = {}
        self.ema_slow = {}
        self.ema_diff_window = {}
        self.prev_bx = {}

        for symbol in self.symbols:
            self.momentum[symbol] = self.roc(symbol, self.lookback_days, Resolution.DAILY)
            self.ema_fast[symbol] = self.ema(symbol, self.bx_l1, Resolution.DAILY)
            self.ema_slow[symbol] = self.ema(symbol, self.bx_l2, Resolution.DAILY)
            self.ema_diff_window[symbol] = RollingWindow[float](self.bx_l3 + 2)
            self.prev_bx[symbol] = None

        self.set_warm_up(self.lookback_days + 20, Resolution.DAILY)

        # Track top momentum stocks
        self.top_momentum_symbols = set()

        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )
        self.set_benchmark("SPY")

    def calc_rsi(self, values, period):
        """Calculate RSI from a list of values"""
        if len(values) < period + 1:
            return None
        changes = [values[i] - values[i-1] for i in range(1, len(values))]
        gains = [c if c > 0 else 0 for c in changes[-period:]]
        losses = [-c if c < 0 else 0 for c in changes[-period:]]
        avg_gain, avg_loss = np.mean(gains), np.mean(losses)
        if avg_loss == 0:
            return 100
        return 100 - (100 / (1 + avg_gain / avg_loss))

    def get_bx(self, symbol):
        """Calculate BX Trender value"""
        if not self.ema_fast[symbol].is_ready or not self.ema_slow[symbol].is_ready:
            return None

        ema_diff = self.ema_fast[symbol].current.value - self.ema_slow[symbol].current.value
        self.ema_diff_window[symbol].add(ema_diff)

        if not self.ema_diff_window[symbol].is_ready:
            return None

        # Get values in chronological order
        values = [self.ema_diff_window[symbol][i] for i in range(self.ema_diff_window[symbol].count)][::-1]
        rsi = self.calc_rsi(values, self.bx_l3)

        if rsi is None:
            return None
        return rsi - 50

    def rebalance(self):
        if self.is_warming_up:
            return

        # Regime filter
        if self.use_regime_filter:
            if not self.spy_sma.is_ready:
                return
            if self.securities[self.spy].price < self.spy_sma.current.value:
                self.liquidate()
                self.top_momentum_symbols = set()
                return

        # Step 1: Rank by momentum
        momentum_scores = {}
        for symbol in self.symbols:
            if not self.momentum[symbol].is_ready:
                continue
            if not self.securities[symbol].has_data:
                continue
            price = self.securities[symbol].price
            if price < 5:
                continue

            mom = self.momentum[symbol].current.value
            if mom > 0:  # Only positive momentum
                momentum_scores[symbol] = mom

        if len(momentum_scores) < 5:
            return

        # Top N by momentum
        ranked = sorted(momentum_scores.items(), key=lambda x: x[1], reverse=True)
        self.top_momentum_symbols = set([s for s, _ in ranked[:self.top_n]])

        # Step 2: Check BX signals for top momentum stocks
        entry_signals = []
        for symbol in self.top_momentum_symbols:
            bx = self.get_bx(symbol)
            prev = self.prev_bx.get(symbol)

            if bx is not None and prev is not None:
                # BX turned bullish
                if prev < 0 and bx >= 0:
                    entry_signals.append((symbol, momentum_scores.get(symbol, 0)))

            self.prev_bx[symbol] = bx

        # Exit: BX turned bearish OR out of top momentum
        for holding in list(self.portfolio.values()):
            if holding.invested and holding.symbol in self.symbols:
                sym = holding.symbol
                bx = self.get_bx(sym)
                prev = self.prev_bx.get(sym)

                # Exit if BX turned bearish
                if bx is not None and prev is not None:
                    if prev >= 0 and bx < 0:
                        self.liquidate(sym)
                        continue

                # Exit if dropped out of top momentum
                if sym not in self.top_momentum_symbols:
                    self.liquidate(sym)

        # Entry: Buy stocks with bullish BX signal (if not already invested)
        current_holdings = sum(1 for h in self.portfolio.values() if h.invested and h.symbol != self.spy)
        max_positions = self.top_n

        for symbol, _ in sorted(entry_signals, key=lambda x: x[1], reverse=True):
            if current_holdings >= max_positions:
                break
            if not self.portfolio[symbol].invested:
                weight = 1.0 / max_positions
                self.set_holdings(symbol, weight)
                current_holdings += 1
