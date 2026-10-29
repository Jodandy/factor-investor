"""Portfolio components (stage 5)."""

import polars as pl
from pydantic import Field

from factor_investor.components.base import (
    WEIGHT_SCHEMA,
    ComponentParams,
    PortfolioComponent,
    register_component,
)


class TopNHysteresisParams(ComponentParams):
    top_n: int = Field(gt=0)
    sell_rank: float = Field(default=1.0, ge=1.0)


@register_component
class TopNHysteresis(PortfolioComponent):
    """Equal weight in N names: current holdings are kept while they rank
    within sell_rank * N; free slots go to the best-ranked names not held.
    Ties rank by lowest instrument id; names without a score are never held."""

    id = "top_n_hysteresis_v1"
    Params = TopNHysteresisParams

    def run(self, ranked: pl.DataFrame, current: list[int]) -> pl.DataFrame:
        p = self.params
        assert isinstance(p, TopNHysteresisParams)
        order = (
            ranked.drop_nulls("score")
            .sort(["score", "instrument_id"], descending=[True, False])
            .with_row_index("rank", offset=1)
        )
        held = set(current)
        keep = order.filter(
            pl.col("instrument_id").is_in(list(held)) & (pl.col("rank") <= p.sell_rank * p.top_n)
        ).head(p.top_n)
        fill = order.filter(~pl.col("instrument_id").is_in(keep["instrument_id"].implode())).head(
            p.top_n - len(keep)
        )
        chosen = pl.concat([keep, fill])["instrument_id"]
        weight = 1 / len(chosen) if len(chosen) else 0.0
        return pl.DataFrame(
            {"instrument_id": chosen, "weight": [weight] * len(chosen)}, schema=WEIGHT_SCHEMA
        )
