"""
Universe Definitions for Strategy Factory

Each universe is designed to minimize survivorship bias and provide
clean tests of signal alpha vs stock-picking alpha.

Universe Types:
    A: Core ETFs - Zero survivorship bias, highly liquid
    B: Sector SPDRs - Zero survivorship bias, sector rotation
    C: Large-Cap Liquid - Low bias, S&P 500 mega-caps (Phase 3)
    D: High-Beta Growth - Medium bias, screened at backtest start (Phase 4)
    E: Single Instrument - Zero bias, pure signal alpha test
"""

from .etf_core import ETF_CORE_UNIVERSE, get_etf_core_symbols
from .sector_spdrs import SECTOR_SPDR_UNIVERSE, get_sector_spdr_symbols
from .single_instrument import SINGLE_INSTRUMENT_UNIVERSE, get_single_instrument_symbols

__all__ = [
    'ETF_CORE_UNIVERSE',
    'get_etf_core_symbols',
    'SECTOR_SPDR_UNIVERSE',
    'get_sector_spdr_symbols',
    'SINGLE_INSTRUMENT_UNIVERSE',
    'get_single_instrument_symbols',
]
