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
from factor_investor.pipeline.view import PointInTimeView, clear_caches
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
            "params": {
                "metric": "ev_ebit",
                "higher_is_better": False,
                "non_positive_is_worst": True,
            },
            "weight": 1,
        },
        {
            "component": "own_history_percentile_v1",
            "params": {"metric": "pe_ratio", "years": 5, "higher_is_better": False},
            "weight": 1,
        },
        {"component": "percentile_v1", "params": {"metric": "momentum_12_1m"}, "weight": 1},
        {
            "component": "history_stat_v1",
            "params": {"metric": "revenue_growth_1y", "stat": "share_positive", "years": 5},
            "weight": 1,
        },
    ],
    {"component": "top_n_hysteresis_v1", "params": {"top_n": 20, "sell_rank": 2.0}},
)
DELETES = [
    "DELETE FROM fundamentals_pit WHERE known_from > :t",
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


def test_history_cut_matches_the_dated_query() -> None:
    """The cached full history, cut at T, equals the history queried up to T."""
    from datetime import timedelta

    from factor_investor.benchmarks.universe import SWEDEN
    from factor_investor.factors.snapshot import metric_history
    from factor_investor.pipeline.view import PointInTimeView

    clear_caches()
    view = PointInTimeView(date(2016, 6, 30), SWEDEN)
    cut = view.metric_history("roic", 5)
    queried = metric_history(
        "roic", date(2016, 6, 30) - timedelta(days=round(365.25 * 5)), date(2016, 6, 30)
    )
    assert cut["date"].max() <= date(2016, 6, 30)
    assert_frame_equal(
        cut.sort("instrument_id", "date"), queried.sort("instrument_id", "date"), check_exact=True
    )


def test_failed_instruments_leave_the_universe_from_their_failure_date() -> None:
    from factor_investor.benchmarks.universe import SWEDEN
    from factor_investor.pipeline.view import PointInTimeView, excluded_instruments

    clear_caches()
    first, second = PointInTimeView(date(2016, 6, 30), SWEDEN).universe()["instrument_id"][:2]
    events = pl.DataFrame(
        {"instrument_id": [first, second], "date": [date(2016, 6, 30), date(2016, 7, 29)]},
        schema={"instrument_id": pl.Int32, "date": pl.Date},
    )
    with excluded_instruments(events):
        june = PointInTimeView(date(2016, 6, 30), SWEDEN).universe()["instrument_id"].to_list()
        july = PointInTimeView(date(2016, 7, 29), SWEDEN).universe()["instrument_id"].to_list()
    assert first not in june and second in june
    assert first not in july and second not in july
    after = PointInTimeView(date(2016, 7, 29), SWEDEN).universe()["instrument_id"].to_list()
    assert first in after and second in after  # only inside the scenario


def test_sector_field_in_expressions() -> None:
    """Börsdata sector 1 = financials and real estate, 10 = utilities."""
    from factor_investor.benchmarks.universe import SWEDEN
    from factor_investor.components.base import build_component
    from factor_investor.pipeline.view import PointInTimeView

    clear_caches()
    view = PointInTimeView(date(2016, 6, 30), SWEDEN)
    universe = view.universe()
    assert set(universe["sector_id"].drop_nulls().unique().to_list()) <= set(range(1, 11))
    kept = build_component(
        "expression_v1", {"expression": "sector_id != 1 and sector_id != 10"}
    ).run(view, universe.select("instrument_id"))
    sectors = universe.join(kept, on="instrument_id")["sector_id"]
    assert 0 < len(kept) < len(universe)
    assert not sectors.is_in([1.0, 10.0]).any()


def test_hold_rules_keep_held_names_that_no_longer_qualify_to_buy() -> None:
    """Buy at P/E < 8, hold while P/E < 12: a year later held names with
    P/E 8-12 stay (the plain strategy would sell them), P/E >= 12 are sold."""
    from factor_investor.pipeline.config import ComponentSpec

    first_date, second_date = date(2016, 3, 31), date(2017, 3, 31)
    clear_caches()
    base = pipeline(
        [{"component": "expression_v1", "params": {"expression": "pe_ratio > 0 and pe_ratio < 8"}}],
        [
            {
                "component": "percentile_v1",
                "params": {"metric": "pe_ratio", "higher_is_better": False},
                "weight": 1,
            }
        ],
        {"component": "top_n_hysteresis_v1", "params": {"top_n": 30, "sell_rank": 1.0}},
    )
    hold_rule = ComponentSpec(
        component="expression_v1", params={"expression": "pe_ratio > 0 and pe_ratio < 12"}
    )
    hold = PipelineStrategy(base.config.model_copy(update={"hold": [hold_rule]}))
    held = hold.generate_signals(first_date).holdings.select("instrument_id")
    second = set(hold.generate_signals(second_date, held).holdings["instrument_id"].to_list())
    plain = set(base.generate_signals(second_date, held).holdings["instrument_id"].to_list())

    pe = snapshot.metric_snapshot("pe_ratio", second_date)
    held_pe = held.join(pe, on="instrument_id", how="left")
    investable = set(
        PointInTimeView(second_date, benchmarks.SWEDEN).universe()["instrument_id"].to_list()
    )
    keep = (
        set(
            held_pe.filter((pl.col("value") > 0) & (pl.col("value") < 12))[
                "instrument_id"
            ].to_list()
        )
        & investable
    )
    drop = set(held_pe["instrument_id"].to_list()) - keep
    assert keep and drop
    assert keep <= second
    assert not drop & second
    assert keep - plain  # names only the hold rule kept


VALUATION = pipeline(
    [
        {"component": "expression_v1", "params": {"expression": "turnover >= 1000000"}},
        {"component": "relative_value_filter_v1", "params": {"band": "mid", "min_upside": 0.1}},
        {"component": "owner_earnings_irr_filter_v1", "params": {"min_irr": 0.08}},
    ],
    [
        {"component": "relative_value_score_v1", "params": {}, "weight": 1},
        {"component": "owner_earnings_irr_score_v1", "params": {}, "weight": 1},
    ],
    {"component": "top_n_capped_v1", "params": {"top_n": 20, "sell_rank": 1.0, "max_weight": 0.05}},
)


def test_valuation_pipeline_identical_with_future_data_deleted() -> None:
    """Relative value (own multiple history) and owner earnings (annual
    reports) use nothing published after T."""
    from factor_investor.pipeline.config import ComponentSpec

    strategy = PipelineStrategy(
        VALUATION.config.model_copy(
            update={
                "hold": [
                    ComponentSpec(
                        component="relative_value_filter_v1",
                        params={"band": "mid", "min_upside": 0.0},
                    )
                ]
            }
        )
    )
    held = pl.DataFrame({"instrument_id": [44, 237, 242]}, schema={"instrument_id": pl.Int32})
    clear_caches()
    full = strategy.generate_signals(T, held).holdings.sort("instrument_id")
    assert len(full) > 3
    with database_truncated_at_t():
        truncated = strategy.generate_signals(T, held).holdings.sort("instrument_id")
    assert_frame_equal(full, truncated, check_exact=True)
