"""Trial registry against the database, inside a transaction that is rolled back.

Synthetic prices and strategies (tests/integrity/synthetic.py); the registry
itself is real: rows, guards, determinism check and trial counts.
"""

from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from factor_investor.backtest.strategy import Strategy
from factor_investor.db import get_engine
from factor_investor.search.models import Trial
from factor_investor.search.registry import TrialSpec, run_trial, trial_counts
from factor_investor.strategy.registry import STRATEGIES, register_strategy
from tests.integrity.synthetic import (
    InMemoryEngine,
    ScheduledStrategy,
    equal_weight,
    random_walk_prices,
    trading_days,
)

DAYS = trading_days(120)
PRICES = random_walk_prices(10, 120, seed=3)
SCHEDULE = {DAYS[0]: equal_weight([0, 1, 2]), DAYS[60]: equal_weight([3, 4, 5])}


def scheduled(params: dict[str, Any]) -> Strategy:
    return ScheduledStrategy(SCHEDULE, cost_bps=params.get("cost_bps", 10))


@pytest.fixture(scope="module", autouse=True)
def test_strategy() -> Iterator[None]:
    register_strategy("registry_db_test_v1")(scheduled)
    yield
    del STRATEGIES["registry_db_test_v1"]


@pytest.fixture
def session() -> Iterator[Session]:
    connection = get_engine().connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    yield session
    session.close()
    transaction.rollback()
    connection.close()


def spec(**params: Any) -> TrialSpec:
    return TrialSpec(
        hypothesis_id="H0",
        experiment="registry_db_test",
        strategy_id="registry_db_test_v1",
        params={"cost_bps": 10, **params},
        area="SE",
        from_date=DAYS[0],
        to_date=DAYS[-1],
    )


def run(session: Session, tmp_path: Path, trial: TrialSpec, **kwargs: Any) -> Any:
    return run_trial(
        trial,
        engine=InMemoryEngine(PRICES),
        session=session,
        trials_dir=tmp_path,
        benchmarks_dir=tmp_path / "no_benchmarks",
        allow_dirty=True,
        **kwargs,
    )


pytestmark = pytest.mark.integration


def test_completed_trial_is_logged_with_returns(session: Session, tmp_path: Path) -> None:
    result = run(session, tmp_path, spec())

    trial = session.get(Trial, result.trial_id)
    assert trial is not None
    assert trial.status == "completed"
    assert trial.final_value == result.final_value
    assert trial.gross is False and trial.cost_bps == 10
    assert trial.price_filter.startswith("price_filter_v")
    assert set(trial.data_fingerprint) >= {"total_returns", "universe_constituents"}
    assert len(trial.code_commit) == 40
    assert trial.metrics is not None and "cagr" in trial.metrics
    assert result.returns_path is not None and result.returns_path.exists()


def test_repeated_configuration_must_give_the_same_result(session: Session, tmp_path: Path) -> None:
    first = run(session, tmp_path, spec())
    second = run(session, tmp_path, spec())
    assert first.final_value == second.final_value

    counts = trial_counts(session, "H0").filter(experiment="registry_db_test")
    assert counts["configurations"].to_list() == [1]
    assert counts["runs"].to_list() == [2]


def test_nondeterminism_is_caught(session: Session, tmp_path: Path) -> None:
    first = run(session, tmp_path, spec())
    trial = session.get(Trial, first.trial_id)
    assert trial is not None
    trial.final_value = first.final_value + 1  # as if the earlier run had given another result
    session.commit()

    with pytest.raises(RuntimeError, match="Nondeterministic"):
        run(session, tmp_path, spec())
    last = session.scalars(select(Trial).order_by(Trial.id.desc())).first()
    assert last is not None and last.status == "failed"


class Broken(ScheduledStrategy):
    def generate_signals(self, *_args: Any, **_kwargs: Any) -> Any:
        raise ValueError("strategy failure")


def test_failed_run_is_logged_and_counted(session: Session, tmp_path: Path) -> None:
    original = STRATEGIES["registry_db_test_v1"]
    STRATEGIES["registry_db_test_v1"] = type(original)(
        original.strategy_id, lambda _params: Broken(SCHEDULE), original.source_file
    )
    try:
        with pytest.raises(ValueError, match="strategy failure"):
            run(session, tmp_path, spec(variant="broken"))
    finally:
        STRATEGIES["registry_db_test_v1"] = original

    failed = session.scalars(select(Trial).where(Trial.status == "failed")).all()
    assert any("strategy failure" in (t.error or "") for t in failed)
    counts = trial_counts(session, "H0").filter(experiment="registry_db_test")
    assert counts["failed"].to_list() == [1]


def test_changed_source_of_a_logged_version_is_refused(session: Session, tmp_path: Path) -> None:
    first = run(session, tmp_path, spec())
    trial = session.get(Trial, first.trial_id)
    assert trial is not None
    trial.strategy_source_hash = "0" * 64  # as if logged with other source code
    session.commit()

    with pytest.raises(ValueError, match="_v2"):
        run(session, tmp_path, spec(top_n=5))


def test_gross_runs_need_the_flag_and_are_labelled(session: Session, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="gross"):
        run(session, tmp_path, spec(cost_bps=0))

    result = run(session, tmp_path, spec(cost_bps=0), allow_gross=True)
    trial = session.get(Trial, result.trial_id)
    assert trial is not None and trial.gross is True and trial.cost_bps == 0


def test_dirty_code_is_refused_by_default(tmp_path: Path) -> None:
    from factor_investor.search import registry

    original = registry.code_state
    registry.code_state = lambda: registry.CodeState("0" * 40, True)  # type: ignore[assignment]
    try:
        with pytest.raises(ValueError, match="commit"):
            run_trial(spec(), engine=InMemoryEngine(PRICES), trials_dir=tmp_path)
    finally:
        registry.code_state = original  # type: ignore[assignment]


def test_period_dates_are_stored(session: Session, tmp_path: Path) -> None:
    result = run(session, tmp_path, spec())
    trial = session.get(Trial, result.trial_id)
    assert trial is not None
    assert (trial.from_date, trial.to_date) == (DAYS[0], DAYS[-1])
    assert isinstance(trial.from_date, date)
