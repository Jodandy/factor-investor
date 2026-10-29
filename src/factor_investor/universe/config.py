"""Configuration for universe construction."""

import tomllib
from pathlib import Path

from pydantic import BaseModel, Field


class UniverseConfig(BaseModel):
    """Universe construction configuration.

    Philosophy: Universe includes ALL instruments with sufficient data quality.
    NO geographic filters, NO market cap/liquidity cutoffs.
    Strategies apply their own selection criteria at backtest time.
    """

    # Opt-in minimum price (local currency). Off by default: prices are
    # split-adjusted, so a threshold excludes stocks based on later splits.
    min_price: float | None = None

    # Instrument names with these endings are excluded: Swedish property
    # companies' D shares are preference-like (capped upside)
    exclude_name_suffixes: list[str] = Field(default_factory=lambda: [" D"])

    # Snapshot price: last close on or before the snapshot date, at most this
    # many calendar days old (weekends, holidays)
    max_price_age_days: int = 7

    # Countries whose listings are excluded entirely (e.g. Germany: mostly
    # secondary listings of foreign companies; see DECISIONS 2026-10-28)
    exclude_country_ids: list[int] = Field(default_factory=list)

    # Liquidity bucket thresholds (for classification, not exclusion)
    liquidity_bucket_thresholds: list[float] = Field(
        default_factory=lambda: [10_000_000.0, 1_000_000.0, 100_000.0, 10_000.0]
    )


class CorporateEventsConfig(BaseModel):
    """Corporate events configuration."""

    default_delisting_recovery: float = 1.0  # Optimistic assumption


def load_universe_config() -> UniverseConfig:
    """Load universe configuration from settings.toml.

    Returns:
        UniverseConfig with values from file or defaults
    """
    config_path = Path("config/settings.toml")
    if not config_path.exists():
        return UniverseConfig()

    with config_path.open("rb") as f:
        data = tomllib.load(f)

    universe_data = data.get("universe", {})
    return UniverseConfig(**universe_data)


def load_corporate_events_config() -> CorporateEventsConfig:
    """Load corporate events configuration from settings.toml.

    Returns:
        CorporateEventsConfig with values from file or defaults
    """
    config_path = Path("config/settings.toml")
    if not config_path.exists():
        return CorporateEventsConfig()

    with config_path.open("rb") as f:
        data = tomllib.load(f)

    events_data = data.get("corporate_events", {})
    return CorporateEventsConfig(**events_data)
