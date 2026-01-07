from AlgorithmImports import *
import numpy as np
import json

class BetaScreener(QCAlgorithm):
    """
    Screens for high-beta stocks by calculating beta from historical returns.
    Outputs list of stocks with beta > 1.5

    Results are stored in ObjectStore for retrieval via API.
    Beta = Cov(stock_returns, market_returns) / Var(market_returns)
    Uses 252 trading days (1 year) of data
    """

    def initialize(self):
        self.set_start_date(2024, 12, 1)
        self.set_end_date(2024, 12, 5)  # Short period - just screening
        self.set_cash(100000)

        # Add SPY as benchmark
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol

        # Add universe of liquid stocks
        self.universe_settings.resolution = Resolution.DAILY
        self.add_universe(self.coarse_filter)

        self.screened = False
        self.symbols_to_screen = []

    def coarse_filter(self, coarse):
        if self.screened:
            return Universe.UNCHANGED

        # Filter: price > $5, high volume, has fundamental data
        filtered = [x for x in coarse
                   if x.price > 5
                   and x.dollar_volume > 5000000
                   and x.has_fundamental_data]

        # Take top 300 by dollar volume for screening
        sorted_by_volume = sorted(filtered, key=lambda x: x.dollar_volume, reverse=True)[:300]

        self.symbols_to_screen = [x.symbol for x in sorted_by_volume]
        self.log(f"Coarse filter selected {len(self.symbols_to_screen)} symbols for beta screening")

        return self.symbols_to_screen

    def on_data(self, data):
        if self.screened or len(self.symbols_to_screen) == 0:
            return

        self.screened = True

        # Get 1 year of history for beta calculation
        all_symbols = self.symbols_to_screen + [self.spy]

        self.log(f"Fetching 252 days of history for {len(all_symbols)} symbols...")
        history = self.history(all_symbols, 252, Resolution.DAILY)

        if history.empty:
            self.log("ERROR: No history returned")
            return

        self.log(f"History shape: {history.shape}")

        # Calculate SPY returns
        try:
            spy_data = history.loc[self.spy]['close']
            spy_returns = spy_data.pct_change().dropna()
            self.log(f"SPY returns: {len(spy_returns)} data points")
        except Exception as e:
            self.log(f"ERROR getting SPY returns: {e}")
            return

        high_beta_stocks = []
        errors = 0

        for symbol in self.symbols_to_screen:
            try:
                stock_data = history.loc[symbol]['close']
                stock_returns = stock_data.pct_change().dropna()

                # Align returns by date
                common_dates = spy_returns.index.intersection(stock_returns.index)
                if len(common_dates) < 60:  # Need at least 60 days
                    continue

                aligned_stock = stock_returns.loc[common_dates].values
                aligned_spy = spy_returns.loc[common_dates].values

                # Calculate beta: Cov(stock, market) / Var(market)
                covariance = np.cov(aligned_stock, aligned_spy)[0][1]
                variance = np.var(aligned_spy)

                if variance == 0:
                    continue

                beta = covariance / variance

                if beta > 1.5:  # High beta threshold
                    high_beta_stocks.append({"ticker": symbol.value, "beta": round(beta, 2)})

            except Exception as e:
                errors += 1
                continue

        self.log(f"Processed with {errors} errors")

        # Sort by beta descending
        high_beta_stocks.sort(key=lambda x: x["beta"], reverse=True)

        # Store results in ObjectStore for API retrieval
        results = {
            "scan_date": str(self.time),
            "total_screened": len(self.symbols_to_screen),
            "high_beta_count": len(high_beta_stocks),
            "threshold": 1.5,
            "stocks": high_beta_stocks
        }

        # Save to ObjectStore
        self.object_store.save("beta_screen_results", json.dumps(results, indent=2))
        self.log("Results saved to ObjectStore: beta_screen_results")

        # Also log top results for visibility
        self.log("")
        self.log("=" * 60)
        self.log(f"HIGH BETA STOCKS (Beta > 1.5): Found {len(high_beta_stocks)}")
        self.log("=" * 60)

        # Group and log by tier
        ultra_high = [s for s in high_beta_stocks if s["beta"] >= 2.5]
        very_high = [s for s in high_beta_stocks if 2.0 <= s["beta"] < 2.5]
        high = [s for s in high_beta_stocks if 1.5 <= s["beta"] < 2.0]

        self.log(f"\nULTRA HIGH (>=2.5): {len(ultra_high)} stocks")
        for s in ultra_high[:15]:
            self.log(f"  {s['ticker']}: {s['beta']}")

        self.log(f"\nVERY HIGH (2.0-2.5): {len(very_high)} stocks")
        for s in very_high[:15]:
            self.log(f"  {s['ticker']}: {s['beta']}")

        self.log(f"\nHIGH (1.5-2.0): {len(high)} stocks")
        for s in high[:20]:
            self.log(f"  {s['ticker']}: {s['beta']}")

        self.log("\n" + "=" * 60)
        self.log("TOP 20 FOR TESTING:")
        self.log("=" * 60)
        for i, s in enumerate(high_beta_stocks[:20], 1):
            self.log(f"{i}. {s['ticker']} (beta: {s['beta']})")
