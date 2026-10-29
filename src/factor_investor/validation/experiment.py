"""Validate an experiment from its logged trials (no new backtests).

Loads the daily returns of an experiment's completed trials, compounds them to
months, and runs CSCV/PBO, the deflated Sharpe ratio of the best configuration
and block stability against the area's `equal_weight_v1`. The number of trials
for the deflated Sharpe ratio is the number of distinct configurations logged
for the whole hypothesis, failed ones included (conservative: configurations
on the same data are correlated, so the effective number is lower).
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
from sqlalchemy import select
from sqlalchemy.orm import Session

from factor_investor.search.models import Trial
from factor_investor.search.registry import BENCHMARKS_DIR, trial_counts
from factor_investor.validation.cscv import block_bounds, block_stability, cscv, deflated_sharpe

VALIDATION_DIR = Path("data/validation")


def monthly_returns(daily: pl.DataFrame) -> pl.DataFrame:
    """[month, r] compounded from [date, portfolio_return]."""
    return (
        daily.sort("date")
        .group_by_dynamic("date", every="1mo")
        .agg(((1 + pl.col("portfolio_return")).product() - 1).alias("r"))
        .rename({"date": "month"})
    )


@dataclass(frozen=True)
class ExperimentReturns:
    trial_ids: list[int]
    params: list[dict[str, Any]]
    months: list[Any]
    returns: np.ndarray  # (months, configurations)
    benchmark: np.ndarray  # (months,)


def load_experiment(
    session: Session, experiment: str, benchmarks_dir: Path = BENCHMARKS_DIR
) -> ExperimentReturns:
    trials = session.scalars(
        select(Trial)
        .where(Trial.experiment == experiment, Trial.status == "completed")
        .order_by(Trial.id)
    ).all()
    if len(trials) < 2:
        raise ValueError(f"Experiment {experiment!r} has {len(trials)} completed trials")
    # one row per configuration: the latest run (reruns are identical by the determinism check)
    latest: dict[str, Trial] = {t.config_hash: t for t in trials}
    chosen = sorted(latest.values(), key=lambda t: t.id)
    areas = {(t.area, t.from_date, t.to_date) for t in chosen}
    if len(areas) != 1:
        raise ValueError(f"Trials differ in area or period: {sorted(areas)}")
    area = chosen[0].area

    frame: pl.DataFrame | None = None
    for t in chosen:
        assert t.returns_path is not None
        m = monthly_returns(pl.read_parquet(t.returns_path)).rename({"r": f"t{t.id}"})
        frame = m if frame is None else frame.join(m, on="month")
    bench = monthly_returns(pl.read_parquet(benchmarks_dir / f"equal_weight_v1_{area}.parquet"))
    assert frame is not None
    # drop the first month, which starts with cash until the first fill
    frame = frame.join(bench.rename({"r": "benchmark"}), on="month").sort("month").slice(1)
    columns = [f"t{t.id}" for t in chosen]
    return ExperimentReturns(
        trial_ids=[t.id for t in chosen],
        params=[t.params for t in chosen],
        months=frame["month"].to_list(),
        returns=frame.select(columns).to_numpy(),
        benchmark=frame["benchmark"].to_numpy(),
    )


def validate_experiment(
    session: Session,
    experiment: str,
    n_blocks: int = 8,
    purge: int = 1,
    relative: bool = True,
    out_dir: Path = VALIDATION_DIR,
    benchmarks_dir: Path = BENCHMARKS_DIR,
) -> dict[str, Any]:
    data = load_experiment(session, experiment, benchmarks_dir)
    tested = data.returns - data.benchmark[:, None] if relative else data.returns
    hypothesis = session.scalars(
        select(Trial.hypothesis_id).where(Trial.experiment == experiment)
    ).first()
    counts = trial_counts(session, hypothesis)
    n_trials = int(counts["configurations"].sum())

    result = cscv(tested, n_blocks=n_blocks, purge=purge)
    stability = block_stability(data.returns, data.benchmark, n_blocks=n_blocks)
    sharpes = tested.mean(axis=0) / tested.std(axis=0, ddof=1)
    best = int(np.argmax(sharpes))
    dsr = deflated_sharpe(tested[:, best], n_trials, float(np.var(sharpes, ddof=1)))
    bounds = block_bounds(len(data.months), n_blocks)

    report: dict[str, Any] = {
        "experiment": experiment,
        "hypothesis_id": hypothesis,
        "months": [str(data.months[0]), str(data.months[-1]), len(data.months)],
        "blocks": [[str(data.months[s]), str(data.months[e - 1])] for s, e in bounds],
        "purge_months": purge,
        "returns": "excess over equal_weight_v1" if relative else "total",
        "configurations": len(data.trial_ids),
        "trials_for_hypothesis": n_trials,
        "cscv": {
            "combinations": result.combinations,
            "pbo": result.pbo,
            "prob_oos_loss": result.prob_oos_loss,
            "oos_sharpe_is_best_mean": float(result.oos_sharpe_of_is_best.mean()),
            "oos_sharpe_median_config_mean": float(result.oos_sharpe_median.mean()),
            "is_winner_counts": {
                str(trial): int(n)
                for trial, n in zip(data.trial_ids, result.best_is_counts, strict=True)
                if n
            },
        },
        "deflated_sharpe": {
            "trial_id": data.trial_ids[best],
            "params": data.params[best],
            "sharpe_monthly": dsr.sharpe,
            "sharpe_annualized": dsr.sharpe * np.sqrt(12),
            "expected_max_sharpe_monthly": dsr.expected_max_sharpe,
            "dsr": dsr.dsr,
            "skew": dsr.skew,
            "kurtosis": dsr.kurtosis,
        },
        "block_stability": [
            {
                "trial_id": trial,
                "params": params,
                "share_of_blocks_beaten": float(share),
                "excess_by_block": [float(x) for x in stability.excess_by_block[:, i]],
            }
            for i, (trial, params, share) in enumerate(
                zip(data.trial_ids, data.params, stability.share_of_blocks_beaten, strict=True)
            )
        ],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{experiment}.json").write_text(json.dumps(report, indent=2, default=str))
    return report
