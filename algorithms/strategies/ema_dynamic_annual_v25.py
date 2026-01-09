from AlgorithmImports import *
import numpy as np

class EMADynamicAnnualV25(QCAlgorithm):
    """
    V25: V8 SETTINGS + MEGA CAP QUALITY

    Back to V8's approach (which got 27.5% CAGR) but with:
    - Focus on mega-cap ($50B+ market cap) for resilience
    - Sector diversification (max 2 per sector)
    - Positive ROE filter for quality
    - Original 20/100 EMAs that worked

    Max 1x leverage: 5 positions at 20%
    Target: 28%+ CAGR with moderate DD
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100000)

        self.universe_size = 50
        self.min_price = 50.0  # Higher price floor
        self.min_dollar_volume = 50_000_000  # More liquid
        self.min_market_cap = 50e9  # $50B+ mega cap
        self.momentum_lookback = 126
        self.volatility_lookback = 60

        self.max_positions = 5
        self.weight_per_stock = 0.20

        # Original EMAs that worked
        self.ema_fast = 20
        self.ema_slow = 100

        self.indicators = {}
        self.prev_ema = {}
        self.current_universe = set()
        self.held_symbols = set()
        self.momentum_scores = {}
        self.stock_sectors = {}
        self.last_refresh_year = -1
        self.universe_symbols = []

        self.add_universe(self.coarse_filter, self.fine_filter)
        self.universe_settings.resolution = Resolution.DAILY
        self.universe_settings.minimum_time_in_universe = timedelta(days=30)

        self.set_benchmark("SPY")
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)
        self.set_warm_up(110, Resolution.DAILY)

    def coarse_filter(self, coarse):
        current_year = self.time.year
        current_month = self.time.month

        if self.last_refresh_year == current_year:
            return list(set(self.universe_symbols) | self.held_symbols)
        if current_month != 1 and self.last_refresh_year != -1:
            return list(set(self.universe_symbols) | self.held_symbols)

        filtered = [x for x in coarse
                   if x.has_fundamental_data
                   and x.price > self.min_price
                   and x.dollar_volume > self.min_dollar_volume
                   and x.market_cap > self.min_market_cap]

        sorted_by_volume = sorted(filtered, key=lambda x: x.dollar_volume, reverse=True)
        return [x.symbol for x in sorted_by_volume[:200]]

    def fine_filter(self, fine):
        current_year = self.time.year
        current_month = self.time.month

        if self.last_refresh_year == current_year:
            return list(set(self.universe_symbols) | self.held_symbols)
        if current_month != 1 and self.last_refresh_year != -1:
            return list(set(self.universe_symbols) | self.held_symbols)

        # Quality filter: positive ROE, not financial/utility/real estate
        filtered = [x for x in fine
                   if x.asset_classification.morningstar_sector_code not in [103, 104, 207]
                   and x.operation_ratios.roe.value is not None
                   and x.operation_ratios.roe.value > 0]

        stock_metrics = []
        for stock in filtered:
            try:
                symbol = stock.symbol
                sector = stock.asset_classification.morningstar_sector_code
                history = self.history(symbol, max(self.momentum_lookback, self.volatility_lookback), Resolution.DAILY)

                if len(history) >= self.momentum_lookback * 0.8:
                    start_price = history['close'].iloc[-self.momentum_lookback]
                    end_price = history['close'].iloc[-1]
                    if start_price > 0:
                        momentum = (end_price - start_price) / start_price
                        returns = history['close'].pct_change().dropna()
                        vol = returns.std() * np.sqrt(252)
                        if momentum > 0:
                            stock_metrics.append((symbol, momentum, vol, sector))
            except:
                pass

        if not stock_metrics:
            return list(self.held_symbols)

        # Above-median volatility
        vols = [x[2] for x in stock_metrics]
        median_vol = np.median(vols)

        volatile_momentum = [x for x in stock_metrics if x[2] >= median_vol]
        volatile_momentum.sort(key=lambda x: x[1], reverse=True)

        # Apply sector diversification (max 2 per sector)
        sector_counts = {}
        selected = []
        for symbol, mom, vol, sector in volatile_momentum:
            if sector not in sector_counts:
                sector_counts[sector] = 0
            if sector_counts[sector] < 2:
                selected.append((symbol, mom, sector))
                sector_counts[sector] += 1
            if len(selected) >= self.universe_size:
                break

        top_stocks = [x[0] for x in selected]
        self.momentum_scores = {x[0]: x[1] for x in selected}
        self.stock_sectors = {x[0]: x[2] for x in selected}
        self.universe_symbols = top_stocks
        self.last_refresh_year = current_year

        self.debug(f"V25 Universe: {len(top_stocks)} mega-cap quality stocks")
        return list(set(top_stocks) | self.held_symbols)

    def on_securities_changed(self, changes):
        for security in changes.removed_securities:
            symbol = security.symbol
            if symbol not in self.held_symbols:
                self.indicators.pop(symbol, None)
                self.prev_ema.pop(symbol, None)
            self.current_universe.discard(symbol)

        for security in changes.added_securities:
            symbol = security.symbol
            self.current_universe.add(symbol)
            if symbol not in self.indicators:
                self.indicators[symbol] = {
                    'ema_fast': self.ema(symbol, self.ema_fast, Resolution.DAILY),
                    'ema_slow': self.ema(symbol, self.ema_slow, Resolution.DAILY),
                }
                self.prev_ema[symbol] = {'fast': None, 'slow': None}

    def on_data(self, data):
        if self.is_warming_up:
            return

        position_count = len(self.held_symbols)
        entry_candidates = []

        for symbol in list(self.current_universe | self.held_symbols):
            if symbol not in data.bars or symbol not in self.indicators:
                continue

            ind = self.indicators[symbol]
            if not ind['ema_fast'].is_ready or not ind['ema_slow'].is_ready:
                continue

            current_price = data.bars[symbol].close
            ema_fast = ind['ema_fast'].current.value
            ema_slow = ind['ema_slow'].current.value

            prev = self.prev_ema.get(symbol, {'fast': None, 'slow': None})
            if prev['fast'] is None:
                self.prev_ema[symbol] = {'fast': ema_fast, 'slow': ema_slow}
                continue

            bullish_cross = prev['fast'] <= prev['slow'] and ema_fast > ema_slow
            bearish_cross = prev['fast'] >= prev['slow'] and ema_fast < ema_slow

            if bearish_cross and symbol in self.held_symbols:
                self.liquidate(symbol, "EMA Exit")
                self.held_symbols.discard(symbol)
                position_count -= 1

            elif bullish_cross and symbol in self.current_universe and symbol not in self.held_symbols:
                mom_score = self.momentum_scores.get(symbol, 0)
                entry_candidates.append((symbol, mom_score))

            self.prev_ema[symbol] = {'fast': ema_fast, 'slow': ema_slow}

        if entry_candidates and position_count < self.max_positions:
            entry_candidates.sort(key=lambda x: x[1], reverse=True)
            for symbol, _ in entry_candidates:
                if position_count >= self.max_positions:
                    break
                self.set_holdings(symbol, self.weight_per_stock)
                self.held_symbols.add(symbol)
                position_count += 1
