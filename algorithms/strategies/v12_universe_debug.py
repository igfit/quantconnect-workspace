"""
Debug: What stocks does the dynamic universe select in 2015?
Just logs the universe, no trading.
"""

from AlgorithmImports import *


class V12UniverseDebug(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2015, 3, 1)  # Short period just to see selection
        self.set_cash(100000)

        self.universe_size = 50
        self.min_market_cap = 2e9
        self.max_market_cap = 500e9
        self.min_price = 10
        self.min_avg_dollar_volume = 20e6

        self.selected_once = False

        self.add_universe(self.coarse_filter, self.fine_filter)

    def coarse_filter(self, coarse):
        if self.selected_once:
            return Universe.UNCHANGED

        filtered = [x for x in coarse
                   if x.has_fundamental_data
                   and x.price > self.min_price
                   and x.dollar_volume > self.min_avg_dollar_volume]

        self.debug(f"Coarse filter: {len(filtered)} stocks passed")

        sorted_by_volume = sorted(filtered, key=lambda x: x.dollar_volume, reverse=True)
        return [x.symbol for x in sorted_by_volume[:500]]

    def fine_filter(self, fine):
        if self.selected_once:
            return Universe.UNCHANGED

        filtered = [x for x in fine
                   if x.market_cap > self.min_market_cap
                   and x.market_cap < self.max_market_cap]

        self.debug(f"Market cap filter: {len(filtered)} stocks passed")

        growth_sectors = [
            MorningstarSectorCode.TECHNOLOGY,
            MorningstarSectorCode.CONSUMER_CYCLICAL,
            MorningstarSectorCode.HEALTHCARE,
            MorningstarSectorCode.COMMUNICATION_SERVICES
        ]

        sector_filtered = [x for x in filtered
                         if x.asset_classification.morningstar_sector_code in growth_sectors]

        self.debug(f"Sector filter: {len(sector_filtered)} stocks passed")

        # Check if NVDA/AMD are in the lists
        for x in fine:
            if "NVDA" in str(x.symbol) or "AMD" in str(x.symbol):
                self.debug(f"Found {x.symbol}: mcap={x.market_cap/1e9:.1f}B, sector={x.asset_classification.morningstar_sector_code}")

        sorted_stocks = sorted(sector_filtered, key=lambda x: x.dollar_volume, reverse=True)
        selected = [x.symbol for x in sorted_stocks[:self.universe_size]]

        # Log selected stocks
        for i, sym in enumerate(selected[:20]):
            self.debug(f"Selected #{i+1}: {sym}")

        self.selected_once = True
        return selected

    def on_data(self, data):
        pass
