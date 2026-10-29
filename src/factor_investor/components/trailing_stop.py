"""trailing_stop_v1: close a position once its price has fallen `pct` below
the highest daily price since entry."""

import polars as pl
from pydantic import Field

from factor_investor.components.base import ComponentParams, ExitComponent, register_component


class TrailingStopParams(ComponentParams):
    pct: float = Field(gt=0, lt=1)


@register_component
class TrailingStop(ExitComponent):
    id = "trailing_stop_v1"
    Params = TrailingStopParams

    def run(self, positions: pl.DataFrame) -> set[int]:
        p = self.params
        assert isinstance(p, TrailingStopParams)
        hit = positions.filter(pl.col("price") <= pl.col("high") * (1 - p.pct))
        return set(hit["instrument_id"].to_list())
