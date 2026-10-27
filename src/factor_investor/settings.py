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
