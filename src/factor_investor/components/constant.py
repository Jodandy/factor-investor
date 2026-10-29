"""constant_v1: the same score for every instrument (no selection).

For controls such as "equal weight over a filtered universe". One component
per file from here on: a component's source hash covers its whole module, so
adding a component to a shared module would change logged strategies' hashes.
"""

import polars as pl

from factor_investor.components.base import (
    SCORE_SCHEMA,
    ComponentParams,
    ScoreComponent,
    View,
    register_component,
)


class ConstantParams(ComponentParams):
    pass


@register_component
class Constant(ScoreComponent):
    id = "constant_v1"
    Params = ConstantParams

    def run(self, view: View, instruments: pl.DataFrame) -> pl.DataFrame:  # noqa: ARG002
        return instruments.select(
            pl.col("instrument_id").cast(pl.Int32), pl.lit(0.5).alias("score")
        ).cast(SCORE_SCHEMA)  # type: ignore[arg-type]
