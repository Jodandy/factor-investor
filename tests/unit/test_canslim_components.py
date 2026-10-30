"""Components for CANSLIM: history filter, percentile filter, stop loss from entry."""

from datetime import date

import polars as pl
import pytest

from factor_investor.components.base import build_component
from tests.unit.test_components import FakeView, ids
from tests.unit.test_history_stat import VIEW as HISTORY_VIEW

PCT_VIEW = FakeView({"momentum_12_1m": {i: float(i) for i in range(1, 11)}})


def kept(
    component: str, params: dict[str, object], view: FakeView, instruments: list[int]
) -> list[int]:
    return sorted(
        build_component(component, params).run(view, ids(*instruments))["instrument_id"].to_list()
    )  # type: ignore[attr-defined]


def test_percentile_filter_keeps_the_top_share() -> None:
    assert kept(
        "percentile_filter_v1",
        {"metric": "momentum_12_1m", "min_percentile": 0.8},
        PCT_VIEW,
        list(range(1, 11)),
    ) == [9, 10]
    # missing values never pass
    assert kept(
        "percentile_filter_v1",
        {"metric": "momentum_12_1m", "min_percentile": 0.0},
        PCT_VIEW,
        [1, 2, 99],
    ) == [1, 2]


def test_history_filter_on_median_growth() -> None:
    """From test_history_stat: 1 has steady 10% growth, 2 is erratic with a 0% median, 3 is too short."""
    params = {
        "metric": "revenue_growth_1y",
        "stat": "median",
        "years": 5,
        "min_observations": 3,
        "min_value": 0.05,
    }
    assert kept("history_filter_v1", params, HISTORY_VIEW, [1, 2, 3]) == [1]


def test_stop_loss_is_measured_from_entry() -> None:
    positions = pl.DataFrame(
        {
            "instrument_id": [1, 2, 3],
            "entry_price": [100.0, 100.0, 100.0],
            "high": [150.0, 100.0, 100.0],
            "price": [93.0, 92.0, 91.9],
        },
        schema={
            "instrument_id": pl.Int32,
            "entry_price": pl.Float64,
            "high": pl.Float64,
            "price": pl.Float64,
        },
    )
    assert build_component("stop_loss_v1", {"pct": 0.08}).run(positions) == {2, 3}  # type: ignore[attr-defined]


def test_invalid_params() -> None:
    with pytest.raises(ValueError):
        build_component("percentile_filter_v1", {"metric": "roic", "min_percentile": 1.5})
    with pytest.raises(ValueError):
        build_component("stop_loss_v1", {"pct": 0})
    assert date  # keep import used


def test_capped_equal_weight_leaves_cash_when_few_pass() -> None:
    ranked = pl.DataFrame(
        {"instrument_id": [1, 2, 3], "score": [0.9, 0.8, None]},
        schema={"instrument_id": pl.Int32, "score": pl.Float64},
    )
    capped = build_component("top_n_capped_v1", {"top_n": 10, "sell_rank": 1.0, "max_weight": 0.1})
    assert dict(capped.run(ranked, current=[]).rows()) == {1: 0.1, 2: 0.1}  # type: ignore[attr-defined]
    uncapped = build_component(
        "top_n_capped_v1", {"top_n": 10, "sell_rank": 1.0, "max_weight": 1.0}
    )
    assert dict(uncapped.run(ranked, current=[]).rows()) == {1: 0.5, 2: 0.5}  # type: ignore[attr-defined]
