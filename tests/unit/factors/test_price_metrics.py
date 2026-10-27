"""Tests for price-based metrics computed from a total return index series.

Lookbacks are in the instrument's own trading days: 1m = 21, 3m = 63,
6m = 126, 12m = 252. A return over N days compares the last value with the
value N rows earlier (index -1 vs -(N+1)).
"""

import polars as pl
import pytest

from factor_investor.factors.base_metrics import price_metrics_from_series


def series(n: int) -> pl.Series:
    """Strictly increasing TR index: value at row i is 100 + i."""
    return pl.Series([100.0 + i for i in range(n)])


def test_returns_use_exact_lookbacks() -> None:
    tr = series(300)
    m = price_metrics_from_series(tr)

    last = tr[-1]
    assert m["return_1m"] == pytest.approx(last / tr[-22] - 1)
    assert m["return_3m"] == pytest.approx(last / tr[-64] - 1)
    assert m["return_6m"] == pytest.approx(last / tr[-127] - 1)
    assert m["return_12m"] == pytest.approx(last / tr[-253] - 1)


def test_momentum_12_1_skips_most_recent_month() -> None:
    tr = series(300)
    m = price_metrics_from_series(tr)

    assert m["momentum_12_1m"] == pytest.approx(tr[-22] / tr[-253] - 1)
    assert m["momentum_12_1m"] != pytest.approx(m["return_12m"])


def test_short_history_omits_long_metrics() -> None:
    m = price_metrics_from_series(series(100))

    assert "return_1m" in m
    assert "return_3m" in m
    assert "return_6m" not in m
    assert "return_12m" not in m
    assert "momentum_12_1m" not in m


def test_drawdown_and_distance_to_high() -> None:
    values = [100.0] * 200 + [150.0] + [120.0] * 60
    m = price_metrics_from_series(pl.Series(values))

    assert m["max_drawdown_1y"] == pytest.approx(120 / 150 - 1)
    assert m["distance_52w_high"] == pytest.approx(120 / 150 - 1)
