"""Configuration for point-in-time fundamentals layer."""

import tomllib
from pathlib import Path

from pydantic import BaseModel


class ReportDelayConfig(BaseModel):
    """Configuration for report publication delay assumptions.

    These delays are used when actual publication dates are missing,
    to conservatively estimate when a report became known to the market.
    """

    quarterly: int = 60
    """Days after period end for quarterly reports (default: 60)."""

    annual: int = 90
    """Days after period end for annual reports (default: 90)."""

    trading_day_buffer: int = 1
    """Additional buffer days to prevent same-day trading (default: 1).

    Note: Currently uses calendar days, not trading days, for simplicity.
    This is conservative and adds ~1-2 extra days of delay.
    """


def load_config() -> ReportDelayConfig:
    """Load report delay configuration from settings.toml."""
    settings_path = Path("config/settings.toml")

    if not settings_path.exists():
        # Return defaults if settings file doesn't exist
        return ReportDelayConfig()

    with settings_path.open("rb") as f:
        settings = tomllib.load(f)

    report_delays = settings.get("report_delays", {})
    return ReportDelayConfig(**report_delays)
