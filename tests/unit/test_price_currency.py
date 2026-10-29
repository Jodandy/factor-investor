"""Converting the price panel to one currency with same-day (or earlier) rates."""

from datetime import date

import polars as pl
import pytest

from factor_investor.backtest.prices import convert_currency

D1, D2, D3 = date(2024, 1, 29), date(2024, 1, 30), date(2024, 1, 31)


def prices(*rows: tuple[int, date, float]) -> pl.DataFrame:
    return pl.DataFrame(
        rows,
        schema={"instrument_id": pl.Int32, "date": pl.Date, "price": pl.Float64},
        orient="row",
    )


CURRENCIES = pl.DataFrame(
    {"instrument_id": [1, 2, 3], "currency": ["EUR", "SEK", "USD"]},
    schema={"instrument_id": pl.Int32, "currency": pl.Utf8},
)


def rates(*rows: tuple[str, date, float]) -> pl.DataFrame:
    return pl.DataFrame(
        rows, schema={"currency": pl.Utf8, "date": pl.Date, "per_usd": pl.Float64}, orient="row"
    )


def converted(frame: pl.DataFrame, fx: pl.DataFrame, base: str) -> list[tuple[int, date, float]]:
    return sorted(convert_currency(frame, CURRENCIES, fx, base).rows())


def test_price_is_converted_through_usd_rates() -> None:
    fx = rates(("EUR", D1, 0.9), ("SEK", D1, 10.8))
    result = converted(prices((1, D1, 100.0)), fx, "SEK")
    assert result == [(1, D1, pytest.approx(100.0 * 10.8 / 0.9))]


def test_same_currency_is_unchanged() -> None:
    fx = rates(("SEK", D1, 10.8))
    assert converted(prices((2, D1, 123.45)), fx, "SEK") == [(2, D1, 123.45)]


def test_usd_needs_no_rate_of_its_own() -> None:
    fx = rates(("EUR", D1, 0.9))
    assert converted(prices((3, D1, 50.0)), fx, "EUR") == [(3, D1, pytest.approx(45.0))]
    assert converted(prices((1, D1, 45.0)), fx, "USD") == [(1, D1, pytest.approx(50.0))]


def test_rates_quoted_after_the_price_date_are_never_used() -> None:
    """A price on D2 uses the D1 rate even though a D3 rate exists."""
    fx = rates(("EUR", D1, 1.0), ("EUR", D3, 2.0), ("SEK", D1, 10.0), ("SEK", D3, 10.0))
    result = converted(prices((1, D2, 100.0), (1, D3, 100.0)), fx, "SEK")
    assert result == [(1, D2, pytest.approx(1000.0)), (1, D3, pytest.approx(500.0))]


def test_prices_without_a_recent_rate_are_dropped() -> None:
    fx = rates(("EUR", date(2024, 1, 1), 0.9), ("SEK", D1, 10.8))
    assert converted(prices((1, D1, 100.0)), fx, "SEK") == []


def test_extra_columns_are_kept() -> None:
    fx = rates(("SEK", D1, 10.8))
    frame = prices((2, D1, 10.0)).with_columns(pl.lit(500, dtype=pl.Int64).alias("volume"))
    assert convert_currency(frame, CURRENCIES, fx, "SEK").columns == [
        "instrument_id",
        "date",
        "price",
        "volume",
    ]
