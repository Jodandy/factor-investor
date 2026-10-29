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


def match_controls(params: list[dict[str, Any]], controls: dict[int, dict[str, Any]]) -> list[int]:
    """For each configuration, the control trial whose parameters all equal the
    configuration's values for the same keys (e.g. the same rebalancing)."""
    matched = []
    for p in params:
        hits = [
            trial_id
            for trial_id, c in controls.items()
            if all(k in p and p[k] == v for k, v in c.items())
        ]
        if not hits:
            raise ValueError(f"no control matches {p}")
        if len(hits) > 1:
            raise ValueError(f"several controls match {p}: {hits}")
        matched.append(hits[0])
    return matched


@dataclass(frozen=True)
class ExperimentReturns:
    trial_ids: list[int]
    params: list[dict[str, Any]]
    months: list[Any]
    returns: np.ndarray  # (months, configurations)
    benchmark: np.ndarray  # (months, configurations): each configuration's benchmark


def _completed(session: Session, experiment: str) -> list[Trial]:
    trials = session.scalars(
        select(Trial)
        .where(Trial.experiment == experiment, Trial.status == "completed")
        .order_by(Trial.id)
    ).all()
    # one per configuration: the latest run (reruns are identical by the determinism check)
    latest: dict[str, Trial] = {t.config_hash: t for t in trials}
    return sorted(latest.values(), key=lambda t: t.id)


def load_experiment(
    session: Session,
    experiment: str,
    benchmarks_dir: Path = BENCHMARKS_DIR,
    control: str | None = None,
) -> ExperimentReturns:
    """Monthly returns of the experiment's configurations and of each one's
    benchmark: the area's equal_weight_v1, or the matching trial of the
    `control` experiment (`match_controls`)."""
    chosen = _completed(session, experiment)
    if len(chosen) < 2:
        raise ValueError(f"Experiment {experiment!r} has {len(chosen)} completed configurations")
    areas = {
        (t.area, t.from_date, t.to_date, json.dumps(t.scenario, sort_keys=True)) for t in chosen
    }
    if len(areas) != 1:
        raise ValueError(f"Trials differ in area, period or scenario: {sorted(areas)}")
    area = chosen[0].area

    def monthly(trial: Trial, name: str) -> pl.DataFrame:
        assert trial.returns_path is not None
        return monthly_returns(pl.read_parquet(trial.returns_path)).rename({"r": name})

    frame: pl.DataFrame | None = None
    for t in chosen:
        m = monthly(t, f"t{t.id}")
        frame = m if frame is None else frame.join(m, on="month")
    assert frame is not None
    if control is None:
        bench = monthly_returns(pl.read_parquet(benchmarks_dir / f"equal_weight_v1_{area}.parquet"))
        frame = frame.join(bench.rename({"r": "b"}), on="month")
        bench_columns = ["b"] * len(chosen)
    else:
        controls = {c.id: c for c in _completed(session, control)}
        if {
            (c.area, c.from_date, c.to_date, json.dumps(c.scenario, sort_keys=True))
            for c in controls.values()
        } != areas:
            raise ValueError(f"Control {control!r} differs in area, period or scenario")
        matched = match_controls(
            [t.params for t in chosen], {i: c.params for i, c in controls.items()}
        )
        for trial_id in sorted(set(matched)):
            frame = frame.join(monthly(controls[trial_id], f"c{trial_id}"), on="month")
        bench_columns = [f"c{i}" for i in matched]
    # drop the first month, which starts with cash until the first fill
    frame = frame.sort("month").slice(1)
    return ExperimentReturns(
        trial_ids=[t.id for t in chosen],
        params=[t.params for t in chosen],
        months=frame["month"].to_list(),
        returns=frame.select([f"t{t.id}" for t in chosen]).to_numpy(),
        benchmark=np.column_stack([frame[c].to_numpy() for c in bench_columns]),
    )


def validate_experiment(
    session: Session,
    experiment: str,
    n_blocks: int = 8,
    purge: int = 1,
    relative: bool = True,
    control: str | None = None,
    out_dir: Path = VALIDATION_DIR,
    benchmarks_dir: Path = BENCHMARKS_DIR,
) -> dict[str, Any]:
    data = load_experiment(session, experiment, benchmarks_dir, control)
    tested = data.returns - data.benchmark if relative else data.returns
    benchmark_name = f"control experiment {control}" if control else "equal_weight_v1"
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
        "benchmark": benchmark_name,
        "returns": f"excess over {benchmark_name}" if relative else "total",
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
