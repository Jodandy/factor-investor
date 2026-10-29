"""Strategy components on a fake point-in-time view (no database)."""

from datetime import date

import polars as pl
import pytest

from factor_investor.components.base import COMPONENTS, build_component, register_component
from factor_investor.components.filters import ExpressionFilter
from factor_investor.components.portfolio import TopNHysteresis
from factor_investor.components.scores import OwnHistoryPercentile, Percentile

T = date(2024, 1, 31)


class FakeView:
    """Same interface as PointInTimeView, from in-memory data."""

    def __init__(
        self,
        metrics: dict[str, dict[int, float]],
        history: dict[str, list[tuple[int, date, float]]] | None = None,
        universe: dict[str, dict[int, float]] | None = None,
    ) -> None:
        self._metrics = metrics
        self._history = history or {}
        self._universe = universe or {}

    @property
    def as_of(self) -> date:
        return T

    def metric(self, name: str) -> pl.DataFrame:
        return pl.DataFrame(
            list(self._metrics[name].items()),
            schema={"instrument_id": pl.Int32, "value": pl.Float64},
            orient="row",
        )

    def metric_history(self, name: str, years: int) -> pl.DataFrame:  # noqa: ARG002
        return pl.DataFrame(
            self._history[name],
            schema={"instrument_id": pl.Int32, "date": pl.Date, "value": pl.Float64},
            orient="row",
        )

    def frame(self, instruments: pl.DataFrame, names: frozenset[str]) -> pl.DataFrame:
        frame = instruments.select(pl.col("instrument_id").cast(pl.Int32))
        for name in sorted(names):
            source = self._universe.get(name) or self._metrics[name]
            frame = frame.join(
                pl.DataFrame(
                    list(source.items()),
                    schema={"instrument_id": pl.Int32, name: pl.Float64},
                    orient="row",
                ),
                on="instrument_id",
                how="left",
            )
        return frame


def ids(*values: int) -> pl.DataFrame:
    return pl.DataFrame({"instrument_id": list(values)}, schema={"instrument_id": pl.Int32})


def scores(frame: pl.DataFrame) -> dict[int, float | None]:
    return dict(frame.select("instrument_id", "score").rows())


VIEW = FakeView(
    {
        "roic": {1: 0.20, 2: 0.05, 3: 0.12, 4: 0.30},
        "pe_ratio": {1: 10.0, 2: 30.0, 3: 12.0, 4: -5.0},
    },
    universe={"turnover": {1: 5e6, 2: 1e5, 3: 2e6, 4: 9e6}},
)


def test_expression_filter_keeps_matching_instruments() -> None:
    component = build_component("expression_v1", {"expression": "roic >= 0.1 and turnover > 1e6"})
    assert isinstance(component, ExpressionFilter)
    assert component.run(VIEW, ids(1, 2, 3, 4))["instrument_id"].to_list() == [1, 3, 4]


def test_percentile_scores_within_the_instruments() -> None:
    component = build_component("percentile_v1", {"metric": "roic", "higher_is_better": True})
    assert isinstance(component, Percentile)
    result = scores(component.run(VIEW, ids(1, 2, 3, 4)))
    assert result == {2: 0.125, 3: 0.375, 1: 0.625, 4: 0.875}
    lower = scores(
        build_component("percentile_v1", {"metric": "roic", "higher_is_better": False}).run(
            VIEW, ids(1, 2, 3, 4)
        )
    )
    assert lower[2] == 0.875


def test_percentile_non_positive_is_worst_and_missing_values() -> None:
    """A negative P/E is a loss: the worst valuation, not an unknown one (an
    unknown block is left out of the composite, which would favour losses)."""
    component = build_component(
        "percentile_v1",
        {"metric": "pe_ratio", "higher_is_better": False, "non_positive_is_worst": True},
    )
    result = scores(component.run(VIEW, ids(1, 2, 3, 4, 5)))
    assert result[4] == 0.0
    assert result[5] is None  # no value at all: unknown
    assert result[1] > result[3] > result[2] > 0


def test_own_history_percentile() -> None:
    """Cheap vs own history: P/E of 10 when it has usually been 15-20."""
    d = [date(2023, m, 28) for m in range(1, 13)]
    view = FakeView(
        {"pe_ratio": {1: 10.0, 2: 25.0}},
        history={
            "pe_ratio": [(1, x, 15.0 + i % 5) for i, x in enumerate(d)]
            + [(1, T, 10.0)]
            + [(2, x, 15.0) for x in d[:3]]
            + [(2, T, 25.0)]
        },
    )
    component = build_component(
        "own_history_percentile_v1",
        {"metric": "pe_ratio", "years": 5, "higher_is_better": False, "min_observations": 6},
    )
    assert isinstance(component, OwnHistoryPercentile)
    result = scores(component.run(view, ids(1, 2)))
    assert result[1] == 1.0  # lower than every earlier value
    assert result[2] is None  # too little history


def test_top_n_without_hysteresis() -> None:
    component = build_component("top_n_hysteresis_v1", {"top_n": 2, "sell_rank": 1.0})
    assert isinstance(component, TopNHysteresis)
    ranked = pl.DataFrame(
        {"instrument_id": [1, 2, 3, 4], "score": [0.9, 0.8, 0.7, None]},
        schema={"instrument_id": pl.Int32, "score": pl.Float64},
    )
    weights = component.run(ranked, current=[3, 4])
    assert dict(weights.rows()) == {1: 0.5, 2: 0.5}


def test_hysteresis_keeps_holdings_until_they_fall_far_enough() -> None:
    component = build_component("top_n_hysteresis_v1", {"top_n": 2, "sell_rank": 2.0})
    ranked = pl.DataFrame(
        {"instrument_id": [1, 2, 3, 4, 5], "score": [0.9, 0.8, 0.7, 0.6, 0.5]},
        schema={"instrument_id": pl.Int32, "score": pl.Float64},
    )
    # 4 is rank 4 = 2N: kept; 5 is rank 5 > 2N: sold; one slot left for the best new name
    weights = component.run(ranked, current=[4, 5])
    assert dict(weights.rows()) == {1: 0.5, 4: 0.5}


def test_ties_are_broken_by_instrument_id() -> None:
    component = build_component("top_n_hysteresis_v1", {"top_n": 2, "sell_rank": 1.0})
    ranked = pl.DataFrame(
        {"instrument_id": [9, 3, 5], "score": [0.5, 0.5, 0.5]},
        schema={"instrument_id": pl.Int32, "score": pl.Float64},
    )
    assert set(dict(component.run(ranked, current=[]).rows())) == {3, 5}


def test_params_are_validated() -> None:
    with pytest.raises(ValueError):
        build_component("percentile_v1", {"metric": "roic", "unknown": 1})
    with pytest.raises(ValueError):
        build_component("top_n_hysteresis_v1", {"top_n": 0, "sell_rank": 1.0})
    with pytest.raises(KeyError):
        build_component("no_such_component_v1", {})


def test_component_ids_must_be_versioned_and_unique() -> None:
    with pytest.raises(ValueError, match="_v<N>"):

        @register_component
        class Unversioned(ExpressionFilter):
            id = "unversioned"

    with pytest.raises(ValueError, match="already registered"):

        @register_component
        class Duplicate(ExpressionFilter):
            id = "expression_v1"

    assert {"expression_v1", "percentile_v1", "own_history_percentile_v1"} <= set(COMPONENTS)


def test_own_history_non_positive_is_worst() -> None:
    """A negative P/E is a loss, not cheap: the worst score."""
    d = [date(2023, m, 28) for m in range(1, 13)]
    view = FakeView(
        {"pe_ratio": {1: -4.0, 2: 10.0}},
        history={
            "pe_ratio": [(1, x, 15.0) for x in d]
            + [(2, x, 15.0) for x in d[:6]]
            + [(2, x, -3.0) for x in d[6:]]
        },
    )
    component = build_component(
        "own_history_percentile_v1",
        {
            "metric": "pe_ratio",
            "higher_is_better": False,
            "non_positive_is_worst": True,
            "min_observations": 6,
        },
    )
    result = scores(component.run(view, ids(1, 2)))
    assert result[1] == 0.0  # current value is a loss
    assert result[2] == 1.0  # compared with its six positive earlier values only
