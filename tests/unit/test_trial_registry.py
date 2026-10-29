"""Trial registry rules that need no database (CLAUDE.md invariants 5, 6, 9)."""

from datetime import date
from pathlib import Path

import polars as pl
import pytest

from factor_investor.search.registry import (
    TrialSpec,
    check_source_hash,
    config_hash,
    known_hypotheses,
)
from factor_investor.strategy.registry import STRATEGIES, register_strategy


def spec(**changes: object) -> TrialSpec:
    values: dict[str, object] = {
        "hypothesis_id": "H0",
        "experiment": "registry_test",
        "strategy_id": "test_strategy_v1",
        "params": {"top_n": 30, "factor": "earnings_yield"},
        "area": "SE",
        "from_date": date(2008, 1, 1),
        "to_date": date(2026, 10, 27),
    }
    values.update(changes)
    return TrialSpec(**values)  # type: ignore[arg-type]


def test_config_hash_ignores_key_order_and_labels() -> None:
    """The hash identifies what was run, not how it was labelled: the same
    configuration in another experiment is the same configuration."""
    a = spec(params={"top_n": 30, "factor": "earnings_yield"})
    b = spec(params={"factor": "earnings_yield", "top_n": 30}, experiment="other", stage="final")
    assert config_hash(a) == config_hash(b)
    assert len(config_hash(a)) == 64


@pytest.mark.parametrize(
    "change",
    [
        {"params": {"top_n": 31, "factor": "earnings_yield"}},
        {"strategy_id": "test_strategy_v2"},
        {"area": "NO"},
        {"from_date": date(2009, 1, 1)},
        {"to_date": date(2026, 1, 1)},
    ],
)
def test_config_hash_changes_with_anything_that_changes_the_run(change: dict[str, object]) -> None:
    assert config_hash(spec(**change)) != config_hash(spec())


def test_hypotheses_come_from_the_hypotheses_document() -> None:
    assert {"H0", "H1", "H2", "H3", "H4"} <= known_hypotheses()


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"hypothesis_id": "H99"}, "hypothesis"),
        ({"strategy_id": "unversioned"}, "_v<N>"),
        ({"experiment": ""}, "experiment"),
        ({"area": "XX"}, "area"),
        ({"from_date": date(2027, 1, 1)}, "from_date"),
    ],
)
def test_invalid_specs_are_refused(change: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        spec(**change).validate()


def test_params_must_be_json() -> None:
    with pytest.raises(ValueError, match="JSON"):
        spec(params={"when": date(2020, 1, 1)}).validate()


def test_changed_source_of_a_used_version_is_refused() -> None:
    check_source_hash("value_ey_v1", "abc", known=set())
    check_source_hash("value_ey_v1", "abc", known={"abc"})
    with pytest.raises(ValueError, match="_v2"):
        check_source_hash("value_ey_v1", "def", known={"abc"})


def test_strategy_ids_must_be_versioned_and_unique() -> None:
    with pytest.raises(ValueError, match="_v<N>"):
        register_strategy("no_version")
    with pytest.raises(ValueError, match="_v<N>"):
        register_strategy("Value_v1")

    @register_strategy("registry_unit_test_v1")
    def factory(params: dict[str, object]) -> None:  # pragma: no cover
        raise NotImplementedError

    try:
        assert STRATEGIES["registry_unit_test_v1"].source_hash()
        with pytest.raises(ValueError, match="already registered"):
            register_strategy("registry_unit_test_v1")(factory)
    finally:
        del STRATEGIES["registry_unit_test_v1"]


def monthly_returns(monthly: float, months: int = 24) -> pl.DataFrame:

    days = [date(2020 + m // 12, m % 12 + 1, 15) for m in range(months)]
    return pl.DataFrame({"date": days, "portfolio_return": [monthly] * months})


def test_relative_metrics() -> None:
    from factor_investor.search.registry import relative_metrics

    result = relative_metrics(monthly_returns(0.02), monthly_returns(0.01))
    assert result["months"] == 24
    assert result["excess_cagr"] == pytest.approx(1.02**12 - 1.01**12)
    assert result["tracking_error"] == pytest.approx(0.0, abs=1e-12)


def test_benchmark_comparison_ranks_against_random_portfolios(tmp_path: Path) -> None:
    from factor_investor.search.registry import benchmark_comparison

    monthly_returns(0.01).write_parquet(tmp_path / "equal_weight_v1_SE.parquet")
    random_dir = tmp_path / "random_pick_v1_SE_k30"
    random_dir.mkdir()
    for seed, r in enumerate([0.0, 0.005, 0.01, 0.015, 0.03], start=1):
        monthly_returns(r).write_parquet(random_dir / f"seed_{seed:03d}.parquet")

    result = benchmark_comparison(monthly_returns(0.012), "SE", tmp_path)
    assert result["equal_weight_v1"]["excess_cagr"] > 0
    assert "cap_weight_v1" not in result
    assert result["random_pick_v1_SE_k30"]["runs"] == 5
    assert result["random_pick_v1_SE_k30"]["percentile"] == pytest.approx(0.6)
