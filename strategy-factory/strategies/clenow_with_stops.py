"""
Clenow Momentum with Position Stops

Adds ATR-based trailing stops to protect gains and limit losses.
Goal: 30%+ CAGR with max drawdown under 30%

Key changes:
- Individual position stops (2.5 ATR trailing)
- Monthly rebalance + daily stop monitoring
- Position-level risk management
"""

from AlgorithmImports import *
from datetime import timedelta
import numpy as np


class ClenowMomentumWithStops(QCAlgorithm):
    """
    Clenow Momentum with Position-Level Stops

    Rules:
    - Monthly momentum ranking for entries
    - 2.5 ATR trailing stop on each position
    - 5 concentrated positions
    - Stops checked daily
    """

    MOMENTUM_LOOKBACK = 60
    TOP_N = 5
    MIN_MOMENTUM = 15
    ATR_PERIOD = 20
    ATR_STOP_MULT = 2.5

    def initialize(self):
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.universe_symbols = [
            # High-beta tech
            "NVDA", "AMD", "TSLA", "NFLX", "META", "SQ", "SHOP",
            # Semiconductors
            "AVGO", "MU", "MRVL", "AMAT", "LRCX",
            # Growth tech
            "CRM", "ADBE", "NOW", "PANW",
            # Established growth
            "AAPL", "MSFT", "GOOGL", "AMZN",
            # Biotech
            "MRNA", "REGN", "VRTX", "LLY",
            # Consumer
            "HD", "COST", "NKE", "SBUX", "LULU",
            # Financials
            "V", "MA", "GS", "JPM",
        ]

        self.stocks = []
        self.atr_indicators = {}

        for ticker in self.universe_symbols:
            try:
                equity = self.add_equity(ticker, Resolution.DAILY)
                equity.set_slippage_model(ConstantSlippageModel(0.001))
                equity.set_fee_model(InteractiveBrokersFeeModel())
                symbol = equity.symbol
                self.stocks.append(symbol)
                self.atr_indicators[symbol] = self.atr(symbol, self.ATR_PERIOD)
            except:
                pass

        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.set_benchmark(self.spy)

        # Position tracking with stops
        self.positions = {}  # symbol -> {entry_price, highest, stop}
        self.completed_trades = []

        self.set_warmup(timedelta(days=100))

        self.schedule.on(
            self.date_rules.month_start(self.spy),
            self.time_rules.after_market_open(self.spy, 30),
            self.rebalance
        )

        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.before_market_close(self.spy, 5),
            self.manage_stops
        )

    def calculate_momentum(self, symbol) -> float:
        history = self.history(symbol, self.MOMENTUM_LOOKBACK + 1, Resolution.DAILY)
        if history.empty or len(history) < self.MOMENTUM_LOOKBACK:
            return None

        try:
            prices = history['close'].values
            if len(prices) < 20:
                return None

            log_prices = np.log(prices)
            x = np.arange(len(log_prices))
            slope, intercept = np.polyfit(x, log_prices, 1)
            annualized_slope = (np.exp(slope * 252) - 1) * 100

            predictions = slope * x + intercept
            ss_res = np.sum((log_prices - predictions) ** 2)
            ss_tot = np.sum((log_prices - np.mean(log_prices)) ** 2)
            r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

            return annualized_slope * r_squared
        except:
            return None

    def rebalance(self):
        if self.is_warming_up:
            return

        # Get momentum rankings
        rankings = []
        for symbol in self.stocks:
            mom = self.calculate_momentum(symbol)
            if mom is not None and mom > self.MIN_MOMENTUM:
                rankings.append((symbol, mom))

        if len(rankings) < self.TOP_N:
            rankings = []
            for symbol in self.stocks:
                mom = self.calculate_momentum(symbol)
                if mom is not None and mom > 0:
                    rankings.append((symbol, mom))

        if len(rankings) < self.TOP_N:
            return

        rankings.sort(key=lambda x: x[1], reverse=True)
        top_stocks = [r[0] for r in rankings[:self.TOP_N]]
        top_stocks_set = set(top_stocks)

        self.log(f"TOP {self.TOP_N}: {' > '.join([f'{r[0].value}({r[1]:.0f})' for r in rankings[:self.TOP_N]])}")

        # Exit positions not in top N or stopped out
        for symbol in list(self.positions.keys()):
            if symbol not in top_stocks_set:
                self.exit_position(symbol, "Dropped from rankings")

        # Enter/maintain positions
        weight = 0.99 / self.TOP_N
        for symbol in top_stocks:
            if symbol not in self.positions:
                self.enter_position(symbol, weight)
            else:
                # Maintain position weight
                self.set_holdings(symbol, weight)

    def enter_position(self, symbol, weight: float):
        price = self.securities[symbol].price
        atr = self.atr_indicators[symbol].current.value if self.atr_indicators[symbol].is_ready else price * 0.03

        initial_stop = price - (self.ATR_STOP_MULT * atr)

        self.set_holdings(symbol, weight)

        self.positions[symbol] = {
            'entry_price': price,
            'entry_date': self.time,
            'highest': price,
            'stop': initial_stop,
        }

        self.log(f"ENTRY: {symbol} @ ${price:.2f} | Stop=${initial_stop:.2f}")

    def manage_stops(self):
        if self.is_warming_up:
            return

        for symbol in list(self.positions.keys()):
            pos = self.positions[symbol]
            price = self.securities[symbol].price
            atr = self.atr_indicators[symbol].current.value if self.atr_indicators[symbol].is_ready else price * 0.03

            # Update trailing stop
            if price > pos['highest']:
                pos['highest'] = price
                new_stop = price - (self.ATR_STOP_MULT * atr)
                if new_stop > pos['stop']:
                    pos['stop'] = new_stop

            # Check stop
            if price < pos['stop']:
                self.exit_position(symbol, f"Stop hit @ ${pos['stop']:.2f}")

    def exit_position(self, symbol, reason: str):
        if symbol not in self.positions:
            return

        pos = self.positions[symbol]
        exit_price = self.securities[symbol].price
        pnl_pct = (exit_price - pos['entry_price']) / pos['entry_price']
        days_held = (self.time - pos['entry_date']).days

        self.liquidate(symbol)

        self.completed_trades.append({
            'symbol': str(symbol),
            'pnl_pct': pnl_pct,
            'days_held': days_held,
        })

        self.log(f"EXIT: {symbol} | {reason} | P&L={pnl_pct*100:.1f}% | Days={days_held}")
        del self.positions[symbol]

    def on_end_of_algorithm(self):
        self.log("=" * 60)
        self.log("CLENOW WITH STOPS - SUMMARY")
        self.log("=" * 60)

        if not self.completed_trades:
            return

        total = len(self.completed_trades)
        winners = [t for t in self.completed_trades if t['pnl_pct'] > 0]
        losers = [t for t in self.completed_trades if t['pnl_pct'] <= 0]

        win_rate = len(winners) / total * 100
        avg_win = sum(t['pnl_pct'] for t in winners) / len(winners) * 100 if winners else 0
        avg_loss = sum(t['pnl_pct'] for t in losers) / len(losers) * 100 if losers else 0

        self.log(f"Total Trades: {total}")
        self.log(f"Win Rate: {win_rate:.1f}%")
        self.log(f"Avg Win: {avg_win:.1f}% | Avg Loss: {avg_loss:.1f}%")

    def on_data(self, data):
        pass
