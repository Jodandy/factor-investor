"""Synthetic bankruptcies: a stress test for Börsdata's missing delisted companies.

Börsdata has no delisted companies, so failures that really happened are not
in the backtests. This scenario adds synthetic ones: each month every company
in the area's investable universe fails with a small probability, higher for
weak companies (decided from data known at that month-end). The draw depends
only on (seed, instrument, month), so a company fails on the same date in
every strategy run under the scenario. A failed company's price falls to
1e-6 of its last price from the next day and stays there (as traded, so the
price filter confirms the loss), and it leaves the investable universe.
"""

import hashlib
from dataclasses import dataclass
from datetime import date

import polars as pl

LOSS_FACTOR = 1e-6
EVENTS_SCHEMA = {"instrument_id": pl.Int32, "date": pl.Date}


def uniform(seed: int, instrument_id: int, as_of: date) -> float:
    """Deterministic uniform in [0, 1) for (seed, instrument, date)."""
    digest = hashlib.sha256(f"{seed}:{instrument_id}:{as_of.isoformat()}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def failure_events(
    panel: pl.DataFrame, rate: float, weak_multiplier: float, seed: int
) -> pl.DataFrame:
    """[instrument_id, date] of failures from a panel [date, instrument_id, weak].

    Monthly hazard 1 - (1 - rate)^(1/12) on average over the names alive that
    month, weak names `weak_multiplier` times the others'. A name fails at most
    once; the failure takes effect after the snapshot date.
    """
    if rate <= 0:
        return pl.DataFrame(schema=EVENTS_SCHEMA)
    monthly = 1 - (1 - rate) ** (1 / 12)
    failed: set[int] = set()
    events: list[tuple[int, date]] = []
    for (as_of,), month in (
        panel.sort("date").partition_by("date", as_dict=True, maintain_order=True).items()
    ):
        alive = month.filter(~pl.col("instrument_id").is_in(list(failed)))
        if alive.is_empty():
            continue
        weights = alive["weak"].cast(pl.Float64) * (weak_multiplier - 1) + 1
        hazards = (monthly * weights / weights.mean()).clip(upper_bound=1.0)
        for instrument_id, hazard in zip(alive["instrument_id"], hazards, strict=True):
            if uniform(seed, instrument_id, as_of) < hazard:
                failed.add(instrument_id)
                events.append((instrument_id, as_of))
    return pl.DataFrame(events, schema=EVENTS_SCHEMA, orient="row").sort("date", "instrument_id")


def apply_failures(prices: pl.DataFrame, events: pl.DataFrame) -> pl.DataFrame:
    """Prices after each failure date replaced by LOSS_FACTOR x the last price
    on or before it, with volume 1. Other rows unchanged."""
    if events.is_empty():
        return prices
    failures = events.rename({"date": "failed_on"})
    last = (
        prices.join(failures, on="instrument_id")
        .filter(pl.col("date") <= pl.col("failed_on"))
        .group_by("instrument_id")
        .agg(pl.col("price").sort_by("date").last().alias("last_price"))
    )
    joined = prices.join(failures, on="instrument_id", how="left").join(
        last, on="instrument_id", how="left"
    )
    after = pl.col("failed_on").is_not_null() & (pl.col("date") > pl.col("failed_on"))
    return joined.with_columns(
        pl.when(after)
        .then(pl.coalesce("last_price", "price") * LOSS_FACTOR)
        .otherwise(pl.col("price"))
        .alias("price"),
        *(
            [
                pl.when(after)
                .then(pl.lit(1, dtype=prices.schema["volume"]))
                .otherwise(pl.col("volume"))
                .alias("volume")
            ]
            if "volume" in prices.columns
            else []
        ),
    ).select(prices.columns)


@dataclass(frozen=True)
class BankruptcyScenario:
    """Average annual failure rate, how much likelier weak companies fail, seed."""

    rate: float
    weak_multiplier: float = 4.0
    seed: int = 1


WEAK_SOLVENCY = 0.3


def weakness_panel(area_code: str, from_date: date, to_date: date) -> pl.DataFrame:
    """[date, instrument_id, weak] over the area's investable universe at every
    month-end: weak = ROIC <= 0 or unknown, or solvency (equity ratio) < 0.3,
    from the snapshot of that month-end."""
    from factor_investor.benchmarks.run import AREAS
    from factor_investor.benchmarks.universe import investable_universe
    from factor_investor.dates import month_end_dates
    from factor_investor.factors.snapshot import metric_snapshot

    area = AREAS[area_code]
    frames = []
    for as_of in month_end_dates(from_date, to_date):
        universe = investable_universe(as_of, area)
        if universe.is_empty():
            continue
        roic = metric_snapshot("roic", as_of).rename({"value": "roic"})
        solvency = metric_snapshot("solvency", as_of).rename({"value": "solvency"})
        frames.append(
            universe.select(pl.col("instrument_id").cast(pl.Int32))
            .join(roic, on="instrument_id", how="left")
            .join(solvency, on="instrument_id", how="left")
            .select(
                pl.lit(as_of).alias("date"),
                "instrument_id",
                (
                    pl.col("roic").is_null()
                    | (pl.col("roic") <= 0)
                    | (pl.col("solvency").fill_null(0) < WEAK_SOLVENCY)
                ).alias("weak"),
            )
        )
    return pl.concat(frames)


def scenario_events(
    scenario: BankruptcyScenario, area_code: str, from_date: date, to_date: date
) -> pl.DataFrame:
    return failure_events(
        weakness_panel(area_code, from_date, to_date),
        scenario.rate,
        scenario.weak_multiplier,
        scenario.seed,
    )
