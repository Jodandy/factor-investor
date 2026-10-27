"""Windowed transformations need history covering the whole window.

Base metrics are sampled monthly, so "at least N data points" let a 5-year
mean be computed from 5 months of history.
"""

from datetime import date

import polars as pl
import pytest

from factor_investor.factors import transformations as t

AS_OF = date(2024, 12, 31)


def monthly(n_months: int) -> pl.DataFrame:
    dates = []
    y, m = AS_OF.year, AS_OF.month
    for _ in range(n_months):
        dates.append(date(y, m, 28))
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    dates.reverse()
    dates[-1] = AS_OF
    return pl.DataFrame(
        {
            "instrument_id": [1] * n_months,
            "date": dates,
            "value": [1.0 + 0.01 * i for i in range(n_months)],
        }
    )


TRANSFORMS = [
    t.transform_mean,
    t.transform_median,
    t.transform_min,
    t.transform_max,
    t.transform_trend,
    t.transform_stability_cv,
    t.transform_percentile_history,
]


def value_at_as_of(fn, df: pl.DataFrame, years: int) -> pl.DataFrame:
    result = fn(df, years)
    return result.filter(pl.col("date") == AS_OF) if len(result) else result


@pytest.mark.parametrize("fn", TRANSFORMS)
def test_short_history_gives_no_value(fn) -> None:
    assert len(value_at_as_of(fn, monthly(12), years=5)) == 0


@pytest.mark.parametrize("fn", TRANSFORMS)
def test_full_history_gives_value(fn) -> None:
    assert len(value_at_as_of(fn, monthly(61), years=5)) == 1
