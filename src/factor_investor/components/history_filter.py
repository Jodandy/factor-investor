"""history_filter_v1: keep instruments whose metric, summarized over its own
annual history (one snapshot a year at the view's month, T included), is at
least min_value (e.g. CANSLIM's A: 3-year median earnings growth >= 25%).
Too little history never passes."""

from datetime import date
from typing import Literal

import polars as pl
from pydantic import Field

from factor_investor.components.base import (
    ComponentParams,
    FilterComponent,
    View,
    register_component,
)


def annual_dates(dates: list[date], as_of: date, years: int) -> list[date]:
    months = [(d, (as_of.year - d.year) * 12 + as_of.month - d.month) for d in dates]
    return [d for d, m in months if m >= 0 and m % 12 == 0 and m < years * 12]


_STATS = {
    "median": pl.col("value").median(),
    "mean": pl.col("value").mean(),
    "share_positive": (pl.col("value") > 0).cast(pl.Float64).mean(),
    "min": pl.col("value").min(),
}


class HistoryFilterParams(ComponentParams):
    metric: str
    stat: Literal["median", "mean", "share_positive", "min"]
    years: int = Field(default=3, ge=1)
    min_observations: int = Field(default=3, ge=1)
    min_value: float


@register_component
class HistoryFilter(FilterComponent):
    id = "history_filter_v1"
    Params = HistoryFilterParams

    def run(self, view: View, instruments: pl.DataFrame) -> pl.DataFrame:
        p = self.params
        assert isinstance(p, HistoryFilterParams)
        history = view.metric_history(p.metric, p.years)
        keep = annual_dates(history["date"].unique().to_list(), view.as_of, p.years)
        passing = (
            history.filter(pl.col("date").is_in(keep))
            .group_by("instrument_id")
            .agg(_STATS[p.stat].alias("stat"), pl.len().alias("n"))
            .filter((pl.col("n") >= p.min_observations) & (pl.col("stat") >= p.min_value))
            .select("instrument_id")
        )
        return instruments.select(pl.col("instrument_id").cast(pl.Int32)).join(
            passing, on="instrument_id"
        )
