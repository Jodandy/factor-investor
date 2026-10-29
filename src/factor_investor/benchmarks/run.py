"""Run benchmarks and save their daily returns.

Each run is written to `data/benchmarks/` as Parquet with columns
[date, portfolio_return]; the file's schema metadata records what was run
(benchmark id, area, currency, k, seed, costs, price filter, period, final
value). Random-pick runs go in one directory per (area, k). Runs are
deterministic, so the files can always be regenerated.
"""

import json
import logging
import multiprocessing as mp
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date
from functools import cache
from pathlib import Path

import pyarrow.parquet as pq

from factor_investor.backtest.engine import BacktestEngine
from factor_investor.backtest.prices import PRICE_FILTER_ID, load_price_panel
from factor_investor.benchmarks.universe import (
    EUROPE,
    NORDICS,
    US,
    WEIGHTINGS,
    Market,
    MarketBenchmark,
    Region,
)

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("data/benchmarks")
METADATA_KEY = "factor_investor.benchmark"
AREAS: dict[str, Market | Region] = {area.code: area for area in (*NORDICS, US, EUROPE)}


@dataclass(frozen=True)
class BenchmarkRun:
    area: str
    weighting: str
    k: int | None = None
    seed: int | None = None

    def path(self, out_dir: Path = OUTPUT_DIR) -> Path:
        benchmark_id = WEIGHTINGS[self.weighting]
        if self.weighting == "random":
            return (
                out_dir / f"{benchmark_id}_{self.area}_k{self.k}" / f"seed_{self.seed:03d}.parquet"
            )
        return out_dir / f"{benchmark_id}_{self.area}.parquet"


@cache
def _engine(currency: str | None) -> BacktestEngine:
    return BacktestEngine(prices=load_price_panel(currency=currency))


def run_one(run: BenchmarkRun, from_date: date, to_date: date, out_dir: Path = OUTPUT_DIR) -> Path:
    """Run one benchmark and write its daily returns. Single markets run on
    prices in their own currency; regions on prices converted to theirs."""
    area = AREAS[run.area]
    currency = area.currency if isinstance(area, Region) else None
    strategy = MarketBenchmark(area, run.weighting, k=run.k, seed=run.seed)
    result = _engine(currency).run(strategy, from_date, to_date)

    metadata = {
        "benchmark_id": strategy.benchmark_id,
        "area": run.area,
        "currency": area.currency,
        "k": run.k,
        "seed": run.seed,
        "cost_bps": strategy.transaction_cost_bps,
        "price_filter": PRICE_FILTER_ID,
        "from_date": str(from_date),
        "to_date": str(to_date),
        "final_value": result.metadata["final_value"],
        "initial_capital": result.metadata["initial_capital"],
    }
    path = run.path(out_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    table = result.returns_df.select("date", "portfolio_return").to_arrow()
    pq.write_table(table.replace_schema_metadata({METADATA_KEY: json.dumps(metadata)}), path)
    return path


def _run_quietly(run: BenchmarkRun, from_date: date, to_date: date, out_dir: Path) -> Path:
    logging.basicConfig(level=logging.ERROR)
    return run_one(run, from_date, to_date, out_dir)


def run_many(
    runs: list[BenchmarkRun],
    from_date: date,
    to_date: date,
    out_dir: Path = OUTPUT_DIR,
    workers: int = 1,
) -> list[Path]:
    """Run benchmarks, in `workers` processes (each loads its own price panel,
    about 5 GB)."""
    if workers <= 1:
        return [run_one(run, from_date, to_date, out_dir) for run in runs]
    start = time.time()
    paths = []
    with ProcessPoolExecutor(workers, mp_context=mp.get_context("spawn")) as pool:
        futures = [pool.submit(_run_quietly, run, from_date, to_date, out_dir) for run in runs]
        for done, future in enumerate(as_completed(futures), 1):
            paths.append(future.result())
            logger.info(f"{done}/{len(runs)} {paths[-1]} ({time.time() - start:.0f}s)")
    return sorted(paths)


def read_metadata(path: Path) -> dict[str, object]:
    metadata = pq.read_schema(path).metadata or {}
    return dict(json.loads(metadata[METADATA_KEY.encode()]))
