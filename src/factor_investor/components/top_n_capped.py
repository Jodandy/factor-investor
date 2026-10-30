"""top_n_capped_v1: like top_n_hysteresis_v1 (keep holdings within sell_rank x
N, fill free slots with the best-ranked names), but each name gets
min(1 / names, max_weight); the rest stays in cash. For screens that often
pass only a few names (CANSLIM), so a single name is not the whole portfolio."""

import polars as pl
from pydantic import Field

from factor_investor.components.base import (
    WEIGHT_SCHEMA,
    ComponentParams,
    PortfolioComponent,
    register_component,
)


class TopNCappedParams(ComponentParams):
    top_n: int = Field(gt=0)
    sell_rank: float = Field(default=1.0, ge=1.0)
    max_weight: float = Field(gt=0, le=1)


@register_component
class TopNCapped(PortfolioComponent):
    id = "top_n_capped_v1"
    Params = TopNCappedParams

    def run(self, ranked: pl.DataFrame, current: list[int]) -> pl.DataFrame:
        p = self.params
        assert isinstance(p, TopNCappedParams)
        order = (
            ranked.drop_nulls("score")
            .sort(["score", "instrument_id"], descending=[True, False])
            .with_row_index("rank", offset=1)
        )
        keep = order.filter(
            pl.col("instrument_id").is_in(list(set(current)))
            & (pl.col("rank") <= p.sell_rank * p.top_n)
        ).head(p.top_n)
        fill = order.filter(~pl.col("instrument_id").is_in(keep["instrument_id"].implode())).head(
            p.top_n - len(keep)
        )
        chosen = pl.concat([keep, fill])["instrument_id"]
        weight = min(1 / len(chosen), p.max_weight) if len(chosen) else 0.0
        return pl.DataFrame(
            {"instrument_id": chosen, "weight": [weight] * len(chosen)}, schema=WEIGHT_SCHEMA
        )
