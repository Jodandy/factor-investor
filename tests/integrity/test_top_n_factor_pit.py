"""top_n_factor_v1 uses only data known on the signal date.

Computes value and momentum targets for T, then again inside a transaction
where every row dated after T (metrics, universe snapshots, prices, total
returns) and every fundamental known after T has been deleted. The targets
must be identical. The transaction is rolled back; the database is not changed.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date

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
from factor_investor.strategy.registry import get_strategy

T = date(2026, 6, 30)
BASE = {"area": "SE", "top_n": 30, "min_turnover": None, "rebalance": "monthly", "cost_bps": 10}
CONFIGS = {
    "value": {**BASE, "factor": "pe_ratio", "higher_is_better": False, "positive_only": True},
    "momentum": {
        **BASE,
        "factor": "momentum_12_1m",
        "higher_is_better": True,
        "positive_only": False,
    },
}
DELETES = [
    "DELETE FROM fundamental_metrics WHERE date > :t OR known_from > :t",
    "DELETE FROM price_metrics WHERE date > :t",
    "DELETE FROM universe_constituents WHERE date > :t",
    "DELETE FROM stock_prices WHERE date > :t",
    "DELETE FROM total_returns WHERE date > :t",
]


def targets() -> dict[str, pl.DataFrame]:
    factory = get_strategy("top_n_factor_v1").factory
    return {
        name: factory(params).generate_signals(T).holdings.sort("instrument_id")
        for name, params in CONFIGS.items()
    }


@contextmanager
def database_truncated_at_t() -> Iterator[None]:
    connection = get_engine().connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    @contextmanager
    def shared_session() -> Iterator[Session]:
        yield session

    benchmarks.investable_universe.cache_clear()
    try:
        with pytest.MonkeyPatch.context() as patch:
            for module in (benchmarks, queries, fx, listings, snapshot):
                patch.setattr(module, "get_session", shared_session)
            for statement in DELETES:
                session.execute(text(statement), {"t": T})
            yield
    finally:
        benchmarks.investable_universe.cache_clear()
        session.close()
        transaction.rollback()
        connection.close()


@pytest.mark.integrity
@pytest.mark.integration
def test_targets_identical_with_future_data_deleted() -> None:
    full = targets()
    assert all(len(frame) == 30 for frame in full.values())

    with database_truncated_at_t():
        truncated = targets()

    for name in CONFIGS:
        assert_frame_equal(full[name], truncated[name], check_exact=True)


@pytest.mark.integrity
@pytest.mark.integration
def test_truncation_is_real() -> None:
    """Guards against a vacuous test: the deletes must remove data."""
    with database_truncated_at_t():
        later = snapshot.metric_snapshot("momentum_12_1m", date(2026, 7, 31))
        known_later = snapshot.metric_snapshot("pe_ratio", date(2026, 9, 30))
    assert later.is_empty() and known_later.is_empty()
    assert not snapshot.metric_snapshot("momentum_12_1m", date(2026, 7, 31)).is_empty()
