"""history_stat_v1: a statistic over a metric's annual history, as a percentile."""

from datetime import date

import pytest

from factor_investor.components.base import build_component
from factor_investor.components.history_stat import annual_dates
from tests.unit.test_components import FakeView, ids, scores

T = date(2024, 1, 31)


def test_annual_dates_are_the_same_month_each_year() -> None:
    dates = [date(2021, 1, 29), date(2021, 7, 30), date(2022, 1, 31), date(2023, 1, 31), T]
    assert annual_dates(dates, T) == [date(2021, 1, 29), date(2022, 1, 31), date(2023, 1, 31), T]
    assert annual_dates(dates, T, years=2) == [date(2023, 1, 31), T]


def history(values: dict[int, list[float]]) -> list[tuple[int, date, float]]:
    """Annual values ending at T (oldest first), plus off-cycle months that must be ignored."""
    rows = []
    for ins, series in values.items():
        for i, value in enumerate(reversed(series)):
            rows.append((ins, date(T.year - i, 1, 28 if T.year - i != 2024 else 31), value))
            rows.append((ins, date(T.year - i - 1, 7, 31), 99.0))  # off-cycle: ignored
    return rows


VIEW = FakeView(
    {"revenue_growth_1y": {1: 0.1, 2: 0.5, 3: 0.0}},
    history={
        "revenue_growth_1y": history(
            {
                1: [0.08, 0.10, 0.12, 0.09, 0.10],  # steady 10%
                2: [-0.2, 0.9, -0.1, 0.0, 0.5],  # erratic, one big year
                3: [0.05, 0.04],  # too short
            }
        )
    },
)


def run(stat: str, **extra: object) -> dict[int, float | None]:
    params = {"metric": "revenue_growth_1y", "stat": stat, "years": 5, "min_observations": 3}
    return scores(build_component("history_stat_v1", {**params, **extra}).run(VIEW, ids(1, 2, 3)))


def test_median_growth() -> None:
    result = run("median")
    assert result[1] > result[2]  # median 0.10 vs 0.0
    assert result[3] is None  # two annual values < min_observations


def test_consistency_is_the_share_of_positive_years() -> None:
    result = run("share_positive")
    assert result[1] > result[2]  # 5/5 vs 2/5


def test_lower_is_better() -> None:
    result = run("median", higher_is_better=False)
    assert result[2] > result[1]


def test_invalid_stat_is_refused() -> None:
    with pytest.raises(ValueError):
        build_component(
            "history_stat_v1", {"metric": "roic", "stat": "max", "years": 5, "min_observations": 3}
        )
