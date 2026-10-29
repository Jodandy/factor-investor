"""Benchmarks use only data known on the signal date.

Computes the investable universe, trailing share counts and all three
benchmark weightings for T, then again inside a transaction where every
universe snapshot and price after T has been deleted. The results must be
identical. The transaction is rolled back; the database is not changed.
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
import factor_investor.universe.fx as fx
import factor_investor.universe.listings as listings
import factor_investor.universe.queries as queries
from factor_investor.benchmarks.universe import (
    SWEDEN,
    cap_weights,
    equal_weights,
    investable_universe,
    random_pick,
    trailing_median_shares,
)
from factor_investor.db import get_engine

T = date(2026, 6, 30)


def benchmark_inputs_and_weights() -> dict[str, pl.DataFrame]:
    universe = investable_universe(T, SWEDEN)
    shares = trailing_median_shares(T, universe["instrument_id"].to_list())
    return {
        "universe": universe,
        "shares": shares.sort("instrument_id"),
        "equal": equal_weights(universe),
        "cap": cap_weights(universe, shares).sort("instrument_id"),
        "random": random_pick(universe, 30, seed=1, as_of_date=T).sort("instrument_id"),
    }


@contextmanager
def database_truncated_at_t() -> Iterator[None]:
    """All universe and price queries see a database without rows after T."""
    connection = get_engine().connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    @contextmanager
    def shared_session() -> Iterator[Session]:
        yield session

    try:
        with pytest.MonkeyPatch.context() as patch:
            for module in (benchmarks, queries, fx, listings):
                patch.setattr(module, "get_session", shared_session)
            session.execute(text("DELETE FROM universe_constituents WHERE date > :t"), {"t": T})
            session.execute(text("DELETE FROM stock_prices WHERE date > :t"), {"t": T})
            yield
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.mark.integrity
@pytest.mark.integration
def test_benchmark_weights_identical_with_future_data_deleted() -> None:
    full = benchmark_inputs_and_weights()
    assert len(full["universe"]) > 300 and len(full["cap"]) > 300

    with database_truncated_at_t():
        truncated = benchmark_inputs_and_weights()

    for key, frame in full.items():
        assert_frame_equal(frame, truncated[key], check_exact=True)


@pytest.mark.integrity
@pytest.mark.integration
def test_truncation_is_real() -> None:
    """Guards the test above: inside the context, data after T is really gone."""
    with database_truncated_at_t():
        later = queries.get_universe(date(2026, 9, 30), is_eligible=True)
    assert later.is_empty()
    assert not queries.get_universe(date(2026, 9, 30), is_eligible=True).is_empty()


@pytest.mark.integrity
@pytest.mark.integration
def test_country_universe_holds_only_domestic_companies() -> None:
    """Nokia (ins_id 249), AstraZeneca and ABB trade in Stockholm in SEK but are
    foreign companies; only SE ISINs belong in the Swedish universe."""
    universe = investable_universe(T, SWEDEN)
    isin_country = benchmarks._instrument_markets().select("instrument_id", "isin_country")
    countries = universe.join(isin_country, on="instrument_id")["isin_country"].unique().to_list()
    assert countries == ["SE"]
    assert 249 not in investable_universe(date(2008, 12, 31), SWEDEN)["instrument_id"].to_list()
