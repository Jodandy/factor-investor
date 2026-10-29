"""Trial registry: every research backtest is run and logged through here.

`run_trial` is the only way to run a research backtest (CLAUDE.md invariant
5). It logs what was run (hypothesis, experiment, strategy id, parameters,
source hash), on which data (fingerprint of the input tables, price filter)
and code (git commit), and the result (metrics, comparison with the area's
benchmarks and random portfolios, daily returns on disk). Trial counts per
experiment and hypothesis feed deflated Sharpe and PBO.

Guards:
- a strategy version whose source changed after it was logged is refused
  (make `_v2`, invariant 9);
- costs off needs `allow_gross=True`, and the trial is labelled gross
  (invariant 6);
- uncommitted changes under src/ or config/ are refused unless
  `allow_dirty=True` (tests), so every trial can be rebuilt from its commit;
- a repeated configuration on the same data and code must give the same
  final value (invariant 7).
"""

import hashlib
import json
import logging
import math
import re
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from functools import cache, lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from factor_investor.backtest.engine import BacktestEngine
from factor_investor.backtest.prices import PRICE_FILTER_ID
from factor_investor.db import get_session
from factor_investor.search.models import Trial
from factor_investor.strategy.registry import VERSIONED_ID, get_strategy

logger = logging.getLogger(__name__)

TRIALS_DIR = Path("data/trials")
BENCHMARKS_DIR = Path("data/benchmarks")
HYPOTHESES_DOC = Path("docs/HYPOTHESES.md")
FINGERPRINT_TABLES = (
    "stock_prices",
    "total_returns",
    "fundamentals_pit",
    "fundamental_metrics",
    "price_metrics",
    "universe_constituents",
    "dividend_calendar",
)


@cache
def known_hypotheses() -> frozenset[str]:
    """Hypothesis ids defined in docs/HYPOTHESES.md (headings '## H<n> — ...')."""
    return frozenset(re.findall(r"^## (H\d+) —", HYPOTHESES_DOC.read_text(), re.MULTILINE))


@dataclass(frozen=True)
class TrialSpec:
    """What to run. `params` must be JSON (it is stored and hashed as is)."""

    hypothesis_id: str
    experiment: str
    strategy_id: str
    params: dict[str, Any]
    area: str
    from_date: date
    to_date: date
    stage: str = "explore"
    # data scenario, e.g. {"bankruptcy": {"rate": 0.05, "weak_multiplier": 4.0, "seed": 1}}
    scenario: dict[str, Any] | None = None

    def validate(self) -> None:
        from factor_investor.benchmarks.run import AREAS

        if self.hypothesis_id not in known_hypotheses():
            raise ValueError(
                f"Unknown hypothesis {self.hypothesis_id!r}; add it to {HYPOTHESES_DOC} first"
            )
        if not self.experiment.strip():
            raise ValueError("An experiment name is required")
        if not VERSIONED_ID.match(self.strategy_id):
            raise ValueError(f"Strategy id {self.strategy_id!r} must end in _v<N>")
        if self.area not in AREAS:
            raise ValueError(f"Unknown area {self.area!r}; choose from {sorted(AREAS)}")
        if self.from_date >= self.to_date or self.from_date > date.today():
            raise ValueError(f"Invalid period: from_date {self.from_date}, to_date {self.to_date}")
        try:
            json.dumps(self.params, allow_nan=False)
        except (TypeError, ValueError) as e:
            raise ValueError(f"params must be JSON: {e}") from e
        if self.scenario is not None:
            bankruptcy_scenario(self.scenario)


def bankruptcy_scenario(scenario: dict[str, Any]) -> Any:
    """The BankruptcyScenario a trial's scenario describes (the only kind so far)."""
    from factor_investor.stress.bankruptcy import BankruptcyScenario

    if set(scenario) != {"bankruptcy"}:
        raise ValueError(f"Unknown scenario {sorted(scenario)}; supported: bankruptcy")
    values = scenario["bankruptcy"]
    if not isinstance(values, dict) or set(values) != {"rate", "weak_multiplier", "seed"}:
        raise ValueError("bankruptcy scenario needs exactly rate, weak_multiplier and seed")
    if not 0 <= values["rate"] < 1 or values["weak_multiplier"] < 1:
        raise ValueError(f"Invalid bankruptcy scenario {values}")
    return BankruptcyScenario(
        float(values["rate"]), float(values["weak_multiplier"]), int(values["seed"])
    )


def config_hash(spec: TrialSpec) -> str:
    """Hash of what is run: strategy, parameters, area, period and data scenario
    (not the hypothesis, experiment or stage labels). Without a scenario the
    hash is the same as before scenarios existed."""
    fields: dict[str, Any] = {
        "strategy_id": spec.strategy_id,
        "params": spec.params,
        "area": spec.area,
        "from_date": spec.from_date.isoformat(),
        "to_date": spec.to_date.isoformat(),
    }
    if spec.scenario is not None:
        fields["scenario"] = spec.scenario
    canonical = json.dumps(
        fields,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def check_source_hash(strategy_id: str, source_hash: str, known: set[str]) -> None:
    """Refuse a strategy version whose source differs from the logged one."""
    if known and source_hash not in known:
        raise ValueError(
            f"{strategy_id} changed after it was used in a logged run "
            f"(source hash {source_hash[:12]} not in {sorted(h[:12] for h in known)}); "
            f"create the next version (_v2, ...) instead"
        )


@dataclass(frozen=True)
class CodeState:
    commit: str
    dirty: bool


def code_state() -> CodeState:
    """Current git commit, and whether src/ or config/ have uncommitted changes."""
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain", "--", "src", "config"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return CodeState(commit, bool(status.strip()))


def data_fingerprint(session: Session) -> dict[str, int | None]:
    """Highest id per input table: every sync or rebuild inserts new rows."""
    return {
        table: session.execute(text(f"SELECT max(id) FROM {table}")).scalar()
        for table in FINGERPRINT_TABLES
    }


def _monthly(returns: pl.DataFrame) -> pl.DataFrame:
    return (
        returns.sort("date")
        .group_by_dynamic("date", every="1mo")
        .agg(((1 + pl.col("portfolio_return")).product() - 1).alias("r"))
    )


def _cagr(monthly: pl.Series) -> float:
    return float((1 + monthly).product() ** (12 / len(monthly)) - 1)


def relative_metrics(returns: pl.DataFrame, benchmark: pl.DataFrame) -> dict[str, float]:
    """Strategy vs benchmark over their common months: excess CAGR, tracking
    error, information ratio, correlation (monthly, so calendars need not match)."""
    joined = _monthly(returns).join(_monthly(benchmark), on="date", suffix="_b").drop_nulls()
    if len(joined) < 12:
        return {}
    diff = (joined["r"] - joined["r_b"]).to_numpy()
    tracking_error = float(np.std(diff, ddof=1) * math.sqrt(12))
    return {
        "months": len(joined),
        "excess_cagr": _cagr(joined["r"]) - _cagr(joined["r_b"]),
        "tracking_error": tracking_error,
        "information_ratio": float(np.mean(diff) * 12 / tracking_error) if tracking_error else 0.0,
        "correlation": float(np.corrcoef(joined["r"], joined["r_b"])[0, 1]),
    }


def benchmark_comparison(
    returns: pl.DataFrame, area: str, out_dir: Path = BENCHMARKS_DIR
) -> dict[str, Any]:
    """Comparison with the area's saved benchmarks, and the percentile of the
    strategy's CAGR among the area's random portfolios over the same months."""
    result: dict[str, Any] = {}
    for benchmark_id in ("equal_weight_v1", "cap_weight_v1"):
        path = out_dir / f"{benchmark_id}_{area}.parquet"
        if path.exists():
            result[benchmark_id] = relative_metrics(returns, pl.read_parquet(path))
    strategy_monthly = _monthly(returns)
    for random_dir in sorted(out_dir.glob(f"random_pick_v1_{area}_k*")):
        cagrs = []
        for path in sorted(random_dir.glob("seed_*.parquet")):
            joined = strategy_monthly.join(_monthly(pl.read_parquet(path)), on="date", suffix="_b")
            cagrs.append(_cagr(joined["r_b"]))
        if cagrs:
            strategy = _cagr(strategy_monthly.join(_monthly(pl.read_parquet(path)), on="date")["r"])
            result[random_dir.name] = {
                "runs": len(cagrs),
                "percentile": float(np.mean(np.array(cagrs) < strategy)),
                "median_cagr": float(np.median(cagrs)),
            }
    return result


def _json_safe(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(v) for v in value]
    if isinstance(value, date | datetime):
        return value.isoformat()
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    return value


@dataclass
class TrialResult:
    trial_id: int
    final_value: float
    metrics: dict[str, Any] = field(default_factory=dict)
    returns_path: Path | None = None


def _engine_for(area: str) -> BacktestEngine:
    from factor_investor.benchmarks.run import AREAS, _engine
    from factor_investor.benchmarks.universe import Region

    region = AREAS[area]
    return _engine(region.currency if isinstance(region, Region) else None)


@lru_cache(maxsize=1)  # one stressed price panel (about 5 GB) per process at a time
def _stressed(
    scenario_json: str, area: str, from_date: date, to_date: date
) -> tuple[BacktestEngine, pl.DataFrame]:
    """Engine on prices with the scenario's failures applied, and the failure
    events (cached per process and scenario)."""
    from factor_investor.backtest.prices import (
        PANEL_PATH,
        PricePanel,
        _currency_frames,
        _is_current,
        build_price_panel,
        convert_currency,
    )
    from factor_investor.benchmarks.run import AREAS
    from factor_investor.benchmarks.universe import Region
    from factor_investor.stress.bankruptcy import apply_failures, scenario_events

    events = scenario_events(
        bankruptcy_scenario(json.loads(scenario_json)), area, from_date, to_date
    )
    if not _is_current(PANEL_PATH):
        build_price_panel(PANEL_PATH)
    frame = pl.read_parquet(PANEL_PATH)
    region = AREAS[area]
    if isinstance(region, Region):
        frame = convert_currency(frame, *_currency_frames(), base=region.currency)
    panel = PricePanel.from_frame(apply_failures(frame, events))
    return BacktestEngine(prices=panel), events


def run_trial(
    spec: TrialSpec,
    *,
    engine: BacktestEngine | None = None,
    session: Session | None = None,
    trials_dir: Path = TRIALS_DIR,
    benchmarks_dir: Path = BENCHMARKS_DIR,
    allow_dirty: bool = False,
    allow_gross: bool = False,
) -> TrialResult:
    """Run one research backtest and log it in the trial registry.

    Single markets run on prices in their own currency, regions on prices
    converted to theirs (as their benchmarks do). `engine` and `session` are
    for tests.
    """
    spec.validate()
    registered = get_strategy(spec.strategy_id)
    if registered.hypothesis is not None and registered.hypothesis != spec.hypothesis_id:
        raise ValueError(
            f"{spec.strategy_id} belongs to {registered.hypothesis}, not {spec.hypothesis_id}"
        )
    if registered.area is not None and registered.area != spec.area:
        raise ValueError(f"{spec.strategy_id} runs on area {registered.area}, not {spec.area}")
    strategy = registered.factory(spec.params)
    source_hash = registered.source_hash()
    cost_bps = strategy.transaction_cost_bps
    if cost_bps == 0 and not allow_gross:
        raise ValueError("Costs are off: pass allow_gross=True; the trial is labelled gross")
    code = code_state()
    if code.dirty and not allow_dirty:
        raise ValueError("Uncommitted changes under src/ or config/: commit before running trials")

    if session is None:
        with get_session() as own_session:
            return _run_logged(
                spec,
                strategy,
                source_hash,
                cost_bps,
                code,
                engine,
                own_session,
                trials_dir,
                benchmarks_dir,
            )
    return _run_logged(
        spec, strategy, source_hash, cost_bps, code, engine, session, trials_dir, benchmarks_dir
    )


def _run_logged(
    spec: TrialSpec,
    strategy: Any,
    source_hash: str,
    cost_bps: int,
    code: CodeState,
    engine: BacktestEngine | None,
    session: Session,
    trials_dir: Path,
    benchmarks_dir: Path,
) -> TrialResult:
    known = set(
        session.scalars(
            select(Trial.strategy_source_hash).where(Trial.strategy_id == spec.strategy_id)
        ).all()
    )
    check_source_hash(spec.strategy_id, source_hash, known)

    trial = Trial(
        status="running",
        hypothesis_id=spec.hypothesis_id,
        experiment=spec.experiment,
        stage=spec.stage,
        strategy_id=spec.strategy_id,
        strategy_source_hash=source_hash,
        params=spec.params,
        config_hash=config_hash(spec),
        area=spec.area,
        from_date=spec.from_date,
        to_date=spec.to_date,
        cost_bps=cost_bps,
        gross=cost_bps == 0,
        scenario=spec.scenario,
        price_filter=PRICE_FILTER_ID,
        data_fingerprint=data_fingerprint(session),
        code_commit=code.commit,
        code_dirty=code.dirty,
    )
    session.add(trial)
    session.commit()  # logged before it runs: a crash still counts as a trial
    logger.info(f"Trial {trial.id}: {spec.strategy_id} {spec.params} ({spec.experiment})")

    try:
        if spec.scenario is not None:
            from factor_investor.pipeline.view import excluded_instruments

            stressed_engine, events = _stressed(
                json.dumps(spec.scenario, sort_keys=True), spec.area, spec.from_date, spec.to_date
            )
            with excluded_instruments(events):
                result = (engine or stressed_engine).run(strategy, spec.from_date, spec.to_date)
        else:
            result = (engine or _engine_for(spec.area)).run(strategy, spec.from_date, spec.to_date)
        returns = result.returns_df.select("date", "portfolio_return")
        final_value = float(result.metadata["final_value"])

        earlier = session.execute(
            select(Trial.final_value, Trial.data_fingerprint).where(
                Trial.config_hash == trial.config_hash,
                Trial.strategy_source_hash == source_hash,
                Trial.code_commit == code.commit,
                Trial.price_filter == PRICE_FILTER_ID,
                Trial.status == "completed",
                Trial.id != trial.id,
            )
        ).all()
        same_data = [v for v, fp in earlier if fp == trial.data_fingerprint]
        if any(value != final_value for value in same_data):
            raise RuntimeError(
                f"Nondeterministic: final value {final_value} differs from an earlier run "
                f"of the same configuration on the same data and code ({same_data})"
            )

        metrics = {
            **asdict(result.metrics),
            "vs": benchmark_comparison(returns, spec.area, benchmarks_dir),
            "num_trades": len(result.trades),
        }
        trials_dir.mkdir(parents=True, exist_ok=True)
        returns_path = trials_dir / f"trial_{trial.id:06d}.parquet"
        returns.write_parquet(returns_path)

        trial.status = "completed"
        trial.final_value = final_value
        trial.metrics = _json_safe(metrics)
        trial.returns_path = str(returns_path)
        trial.finished_at = datetime.now()
        session.commit()
        return TrialResult(trial.id, final_value, trial.metrics or {}, returns_path)
    except Exception as e:
        session.rollback()
        trial.status = "failed"
        trial.error = f"{type(e).__name__}: {e}"
        trial.finished_at = datetime.now()
        session.commit()
        raise


def trial_counts(session: Session, hypothesis_id: str | None = None) -> pl.DataFrame:
    """Distinct configurations tried per hypothesis and experiment (failed
    runs included): the trial counts for deflated Sharpe and PBO."""
    query = select(Trial.hypothesis_id, Trial.experiment, Trial.config_hash, Trial.status)
    if hypothesis_id is not None:
        query = query.where(Trial.hypothesis_id == hypothesis_id)
    rows = session.execute(query).all()
    frame = pl.DataFrame(
        rows,
        schema={
            "hypothesis_id": pl.Utf8,
            "experiment": pl.Utf8,
            "config_hash": pl.Utf8,
            "status": pl.Utf8,
        },
        orient="row",
    )
    return (
        frame.group_by("hypothesis_id", "experiment")
        .agg(
            pl.col("config_hash").n_unique().alias("configurations"),
            pl.len().alias("runs"),
            (pl.col("status") == "failed").sum().alias("failed"),
        )
        .sort("hypothesis_id", "experiment")
    )
