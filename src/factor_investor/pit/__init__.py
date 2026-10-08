"""Point-in-time fundamentals layer.

This module provides lookahead-free access to financial data by tracking
when each metric value became known to the market (publication date + buffer).

Public API:
    - PITService: Build and manage the PIT table
    - as_of(): Query fundamentals as of a specific date
    - ReportDelayConfig: Configuration for publication date fallbacks
"""

from factor_investor.pit.config import ReportDelayConfig, load_config
from factor_investor.pit.queries import as_of
from factor_investor.pit.service import BuildStats, PITService

__all__ = [
    "BuildStats",
    "PITService",
    "ReportDelayConfig",
    "as_of",
    "load_config",
]
