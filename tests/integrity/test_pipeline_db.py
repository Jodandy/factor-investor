"""Pipeline strategy on the real database.

1. Equivalence: a pipeline configured like top_n_factor_v1 picks exactly the
   same names (the framework adds no behaviour of its own).
2. Truncation: a pipeline using every component gives identical targets for T
   when every row dated after T, and every fundamental known after T, has been
   deleted (in a transaction that is rolled back).
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from typing import Any

import polars as pl
import pytest
from polars.testing import assert_frame_equal
from sqlalchemy import text
from sqlalchemy.orm import Session

import factor_investor.benchmarks.universe as benchmarks
import factor_investor.factors.snapshot as snapshot
import factor_investor.universe.fx as fx
import factor_investor.universe.listings as listings
import factor_investor.universe.queries as queries
from factor_investor.db import get_engine
from factor_investor.pipeline.config import StrategyConfig
from factor_investor.pipeline.strategy import PipelineStrategy
from factor_investor.pipeline.view import clear_caches
from factor_investor.strategy.registry import get_strategy

pytestmark = [pytest.mark.integration, pytest.mark.integrity]


def pipeline(
    universe: list[dict[str, Any]], blocks: list[dict[str, Any]], portfolio: dict[str, Any]
) -> PipelineStrategy:
    return PipelineStrategy(
        StrategyConfig.model_validate(
            {
                "id": "pipeline_test_v1",
                "hypothesis": "H0",
                "area": "SE",
                "rebalance": "monthly",
                "universe": universe,
                "scoring": {"blocks": blocks},
                "portfolio": portfolio,
            }
        )
    )


TOP_30 = {"component": "top_n_hysteresis_v1", "params": {"top_n": 30, "sell_rank": 1.0}}
EQUIVALENT = {
    "value": (
        pipeline(
            [{"component": "expression_v1", "params": {"expression": "pe_ratio > 0"}}],
            [
                {
                    "component": "percentile_v1",
                    "params": {"metric": "pe_ratio", "higher_is_better": False},
                    "weight": 1,
                }
            ],
            TOP_30,
        ),
        {"factor": "pe_ratio", "higher_is_better": False, "positive_only": True},
    ),
    "momentum": (
        pipeline(
            [],
            [
                {
                    "component": "percentile_v1",
                    "params": {"metric": "momentum_12_1m"},
                    "weight": 1,
                }
            ],
            TOP_30,
        ),
        {"factor": "momentum_12_1m", "higher_is_better": True, "positive_only": False},
    ),
}


@pytest.mark.parametrize("name", list(EQUIVALENT))
@pytest.mark.parametrize("as_of", [date(2009, 3, 31), date(2016, 6, 30), date(2025, 12, 31)])
def test_pipeline_reproduces_top_n_factor(name: str, as_of: date) -> None:
    strategy, factor_params = EQUIVALENT[name]
    reference = get_strategy("top_n_factor_v1").factory(
        {
            **factor_params,
            "area": "SE",
            "top_n": 30,
            "min_turnover": None,
            "rebalance": "monthly",
            "cost_bps": 10,
        }
    )
    expected = reference.generate_signals(as_of).holdings.sort("instrument_id")
    actual = strategy.generate_signals(as_of).holdings.sort("instrument_id")
    assert len(expected) == 30
    assert_frame_equal(actual, expected, check_exact=True)


T = date(2026, 6, 30)
FULL = pipeline(
    [
        {
            "component": "expression_v1",
            "params": {"expression": "turnover >= 500000 and (roic > 0 or market_cap > 1e10)"},
        }
    ],
    [
        {"component": "percentile_v1", "params": {"metric": "roic"}, "weight": 2},
        {
            "component": "percentile_v1",
            "params": {"metric": "ev_ebit", "higher_is_better": False, "non_positive_is_worst": True},
            "weight": 1,
        },
        {
            "component": "own_history_percentile_v1",
            "params": {"metric": "pe_ratio", "years": 5, "higher_is_better": False},
            "weight": 1,
        },
        {"component": "percentile_v1", "params": {"metric": "momentum_12_1m"}, "weight": 1},
    ],
    {"component": "top_n_hysteresis_v1", "params": {"top_n": 20, "sell_rank": 2.0}},
)
DELETES = [
    "DELETE FROM fundamental_metrics WHERE date > :t OR known_from > :t",
    "DELETE FROM price_metrics WHERE date > :t",
    "DELETE FROM universe_constituents WHERE date > :t",
    "DELETE FROM stock_prices WHERE date > :t",
    "DELETE FROM total_returns WHERE date > :t",
]


def full_pipeline_targets() -> pl.DataFrame:
    # current holdings exercise the hysteresis branch
    held = pl.DataFrame({"instrument_id": [1, 2, 3, 5, 8]}, schema={"instrument_id": pl.Int32})
    return FULL.generate_signals(T, held).holdings.sort("instrument_id")


@contextmanager
def database_truncated_at_t() -> Iterator[None]:
    connection = get_engine().connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    @contextmanager
    def shared_session() -> Iterator[Session]:
        yield session

    clear_caches()
    try:
        with pytest.MonkeyPatch.context() as patch:
            for module in (benchmarks, queries, fx, listings, snapshot):
                patch.setattr(module, "get_session", shared_session)
            for statement in DELETES:
                session.execute(text(statement), {"t": T})
            yield
    finally:
        clear_caches()
        session.close()
        transaction.rollback()
        connection.close()


def test_full_pipeline_identical_with_future_data_deleted() -> None:
    clear_caches()
    full = full_pipeline_targets()
    assert len(full) == 20

    with database_truncated_at_t():
        truncated = full_pipeline_targets()

    assert_frame_equal(full, truncated, check_exact=True)
