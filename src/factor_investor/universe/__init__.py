"""Universe construction and dividend/total return management.

This module provides functionality to build and maintain investable universes,
sync dividend data, calculate total return series, and detect corporate events.

Public API:
    - DividendService: Sync dividends and build total returns
    - UniverseService: Build investable universe
    - get_universe, get_total_returns: Query functions
    - Dividend, TotalReturn, UniverseConstituent, CorporateEvent: ORM models
    - UniverseConfig: Configuration
    - events: Corporate event detection
"""

from factor_investor.universe import events
from factor_investor.universe.config import UniverseConfig, load_universe_config
from factor_investor.universe.dividend_service import (
    BuildStats as DividendBuildStats,
)
from factor_investor.universe.dividend_service import DividendService
from factor_investor.universe.models import (
    CorporateEvent,
    Dividend,
    TotalReturn,
    UniverseConstituent,
)
from factor_investor.universe.queries import get_total_returns, get_universe
from factor_investor.universe.universe_service import (
    BuildStats as UniverseBuildStats,
)
from factor_investor.universe.universe_service import UniverseService

__all__ = [
    "CorporateEvent",
    "Dividend",
    "DividendBuildStats",
    "DividendService",
    "TotalReturn",
    "UniverseBuildStats",
    "UniverseConfig",
    "UniverseConstituent",
    "UniverseService",
    "events",
    "get_total_returns",
    "get_universe",
    "load_universe_config",
]
