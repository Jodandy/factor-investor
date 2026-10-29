"""top_n_factor_v1: the top N names by one base metric, equal weight.

The simplest factor strategy, for value (lowest positive P/E) and momentum
(highest 12-1 month return) baselines. On each rebalancing date T it ranks the
area's investable universe (eligible, domestic, one listing per company; as
for the benchmarks) by the metric's snapshot for T, which uses only data known
on T. Orders execute from T+1 in the engine.
"""

from datetime import date
from typing import Any

import polars as pl

from factor_investor.backtest.strategy import Strategy, TargetPortfolio
from factor_investor.benchmarks.universe import WEIGHTS_SCHEMA, Market, Region, investable_universe
from factor_investor.dates import month_end_dates
from factor_investor.factors.snapshot import metric_snapshot
from factor_investor.strategy.registry import register_strategy

PARAMS = {
    "area",  # benchmark area code: SE, NO, FI, DK, US, EU
    "factor",  # base metric name (fundamental_metrics or price_metrics)
    "higher_is_better",
    "positive_only",  # drop values <= 0 (a negative P/E is a loss, not cheap)
    "top_n",
    "min_turnover",  # median 60-day turnover in the area's currency, or None
    "rebalance",  # monthly or quarterly
    "cost_bps",
}
QUARTER_ENDS = {3, 6, 9, 12}


def rebalancing_dates(rebalance: str, from_date: date, to_date: date) -> list[date]:
    dates = month_end_dates(from_date, to_date)
    if rebalance == "monthly":
        return dates
    if rebalance == "quarterly":
        return [d for d in dates if d.month in QUARTER_ENDS]
    raise ValueError(f"Unknown rebalance {rebalance!r}")


def select_top_n(
    universe: pl.DataFrame,
    values: pl.DataFrame,
    *,
    top_n: int,
    higher_is_better: bool,
    positive_only: bool,
    min_turnover: float | None,
) -> pl.DataFrame:
    """Equal weights for the top_n universe names by value (ties: lowest id)."""
    candidates = universe.select(
        pl.col("instrument_id").cast(pl.Int32), "median_turnover_60d", "to_base"
    ).join(values, on="instrument_id")
    if positive_only:
        candidates = candidates.filter(pl.col("value") > 0)
    if min_turnover is not None:
        candidates = candidates.filter(
            pl.col("median_turnover_60d") * pl.col("to_base") >= min_turnover
        )
    top = candidates.sort(["value", "instrument_id"], descending=[higher_is_better, False]).head(
        top_n
    )
    return top.select(
        "instrument_id", pl.lit(1 / len(top) if len(top) else 0.0).alias("weight")
    ).cast(WEIGHTS_SCHEMA)  # type: ignore[arg-type]


class TopNFactorStrategy(Strategy):
    def __init__(
        self,
        area: Market | Region,
        factor: str,
        higher_is_better: bool,
        positive_only: bool,
        top_n: int,
        min_turnover: float | None,
        rebalance: str,
        cost_bps: int,
    ) -> None:
        self.area = area
        self.factor = factor
        self.higher_is_better = higher_is_better
        self.positive_only = positive_only
        self.top_n = top_n
        self.min_turnover = min_turnover
        self.rebalance = rebalance
        self.cost_bps = cost_bps

    @property
    def name(self) -> str:
        order = "highest" if self.higher_is_better else "lowest"
        return f"top_n_factor_v1 {self.area.code} {order} {self.factor} top {self.top_n}"

    @property
    def transaction_cost_bps(self) -> int:
        return self.cost_bps

    @property
    def max_position_weight(self) -> float:
        return 1.0

    def get_rebalancing_dates(self, from_date: date, to_date: date) -> list[date]:
        return rebalancing_dates(self.rebalance, from_date, to_date)

    def generate_signals(
        self,
        as_of_date: date,
        current_holdings: pl.DataFrame | None = None,  # noqa: ARG002
    ) -> TargetPortfolio:
        universe = investable_universe(as_of_date, self.area)
        if universe.is_empty():
            return TargetPortfolio(pl.DataFrame(schema=WEIGHTS_SCHEMA))
        weights = select_top_n(
            universe,
            metric_snapshot(self.factor, as_of_date),
            top_n=self.top_n,
            higher_is_better=self.higher_is_better,
            positive_only=self.positive_only,
            min_turnover=self.min_turnover,
        )
        return TargetPortfolio(weights, metadata={"universe_size": len(universe)})


@register_strategy("top_n_factor_v1")
def top_n_factor_v1(params: dict[str, Any]) -> Strategy:
    from factor_investor.benchmarks.run import AREAS

    missing = PARAMS - set(params)
    unknown = set(params) - PARAMS
    if missing or unknown:
        raise ValueError(f"top_n_factor_v1: missing {sorted(missing)}, unknown {sorted(unknown)}")
    return TopNFactorStrategy(
        area=AREAS[params["area"]],
        factor=params["factor"],
        higher_is_better=bool(params["higher_is_better"]),
        positive_only=bool(params["positive_only"]),
        top_n=int(params["top_n"]),
        min_turnover=params["min_turnover"],
        rebalance=params["rebalance"],
        cost_bps=int(params["cost_bps"]),
    )
