"""Corrupted instruments management.

This module handles instruments with known data quality issues that should
be excluded from backtests and analysis.

Common issues include:
- Reverse splits not properly adjusted
- Corporate actions missing
- Delisting/bankruptcy events
- Data provider errors
"""

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


_CORRUPTED_INSTRUMENTS_CACHE: set[int] | None = None


def load_corrupted_instruments() -> set[int]:
    """Load list of corrupted instrument IDs from config.

    Returns:
        Set of instrument IDs to exclude

    Example:
        >>> corrupted = load_corrupted_instruments()
        >>> if instrument_id in corrupted:
        ...     # Skip this instrument
    """
    global _CORRUPTED_INSTRUMENTS_CACHE

    if _CORRUPTED_INSTRUMENTS_CACHE is not None:
        return _CORRUPTED_INSTRUMENTS_CACHE

    config_path = Path("config/corrupted_instruments.yaml")

    if not config_path.exists():
        logger.warning(f"Corrupted instruments config not found: {config_path}")
        _CORRUPTED_INSTRUMENTS_CACHE = set()
        return _CORRUPTED_INSTRUMENTS_CACHE

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    corrupted_ids = set()

    if config and "corrupted_instruments" in config:
        for entry in config["corrupted_instruments"]:
            instrument_id = entry.get("instrument_id")
            if instrument_id:
                corrupted_ids.add(instrument_id)
                logger.info(
                    f"Marking instrument {instrument_id} ({entry.get('name', 'Unknown')}) "
                    f"as corrupted: {entry.get('issue', 'No issue specified')}"
                )

    logger.info(f"Loaded {len(corrupted_ids)} corrupted instruments")
    _CORRUPTED_INSTRUMENTS_CACHE = corrupted_ids
    return _CORRUPTED_INSTRUMENTS_CACHE


def is_corrupted(instrument_id: int) -> bool:
    """Check if an instrument is marked as corrupted.

    Args:
        instrument_id: Instrument ID to check

    Returns:
        True if instrument should be excluded

    Example:
        >>> if is_corrupted(61873):
        ...     print("Synergy CHC Corp - known data issue")
    """
    corrupted = load_corrupted_instruments()
    return instrument_id in corrupted


def filter_corrupted(instrument_ids: list[int]) -> list[int]:
    """Filter out corrupted instruments from a list.

    Args:
        instrument_ids: List of instrument IDs

    Returns:
        Filtered list with corrupted instruments removed

    Example:
        >>> clean_ids = filter_corrupted([61873, 12345, 67890])
        >>> # 61873 (Synergy CHC) will be filtered out
    """
    corrupted = load_corrupted_instruments()
    filtered = [id for id in instrument_ids if id not in corrupted]

    num_filtered = len(instrument_ids) - len(filtered)
    if num_filtered > 0:
        logger.debug(f"Filtered out {num_filtered} corrupted instruments")

    return filtered


def add_corrupted_instrument(
    instrument_id: int,
    name: str,
    issue: str,
    isin: str | None = None,
    notes: str | None = None,
) -> None:
    """Add an instrument to the corrupted list.

    Args:
        instrument_id: Instrument ID
        name: Instrument name
        issue: Description of the issue
        isin: Optional ISIN code
        notes: Optional additional notes

    Example:
        >>> add_corrupted_instrument(
        ...     61873,
        ...     "Synergy CHC Corp",
        ...     "Extreme price spike - likely reverse split",
        ...     notes="689x price increase in 4 months"
        ... )
    """
    from datetime import date

    config_path = Path("config/corrupted_instruments.yaml")

    # Load existing config
    if config_path.exists():
        with open(config_path, "r") as f:
            config = yaml.safe_load(f) or {}
    else:
        config = {}

    if "corrupted_instruments" not in config:
        config["corrupted_instruments"] = []

    # Check if already exists
    existing_ids = {entry.get("instrument_id") for entry in config["corrupted_instruments"]}
    if instrument_id in existing_ids:
        logger.warning(f"Instrument {instrument_id} already in corrupted list")
        return

    # Add new entry
    new_entry = {
        "instrument_id": instrument_id,
        "name": name,
        "isin": isin,
        "issue": issue,
        "date_identified": date.today().isoformat(),
    }
    if notes:
        new_entry["notes"] = notes

    config["corrupted_instruments"].append(new_entry)

    # Save
    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    logger.info(f"Added instrument {instrument_id} ({name}) to corrupted list")

    # Invalidate cache
    global _CORRUPTED_INSTRUMENTS_CACHE
    _CORRUPTED_INSTRUMENTS_CACHE = None
