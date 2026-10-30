"""relative_value_filter_v1 and relative_value_score_v1: valuation against the
company's own history (H11, the ValBands idea). Upside = mean over valid
multiples of (historical median or 75th percentile / today's multiple - 1);
see valuation.py.

The filter keeps names whose upside to the chosen band is at least
min_upside: as a buy rule (e.g. >= 25% to fair value mid) or a hold rule
(e.g. > 0: still below fair value). The score ranks by upside to mid."""

from typing import Literal

import polars as pl
from pydantic import Field

from factor_investor.components.base import (
    SCORE_SCHEMA,
    ComponentParams,
    FilterComponent,
    ScoreComponent,
    View,
    register_component,
)
from factor_investor.components.valuation import RELATIVE_METRICS, relative_upsides


class RelativeParams(ComponentParams):
    metrics: list[str] = Field(default_factory=lambda: list(RELATIVE_METRICS))
    years: int = Field(default=2, ge=1)
    min_observations: int = Field(default=12, ge=1)
    min_metrics: int = Field(default=2, ge=1)


class RelativeFilterParams(RelativeParams):
    band: Literal["mid", "high"]
    min_upside: float


@register_component
class RelativeValueFilter(FilterComponent):
    id = "relative_value_filter_v1"
    Params = RelativeFilterParams
    extra_sources = ("valuation.py",)

    def run(self, view: View, instruments: pl.DataFrame) -> pl.DataFrame:
        p = self.params
        assert isinstance(p, RelativeFilterParams)
        upsides: pl.DataFrame = relative_upsides(
            view, instruments, p.metrics, p.years, p.min_observations, p.min_metrics
        )
        column = "upside_mid" if p.band == "mid" else "upside_high"
        return upsides.filter(pl.col(column) >= p.min_upside).select("instrument_id")


@register_component
class RelativeValueScore(ScoreComponent):
    id = "relative_value_score_v1"
    Params = RelativeParams
    extra_sources = ("valuation.py",)

    def run(self, view: View, instruments: pl.DataFrame) -> pl.DataFrame:
        p = self.params
        assert isinstance(p, RelativeParams)
        upsides: pl.DataFrame = relative_upsides(
            view, instruments, p.metrics, p.years, p.min_observations, p.min_metrics
        )
        pct = (pl.col("upside_mid").rank("average") - 0.5) / pl.col("upside_mid").count()
        return upsides.select("instrument_id", pct.alias("score")).cast(SCORE_SCHEMA)  # type: ignore[arg-type]
