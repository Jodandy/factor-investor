"""Tests for annualization in performance metrics.

The backtest calendar is the union of all markets, so a year can have ~365
rows (some markets trade on weekends) or ~252 rows. Annualization must
follow the actual date span, not assume 252 rows per year.
"""

from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest

from factor_investor.analytics.metrics import calculate_performance_metrics

START = date(2020, 1, 1)
END = date(2022, 1, 1)  # exactly 2 years (2020 is a leap year: 731 days)


def returns_frame(dates: list[date], returns: list[float]) -> pl.DataFrame:
    return pl.DataFrame({"date": dates, "portfolio_return": returns})


def calendar_days() -> list[date]:
    return [START + timedelta(days=i) for i in range((END - START).days + 1)]


def business_days() -> list[date]:
    return [d for d in calendar_days() if d.weekday() < 5]


@pytest.mark.parametrize("days", [calendar_days, business_days])
def test_cagr_follows_date_span(days) -> None:
    dates = days()
    daily = 1.21 ** (1 / (len(dates) - 1)) - 1  # +21% over exactly 2 years
    returns = [0.0] + [daily] * (len(dates) - 1)

    metrics = calculate_performance_metrics(returns_frame(dates, returns))

    assert metrics.total_return == pytest.approx(0.21)
    assert metrics.cagr == pytest.approx(0.10, abs=1e-3)


def test_volatility_ignores_non_trading_rows() -> None:
    """Zero-return weekend rows must not change annualized volatility much."""
    rng = np.random.default_rng(42)
    bdays = business_days()
    trading_returns = rng.normal(0, 0.01, len(bdays))
    by_day = dict(zip(bdays, trading_returns, strict=True))
    cdays = calendar_days()
    padded = [by_day.get(d, 0.0) for d in cdays]

    vol_business = calculate_performance_metrics(
        returns_frame(bdays, list(trading_returns))
    ).volatility
    vol_calendar = calculate_performance_metrics(returns_frame(cdays, padded)).volatility

    assert vol_calendar == pytest.approx(vol_business, rel=0.05)
    assert vol_business == pytest.approx(0.01 * np.sqrt(len(bdays) / 2), rel=0.1)
