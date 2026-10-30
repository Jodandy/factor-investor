"""stop_loss_v1: close a position once its price is `pct` below the entry
price (CANSLIM: cut losses at 7-8% below the buy point)."""

import polars as pl
from pydantic import Field

from factor_investor.components.base import ComponentParams, ExitComponent, register_component


class StopLossParams(ComponentParams):
    pct: float = Field(gt=0, lt=1)


@register_component
class StopLoss(ExitComponent):
    id = "stop_loss_v1"
    Params = StopLossParams

    def run(self, positions: pl.DataFrame) -> set[int]:
        p = self.params
        assert isinstance(p, StopLossParams)
        hit = positions.filter(pl.col("price") <= pl.col("entry_price") * (1 - p.pct))
        return set(hit["instrument_id"].to_list())
