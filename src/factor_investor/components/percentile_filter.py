"""percentile_filter_v1: keep instruments whose metric ranks at or above a
percentile among the instruments given (e.g. CANSLIM's relative strength:
top 20% by momentum). Missing values never pass."""

import polars as pl
from pydantic import Field

from factor_investor.components.base import (
    ComponentParams,
    FilterComponent,
    View,
    register_component,
)


class PercentileFilterParams(ComponentParams):
    metric: str
    min_percentile: float = Field(ge=0, le=1)
    higher_is_better: bool = True


@register_component
class PercentileFilter(FilterComponent):
    id = "percentile_filter_v1"
    Params = PercentileFilterParams

    def run(self, view: View, instruments: pl.DataFrame) -> pl.DataFrame:
        p = self.params
        assert isinstance(p, PercentileFilterParams)
        values = instruments.select(pl.col("instrument_id").cast(pl.Int32)).join(
            view.metric(p.metric), on="instrument_id"
        )
        pct = (pl.col("value").rank("average") - 0.5) / pl.col("value").count()
        if not p.higher_is_better:
            pct = 1 - pct
        return values.filter(pct >= p.min_percentile).select("instrument_id")
