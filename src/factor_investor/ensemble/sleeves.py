"""sleeves_v1: strategies run side by side, each with its own share of capital.

Each member is a logged trial (its daily returns already include its own
trading costs). The ensemble holds the members in fixed weights: the sleeves
drift with their returns and are set back to the weights at the end of each
rebalancing period; the money moved between sleeves pays cost_bps (sells and
buys both count). This is the portfolio-of-portfolios ensemble; holdings that
two sleeves share are not netted.
"""

import itertools
from collections.abc import Callable
from datetime import date
from typing import Any

import polars as pl

PERIOD_KEY: dict[str, Callable[[date], tuple[int, ...]]] = {
    "monthly": lambda d: (d.year, d.month),
    "quarterly": lambda d: (d.year, (d.month - 1) // 3),
    "annual": lambda d: (d.year,),
}


def rebalance_days(days: list[date], rebalance: str) -> set[date]:
    """The days followed by a day in another period (the last trading day of
    each period; not the last day of the data)."""
    key = PERIOD_KEY[rebalance]
    ordered = sorted(days)
    return {d for d, nxt in itertools.pairwise(ordered) if key(d) != key(nxt)}


def combine_sleeves(
    members: list[pl.DataFrame], weights: list[float], rebalance_on: set[date], cost_bps: float
) -> pl.DataFrame:
    """[date, portfolio_return] of the ensemble from members' [date, portfolio_return]."""
    if abs(sum(weights) - 1) > 1e-9 or any(w < 0 for w in weights):
        raise ValueError(f"Sleeve weights must be non-negative and sum to 1, got {weights}")
    dates = members[0]["date"].to_list()
    if any(m["date"].to_list() != dates for m in members[1:]):
        raise ValueError("Members must have the same dates (same engine calendar and period)")
    series = [m["portfolio_return"].to_list() for m in members]
    sleeves = list(weights)
    out = []
    previous = 1.0
    for t, day in enumerate(dates):
        sleeves = [v * (1 + s[t]) for v, s in zip(sleeves, series, strict=True)]
        total = sum(sleeves)
        if day in rebalance_on:
            traded = sum(abs(w * total - v) for w, v in zip(weights, sleeves, strict=True))
            total -= traded * cost_bps / 10_000
            sleeves = [w * total for w in weights]
        out.append(total / previous - 1)
        previous = total
    return pl.DataFrame({"date": dates, "portfolio_return": out})


class Result:
    """The parts of a BacktestResult the trial registry logs."""

    def __init__(self, returns_df: pl.DataFrame, initial_capital: float = 1_000_000) -> None:
        from factor_investor.analytics.metrics import calculate_performance_metrics

        self.returns_df = returns_df
        self.metrics = calculate_performance_metrics(returns_df)
        self.metadata = {
            "final_value": initial_capital * float((1 + returns_df["portfolio_return"]).product())
        }
        self.trades = pl.DataFrame()


class SleevesEnsemble:
    """Members given by strategy id and parameters; each must already be logged
    as a completed trial with the ensemble's area and period."""

    def __init__(self, params: dict[str, Any]) -> None:
        unknown = set(params) - {"members", "rebalance", "cost_bps"}
        if unknown or "members" not in params:
            raise ValueError(
                f"sleeves_v1 needs members (and rebalance, cost_bps); unknown {unknown}"
            )
        self.members = params["members"]
        self.rebalance = params.get("rebalance", "quarterly")
        self.cost_bps = int(params.get("cost_bps", 10))
        if self.rebalance not in PERIOD_KEY:
            raise ValueError(f"Unknown rebalance {self.rebalance!r}")
        for member in self.members:
            if set(member) != {"strategy_id", "params", "weight"}:
                raise ValueError(f"Member needs strategy_id, params and weight: {member}")

    @property
    def transaction_cost_bps(self) -> int:
        return self.cost_bps

    def combine(self, spec: Any, session: Any) -> Result:
        from sqlalchemy import select

        from factor_investor.search.models import Trial
        from factor_investor.search.registry import TrialSpec, config_hash

        returns = []
        for member in self.members:
            member_spec = TrialSpec(
                spec.hypothesis_id,
                spec.experiment,
                member["strategy_id"],
                member["params"],
                spec.area,
                spec.from_date,
                spec.to_date,
            )
            trial = session.scalars(
                select(Trial)
                .where(Trial.config_hash == config_hash(member_spec), Trial.status == "completed")
                .order_by(Trial.id.desc())
            ).first()
            if trial is None or trial.returns_path is None:
                raise ValueError(f"Member not logged for this area and period: {member}")
            returns.append(pl.read_parquet(trial.returns_path).select("date", "portfolio_return"))
        days = returns[0]["date"].to_list()
        combined = combine_sleeves(
            returns,
            [float(m["weight"]) for m in self.members],
            rebalance_days(days, self.rebalance),
            self.cost_bps,
        )
        return Result(combined)
