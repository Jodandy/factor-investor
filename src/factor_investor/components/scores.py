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
    # values <= 0 score 0 (worst) and the rest are ranked among themselves;
    # for ratios such as P/E or EV/EBIT where a loss makes the value negative
    non_positive_is_worst: bool = False


def _percentile(values: pl.Expr, higher_is_better: bool) -> pl.Expr:
    """(rank - 0.5) / n with average ranks for ties, flipped if lower is better."""
    pct = (values.rank("average") - 0.5) / values.count()
    return pct if higher_is_better else 1 - pct


@register_component
class Percentile(ScoreComponent):
    """Cross-sectional percentile of a metric among the given instruments.

    Instruments without a value get null (unknown), which the composite leaves
    out; use non_positive_is_worst where a missing-looking value is really bad.
    """

    id = "percentile_v1"
    Params = PercentileParams

    def run(self, view: View, instruments: pl.DataFrame) -> pl.DataFrame:
        p = self.params
        assert isinstance(p, PercentileParams)
        values = instruments.select(pl.col("instrument_id").cast(pl.Int32)).join(
            view.metric(p.metric), on="instrument_id", how="left"
        )
        if p.non_positive_is_worst:
            positive = pl.when(pl.col("value") > 0).then(pl.col("value"))
            score = (
                pl.when(pl.col("value") <= 0)
                .then(0.0)
                .otherwise(_percentile(positive, p.higher_is_better))
            )
        else:
            score = _percentile(pl.col("value"), p.higher_is_better)
        scored = values.with_columns(score.alias("score"))
        return scored.select("instrument_id", "score").cast(SCORE_SCHEMA)  # type: ignore[arg-type]


class OwnHistoryParams(ComponentParams):
    metric: str
    years: int = 5
    higher_is_better: bool = True
    # a current value <= 0 scores 0 (worst); earlier values <= 0 are left out
    non_positive_is_worst: bool = False
    min_observations: int = 24


@register_component
class OwnHistoryPercentile(ScoreComponent):
    """Where the metric's current value stands in the instrument's own monthly
    snapshots over the past `years` (before the view's date): the share of
    earlier values it beats, ties counting half. With non_positive_is_worst a
    current value <= 0 (e.g. a P/E from a loss) scores 0, and earlier values
    <= 0 are left out of the comparison."""

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
        if p.non_positive_is_worst:
            earlier = earlier.filter(pl.col("value") > 0)
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
        if p.non_positive_is_worst:
            losses = current.filter(pl.col("current") <= 0).select(
                "instrument_id", pl.lit(0.0).alias("score")
            )
            scored = pl.concat([scored.join(losses, on="instrument_id", how="anti"), losses])
        return (
            instruments.select(pl.col("instrument_id").cast(pl.Int32))
            .join(scored, on="instrument_id", how="left")
            .cast(SCORE_SCHEMA)  # type: ignore[arg-type]
        )
