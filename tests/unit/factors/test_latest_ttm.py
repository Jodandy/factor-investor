"""Tests for picking the latest trailing-twelve-month value per instrument."""

from datetime import date

import polars as pl

from factor_investor.factors.queries import select_latest_ttm


def pit_rows(rows: list[tuple[int, str, date, float]]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "instrument_id": [r[0] for r in rows],
            "period_type": [r[1] for r in rows],
            "period_end": [r[2] for r in rows],
            "value": [r[3] for r in rows],
        }
    )


def test_quarter_rows_are_never_used() -> None:
    """Quarter rows hold 3-month (or, for semi-annual reporters, 6-month)
    figures. A newer quarter must not override the latest r12."""
    df = pit_rows([
        (1, "r12", date(2024, 6, 30), 100.0),
        (1, "quarter", date(2024, 9, 30), 30.0),
    ])

    result = select_latest_ttm(df)

    assert result["value"].to_list() == [100.0]


def test_r12_preferred_over_year_for_same_period() -> None:
    df = pit_rows([
        (1, "year", date(2024, 12, 31), 90.0),
        (1, "r12", date(2024, 12, 31), 100.0),
    ])

    assert select_latest_ttm(df)["value"].to_list() == [100.0]


def test_newest_period_wins() -> None:
    df = pit_rows([
        (1, "year", date(2023, 12, 31), 80.0),
        (1, "r12", date(2024, 9, 30), 100.0),
        (2, "year", date(2024, 12, 31), 50.0),
        (2, "r12", date(2024, 6, 30), 40.0),
    ])

    result = select_latest_ttm(df).sort("instrument_id")

    assert result["value"].to_list() == [100.0, 50.0]


def test_instrument_with_only_quarters_is_dropped() -> None:
    df = pit_rows([(1, "quarter", date(2024, 9, 30), 30.0)])

    assert len(select_latest_ttm(df)) == 0
