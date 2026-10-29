"""Project-wide settings from config/settings.toml."""

import tomllib
from pathlib import Path
from typing import Any

SETTINGS_PATH = Path("config/settings.toml")


def _load() -> dict[str, Any]:
    with SETTINGS_PATH.open("rb") as f:
        return tomllib.load(f)


def execution_delay_days() -> int:
    """Trading days between signal and execution (CLAUDE.md invariant 2)."""
    delay = int(_load().get("backtest", {}).get("execution_delay_days", 1))
    if delay < 1:
        raise ValueError(f"execution_delay_days must be >= 1 in settings, got {delay}")
    return delay


def stock_instrument_types() -> list[int]:
    """Börsdata instrument types treated as stocks: synced with reports and
    eligible for the universe."""
    return list(_load()["instruments"]["stock_types"])


def price_only_instrument_types() -> list[int]:
    """Instrument types synced for prices only (benchmarks, FX), never eligible."""
    return list(_load()["instruments"]["price_only_types"])


def dividend_fallback_lag_days() -> tuple[int, dict[int, int]]:
    """(default, per country id) days from report known_from to an estimated
    ex-date, for dividends without a dividend calendar entry."""
    section = _load()["dividends"]
    by_country = {int(k): int(v) for k, v in section["fallback_lag_days_by_country"].items()}
    return int(section["fallback_lag_days"]), by_country
