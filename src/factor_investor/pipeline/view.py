"""Point-in-time view (ARCHITECTURE §6): the only way components see data.

A view is bound to one date T and an area. It reads month-end snapshots
(fundamentals known by T, prices up to T) and the area's investable universe
for T; no method takes a date. Snapshot reads are cached per process, keyed
by date, so many trials share them (`clear_caches` empties them).
"""

from datetime import date, timedelta
from functools import cache, lru_cache

import polars as pl

from factor_investor.benchmarks.universe import Market, Region, investable_universe
from factor_investor.factors.snapshot import known_metrics, metric_history, metric_snapshot

# Universe fields usable in expressions; amounts in the area's currency
UNIVERSE_FIELDS = frozenset({"market_cap", "turnover", "price", "years_of_history"})


@lru_cache(maxsize=4096)
def _snapshot(metric: str, as_of: date) -> pl.DataFrame:
    return metric_snapshot(metric, as_of)


@lru_cache(maxsize=1024)
def _history(metric: str, from_date: date, as_of: date) -> pl.DataFrame:
    return metric_history(metric, from_date, as_of)


@cache
def available_names() -> frozenset[str]:
    return known_metrics() | UNIVERSE_FIELDS


def clear_caches() -> None:
    _snapshot.cache_clear()
    _history.cache_clear()
    investable_universe.cache_clear()


class PointInTimeView:
    def __init__(self, as_of: date, area: Market | Region) -> None:
        self._as_of = as_of
        self._area = area

    @property
    def as_of(self) -> date:
        return self._as_of

    def universe(self) -> pl.DataFrame:
        """Investable universe on T: [instrument_id, market_cap, turnover, price,
        years_of_history] (eligible, domestic, one listing per company)."""
        universe = investable_universe(self._as_of, self._area)
        if universe.is_empty():
            return pl.DataFrame(
                schema={"instrument_id": pl.Int32, **dict.fromkeys(UNIVERSE_FIELDS, pl.Float64)}
            )
        return universe.select(
            pl.col("instrument_id").cast(pl.Int32),
            (pl.col("market_cap_local") * pl.col("to_base")).alias("market_cap"),
            (pl.col("median_turnover_60d") * pl.col("to_base")).alias("turnover"),
            pl.col("price"),
            pl.col("years_of_history"),
        )

    def metric(self, name: str) -> pl.DataFrame:
        return _snapshot(name, self._as_of)

    def metric_history(self, name: str, years: int) -> pl.DataFrame:
        return _history(name, self._as_of - timedelta(days=round(365.25 * years)), self._as_of)

    def frame(self, instruments: pl.DataFrame, names: frozenset[str]) -> pl.DataFrame:
        unknown = set(names) - available_names()
        if unknown:
            raise ValueError(f"Unknown names {sorted(unknown)}")
        frame = instruments.select(pl.col("instrument_id").cast(pl.Int32))
        fields = sorted(set(names) & UNIVERSE_FIELDS)
        if fields:
            frame = frame.join(
                self.universe().select("instrument_id", *fields), on="instrument_id", how="left"
            )
        for name in sorted(set(names) - UNIVERSE_FIELDS):
            frame = frame.join(
                self.metric(name).rename({"value": name}), on="instrument_id", how="left"
            )
        return frame
