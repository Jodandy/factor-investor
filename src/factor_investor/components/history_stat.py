"""history_stat_v1: a statistic of a metric over its own annual history, ranked
as a cross-sectional percentile (higher is better, null if unknown).

The history is sampled once a year at the view's calendar month (T, T-12m,
T-24m, ...), so trailing-twelve-month values do not overlap. Every snapshot
holds only what was known on its own date. Statistics:
- median: typical level over the years (e.g. 5-year median ROIC or growth)
- mean
- share_positive: share of years above zero (e.g. growth consistency)
- min: the worst year
"""

from datetime import date
from typing import Literal

import polars as pl
from pydantic import Field

from factor_investor.components.base import (
    SCORE_SCHEMA,
    ComponentParams,
    ScoreComponent,
    View,
    register_component,
)


def annual_dates(dates: list[date], as_of: date, years: int | None = None) -> list[date]:
    """The dates whose month is a whole number of years before as_of's month
    (at most `years` of them, as_of's own month included)."""
    months = [(d, (as_of.year - d.year) * 12 + as_of.month - d.month) for d in dates]
    return [d for d, m in months if m >= 0 and m % 12 == 0 and (years is None or m < years * 12)]


class HistoryStatParams(ComponentParams):
    metric: str
    stat: Literal["median", "mean", "share_positive", "min"]
    years: int = Field(default=5, ge=1)
    higher_is_better: bool = True
    min_observations: int = Field(default=3, ge=1)


_STATS = {
    "median": pl.col("value").median(),
    "mean": pl.col("value").mean(),
    "share_positive": (pl.col("value") > 0).cast(pl.Float64).mean(),
    "min": pl.col("value").min(),
}


@register_component
class HistoryStat(ScoreComponent):
    id = "history_stat_v1"
    Params = HistoryStatParams

    def run(self, view: View, instruments: pl.DataFrame) -> pl.DataFrame:
        p = self.params
        assert isinstance(p, HistoryStatParams)
        history = view.metric_history(p.metric, p.years)
        keep = annual_dates(history["date"].unique().to_list(), view.as_of, p.years)
        stats = (
            history.filter(pl.col("date").is_in(keep))
            .group_by("instrument_id")
            .agg(_STATS[p.stat].alias("stat"), pl.len().alias("n"))
            .filter(pl.col("n") >= p.min_observations)
        )
        frame = instruments.select(pl.col("instrument_id").cast(pl.Int32)).join(
            stats, on="instrument_id", how="left"
        )
        pct = (pl.col("stat").rank("average") - 0.5) / pl.col("stat").count()
        return frame.select(
            "instrument_id", (pct if p.higher_is_better else 1 - pct).alias("score")
        ).cast(SCORE_SCHEMA)  # type: ignore[arg-type]
