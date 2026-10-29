"""PricePanel: per-day lookups from an in-memory frame."""

from datetime import date

import polars as pl

from factor_investor.backtest.prices import PricePanel

D1, D2, D3 = date(2024, 1, 29), date(2024, 1, 30), date(2024, 1, 31)


def panel() -> PricePanel:
    return PricePanel.from_frame(
        pl.DataFrame(
            {
                "instrument_id": [1, 2, 1, 1],
                "date": [D1, D1, D2, D3],
                "price": [100.0, 50.0, 101.0, 102.0],
            }
        )
    )


def test_trading_days_are_sorted_union_of_dates() -> None:
    assert panel().trading_days == [D1, D2, D3]
    assert panel().trading_days_between(D2, D3) == [D2, D3]


def test_prices_on_returns_only_instruments_traded_that_day() -> None:
    day = panel().prices_on(D2)
    assert day.columns == ["instrument_id", "price"]
    assert day.rows() == [(1, 101.0)]


def test_prices_on_day_without_data_is_empty_with_schema() -> None:
    day = panel().prices_on(date(2024, 2, 1))
    assert day.is_empty()
    assert day.schema == pl.Schema({"instrument_id": pl.Int32, "price": pl.Float64})


def test_non_positive_prices_are_treated_as_missing() -> None:
    """A total return index of 0 (or below) is not a tradable price: the
    instrument has no price that day, but the day stays in the calendar."""
    p = PricePanel.from_frame(
        pl.DataFrame(
            {
                "instrument_id": [1, 2, 1],
                "date": [D1, D1, D2],
                "price": [100.0, 0.0, 0.0],
            }
        )
    )
    assert p.prices_on(D1).rows() == [(1, 100.0)]
    assert p.prices_on(D2).is_empty()
    assert p.trading_days == [D1, D2]
