from AlgorithmImports import *
from datetime import timedelta


class SectorAcceleratingRotation(QCAlgorithm):
    """
    Sector ETF Rotation with Accelerating Momentum

    Uses sector ETFs for better diversification and lower correlation.
    Rotates into sectors with accelerating momentum.

    Target: Lower drawdown, steady returns, Sharpe > 1.0
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.set_security_initializer(self._initialize_security)

        # Sector ETFs + Growth ETFs
        self.etf_list = [
            # Sector ETFs
            "XLK",  # Technology
            "XLF",  # Financials
            "XLE",  # Energy
            "XLV",  # Healthcare
            "XLY",  # Consumer Discretionary
            "XLP",  # Consumer Staples
            "XLI",  # Industrials
            "XLU",  # Utilities
            "XLB",  # Materials
            "XLRE", # Real Estate
            # Growth/Momentum ETFs
            "QQQ",  # Nasdaq 100
            "IWF",  # Russell 1000 Growth
            "VGT",  # Vanguard Tech
            "SMH",  # Semiconductors
        ]

        self.symbols = {}
        for ticker in self.etf_list:
            equity = self.add_equity(ticker, Resolution.DAILY)
            self.symbols[ticker] = equity.symbol

        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.set_benchmark("SPY")

        # Indicators
        self.sma50 = {}
        self.roc_21 = {}
        self.roc_63 = {}
        self.roc_126 = {}

        for ticker, symbol in self.symbols.items():
            self.sma50[symbol] = self.sma(symbol, 50, Resolution.DAILY)
            self.roc_21[symbol] = self.roc(symbol, 21, Resolution.DAILY)
            self.roc_63[symbol] = self.roc(symbol, 63, Resolution.DAILY)
            self.roc_126[symbol] = self.roc(symbol, 126, Resolution.DAILY)

        # SPY indicators for relative strength
        self.spy_roc_21 = self.roc(self.spy, 21, Resolution.DAILY)
        self.spy_roc_63 = self.roc(self.spy, 63, Resolution.DAILY)
        self.spy_roc_126 = self.roc(self.spy, 126, Resolution.DAILY)

        # Position sizing - equal weight across sectors
        self.max_position_pct = 0.15  # 15% max per ETF
        self.min_positions = 3
        self.max_positions = 8  # Hold top 8 sectors

        self.set_warmup(timedelta(days=150))

        # Weekly rebalancing
        self.schedule.on(
            self.date_rules.every(DayOfWeek.FRIDAY),
            self.time_rules.before_market_close("SPY", 30),
            self.rebalance
        )

    def _initialize_security(self, security):
        security.set_slippage_model(ConstantSlippageModel(0.0005))  # Lower slippage for ETFs
        security.set_fee_model(InteractiveBrokersFeeModel())

    def calculate_accel_momentum(self, symbol):
        """Accelerating momentum"""
        if symbol not in self.roc_21:
            return None

        roc21 = self.roc_21[symbol]
        roc63 = self.roc_63[symbol]
        roc126 = self.roc_126[symbol]

        if not (roc21.is_ready and roc63.is_ready and roc126.is_ready):
            return None

        return (roc21.current.value + roc63.current.value + roc126.current.value) / 3

    def calculate_spy_accel_momentum(self):
        """SPY accelerating momentum"""
        if not (self.spy_roc_21.is_ready and self.spy_roc_63.is_ready and self.spy_roc_126.is_ready):
            return None

        return (self.spy_roc_21.current.value + self.spy_roc_63.current.value + self.spy_roc_126.current.value) / 3

    def check_entry_conditions(self, symbol):
        """
        Entry if:
        1. Accelerating momentum > 0
        2. Sector beating SPY
        3. Price above 50 SMA
        """
        accel_mom = self.calculate_accel_momentum(symbol)
        if accel_mom is None or accel_mom <= 0:
            return False

        spy_accel = self.calculate_spy_accel_momentum()
        if spy_accel is not None and accel_mom <= spy_accel:
            return False

        sma = self.sma50.get(symbol)
        if sma is None or not sma.is_ready:
            return False
        if self.securities[symbol].price <= sma.current.value:
            return False

        return True

    def check_exit_conditions(self, symbol):
        """Exit if momentum turns negative or breaks trend"""
        accel_mom = self.calculate_accel_momentum(symbol)
        if accel_mom is None or accel_mom < 0:
            return True

        sma = self.sma50.get(symbol)
        if sma is not None and sma.is_ready:
            if self.securities[symbol].price < sma.current.value:
                return True

        return False

    def rebalance(self):
        """Weekly sector rotation"""
        if self.is_warming_up:
            return

        # Score all ETFs by accelerating momentum
        scores = []
        for ticker, symbol in self.symbols.items():
            if self.check_entry_conditions(symbol):
                accel_mom = self.calculate_accel_momentum(symbol)
                if accel_mom is not None:
                    scores.append((symbol, ticker, accel_mom))

        # Sort by momentum
        scores.sort(key=lambda x: x[2], reverse=True)

        # Select top N
        top_etfs = scores[:self.max_positions]
        target_symbols = set(s for s, _, _ in top_etfs)

        # Liquidate positions not in top
        for symbol in self.symbols.values():
            if self.portfolio[symbol].invested and symbol not in target_symbols:
                self.liquidate(symbol, "Rotated out")
                self.log(f"EXIT: {symbol}")

        # Equal weight target holdings
        if len(target_symbols) > 0:
            weight = min(1.0 / len(target_symbols), self.max_position_pct)

            for symbol, ticker, mom in top_etfs:
                current_weight = self.portfolio[symbol].holdings_value / self.portfolio.total_portfolio_value

                if not self.portfolio[symbol].invested or abs(current_weight - weight) > 0.02:
                    self.set_holdings(symbol, weight)
                    if not self.portfolio[symbol].invested:
                        self.log(f"ENTRY: {ticker} (AccelMom: {mom:.1f}%)")

    def on_data(self, data):
        pass
