"""Score components (stage 2): higher is better, scaled to (0, 1), null if unknown."""

from datetime import timedelta

import polars as pl

from factor_investor.components.base import (
    SCORE_SCHEMA,
    ComponentParams,
    ScoreComponent,
    View,
    register_component,
)


class PercentileParams(ComponentParams):
    metric: str
    higher_is_better: bool = True
    positive_only: bool = False


def _percentile(values: pl.Expr, higher_is_better: bool) -> pl.Expr:
    """(rank - 0.5) / n with average ranks for ties, flipped if lower is better."""
    pct = (values.rank("average") - 0.5) / values.count()
    return pct if higher_is_better else 1 - pct


@register_component
class Percentile(ScoreComponent):
    """Cross-sectional percentile of a metric among the given instruments."""

    id = "percentile_v1"
    Params = PercentileParams

    def run(self, view: View, instruments: pl.DataFrame) -> pl.DataFrame:
        p = self.params
        assert isinstance(p, PercentileParams)
        values = view.metric(p.metric)
        if p.positive_only:
            values = values.filter(pl.col("value") > 0)
        scored = (
            instruments.select(pl.col("instrument_id").cast(pl.Int32))
            .join(values, on="instrument_id", how="left")
            .with_columns(_percentile(pl.col("value"), p.higher_is_better).alias("score"))
        )
        return scored.select("instrument_id", "score").cast(SCORE_SCHEMA)  # type: ignore[arg-type]


class OwnHistoryParams(ComponentParams):
    metric: str
    years: int = 5
    higher_is_better: bool = True
    min_observations: int = 24


@register_component
class OwnHistoryPercentile(ScoreComponent):
    """Where the metric's current value stands in the instrument's own monthly
    snapshots over the past `years` (before the view's date): the share of
    earlier values it beats, ties counting half."""

    id = "own_history_percentile_v1"
    Params = OwnHistoryParams

    def run(self, view: View, instruments: pl.DataFrame) -> pl.DataFrame:
        p = self.params
        assert isinstance(p, OwnHistoryParams)
        current = view.metric(p.metric).rename({"value": "current"})
        earlier = view.metric_history(p.metric, p.years).filter(
            pl.col("date") < view.as_of,
            pl.col("date") > view.as_of - timedelta(days=round(365.25 * p.years)),
        )
        better = (
            (pl.col("value") < pl.col("current"))
            if p.higher_is_better
            else (pl.col("value") > pl.col("current"))
        )
        scored = (
            earlier.join(current, on="instrument_id")
            .group_by("instrument_id")
            .agg(
                (better.cast(pl.Float64) + 0.5 * (pl.col("value") == pl.col("current")))
                .mean()
                .alias("score"),
                pl.len().alias("n"),
            )
            .filter(pl.col("n") >= p.min_observations)
            .select("instrument_id", "score")
        )
        return (
            instruments.select(pl.col("instrument_id").cast(pl.Int32))
            .join(scored, on="instrument_id", how="left")
            .cast(SCORE_SCHEMA)  # type: ignore[arg-type]
        )
