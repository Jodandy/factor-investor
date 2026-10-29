"""top_n_factor_v1 selection rules (pure functions, no database)."""

from datetime import date

import polars as pl
import pytest

from factor_investor.strategy.registry import get_strategy
from factor_investor.strategy.top_n_factor import (
    PARAMS,
    TopNFactorStrategy,
    rebalancing_dates,
    select_top_n,
)


def universe(rows: list[tuple[int, float | None]], to_base: float = 1.0) -> pl.DataFrame:
    """(instrument_id, median_turnover_60d)."""
    return pl.DataFrame(
        rows, schema={"instrument_id": pl.Int32, "median_turnover_60d": pl.Float64}, orient="row"
    ).with_columns(pl.lit(to_base).alias("to_base"))


def values(rows: list[tuple[int, float]]) -> pl.DataFrame:
    return pl.DataFrame(rows, schema={"instrument_id": pl.Int32, "value": pl.Float64}, orient="row")


def chosen(weights: pl.DataFrame) -> dict[int, float]:
    return dict(weights.rows())


U = universe([(i, 1e6) for i in range(1, 7)])
V = values([(1, 5.0), (2, -3.0), (3, 12.0), (4, 8.0), (5, 20.0), (99, 1.0)])


def test_lowest_values_equal_weight() -> None:
    weights = select_top_n(
        U, V, top_n=2, higher_is_better=False, positive_only=False, min_turnover=None
    )
    assert chosen(weights) == {2: 0.5, 1: 0.5}


def test_positive_only_drops_negative_values() -> None:
    """P/E: a negative P/E is a loss, not a cheap stock."""
    weights = select_top_n(
        U, V, top_n=2, higher_is_better=False, positive_only=True, min_turnover=None
    )
    assert chosen(weights) == {1: 0.5, 4: 0.5}


def test_highest_values() -> None:
    weights = select_top_n(
        U, V, top_n=2, higher_is_better=True, positive_only=False, min_turnover=None
    )
    assert chosen(weights) == {5: 0.5, 3: 0.5}


def test_only_the_investable_universe_is_ranked() -> None:
    """Instrument 99 has a value but is not in the universe; 6 is in the
    universe but has no value."""
    weights = select_top_n(
        U, V, top_n=10, higher_is_better=True, positive_only=False, min_turnover=None
    )
    assert set(chosen(weights)) == {1, 2, 3, 4, 5}


def test_min_turnover_in_the_area_currency() -> None:
    u = universe([(1, 100.0), (3, 1000.0), (5, None)], to_base=10.0)
    weights = select_top_n(
        u, V, top_n=5, higher_is_better=True, positive_only=False, min_turnover=5000.0
    )
    assert set(chosen(weights)) == {3}


def test_ties_are_broken_by_instrument_id() -> None:
    v = values([(4, 1.0), (2, 1.0), (3, 1.0)])
    weights = select_top_n(
        U, v, top_n=2, higher_is_better=True, positive_only=False, min_turnover=None
    )
    assert set(chosen(weights)) == {2, 3}


def test_rebalancing_dates() -> None:
    monthly = rebalancing_dates("monthly", date(2024, 1, 1), date(2024, 6, 30))
    quarterly = rebalancing_dates("quarterly", date(2024, 1, 1), date(2024, 12, 31))
    assert len(monthly) == 6
    assert [d.month for d in quarterly] == [3, 6, 9, 12]
    with pytest.raises(ValueError):
        rebalancing_dates("weekly", date(2024, 1, 1), date(2024, 6, 30))


FULL = {
    "area": "SE",
    "factor": "pe_ratio",
    "higher_is_better": False,
    "positive_only": True,
    "top_n": 30,
    "min_turnover": None,
    "rebalance": "monthly",
    "cost_bps": 10,
}


def test_registered_factory_needs_every_parameter() -> None:
    """The logged parameters are then always complete."""
    assert set(FULL) == set(PARAMS)
    factory = get_strategy("top_n_factor_v1").factory
    strategy = factory(FULL)
    assert isinstance(strategy, TopNFactorStrategy)
    assert strategy.transaction_cost_bps == 10
    with pytest.raises(ValueError, match="missing"):
        factory({k: v for k, v in FULL.items() if k != "top_n"})
    with pytest.raises(ValueError, match="unknown"):
        factory({**FULL, "topn": 30})
