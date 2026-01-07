from AlgorithmImports import *

class SectorRotation(QCAlgorithm):
    """
    Sector Rotation Strategy

    Hypothesis: Rotate to best-performing sector ETFs
    Can capture broader trends than individual stocks

    Signal: 3-month momentum, must beat SPY
    Positions: Top 2 sectors
    Rebalance: Monthly
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # === PARAMETERS ===
        self.num_positions = 2
        self.lookback = 63  # 3 months for sectors (faster rotation)
        self.sma_period = 50

        # === SECTOR ETFs ===
        self.sector_etfs = [
            "XLK",  # Technology
            "XLY",  # Consumer Discretionary
            "XLF",  # Financials
            "XLE",  # Energy
            "XLI",  # Industrials
            "XLV",  # Healthcare
            "XLC",  # Communication Services
            "XLB",  # Materials
            "XLRE", # Real Estate
            "XLU",  # Utilities
            "XLP",  # Consumer Staples
        ]

        # Add leveraged alternatives for more return potential
        self.leveraged_map = {
            "XLK": "TECL",  # 3x Tech
            "XLY": "WANT",  # 3x Consumer
            "XLF": "FAS",   # 3x Financials
            "XLE": "ERX",   # 2x Energy
        }

        # === ADD SECURITIES ===
        self.symbols = {}
        for etf in self.sector_etfs:
            equity = self.add_equity(etf, Resolution.DAILY)
            self.symbols[etf] = equity.symbol

        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.set_benchmark("SPY")

        # === DATA STRUCTURES ===
        self.price_windows = {}
        window_size = self.lookback + 10

        for etf in self.sector_etfs:
            self.price_windows[etf] = RollingWindow[float](window_size)

        self.spy_prices = RollingWindow[float](window_size)

        # === INDICATORS ===
        self.sma_indicators = {}
        for etf, symbol in self.symbols.items():
            self.sma_indicators[etf] = self.sma(symbol, self.sma_period, Resolution.DAILY)

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

        for etf, symbol in self.symbols.items():
            if data.bars.contains_key(symbol):
                self.price_windows[etf].add(data.bars[symbol].close)

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

    def get_signal_score(self, etf):
        window = self.price_windows.get(etf)
        sma = self.sma_indicators.get(etf)

        if window is None or not window.is_ready:
            return False, 0

        if sma is None or not sma.is_ready:
            return False, 0

        current_price = window[0]
        etf_return = self.calculate_return(window)
        spy_return = self.calculate_return(self.spy_prices)

        if etf_return is None or spy_return is None:
            return False, 0

        # Must beat SPY and be in uptrend
        if etf_return <= spy_return:
            return False, 0
        if current_price <= sma.current.value:
            return False, 0

        return True, etf_return

    def rebalance(self):
        if self.is_warming_up:
            return

        signals = []
        for etf in self.sector_etfs:
            passes, score = self.get_signal_score(etf)
            if passes:
                signals.append({'etf': etf, 'symbol': self.symbols[etf], 'score': score})

        signals.sort(key=lambda x: x['score'], reverse=True)
        top_signals = signals[:self.num_positions]

        self.debug(f"=== REBALANCE {self.time.strftime('%Y-%m-%d')} ===")
        self.debug(f"Sectors passing: {len(signals)}, Taking top {len(top_signals)}")
        for s in top_signals:
            self.debug(f"  {s['etf']}: {s['score']*100:.1f}%")

        target_etfs = {s['etf'] for s in top_signals}

        # Exit positions not in top
        for etf, symbol in self.symbols.items():
            if self.portfolio[symbol].invested and etf not in target_etfs:
                self.liquidate(symbol)

        if len(top_signals) == 0:
            self.debug("  No sectors beat SPY - holding cash")
            return

        position_size = 1.0 / len(top_signals)

        for sig in top_signals:
            symbol = sig['symbol']
            current_pct = self.portfolio[symbol].holdings_value / self.portfolio.total_portfolio_value
            if abs(current_pct - position_size) > 0.02:
                self.set_holdings(symbol, position_size)
