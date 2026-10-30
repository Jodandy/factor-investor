"""owner_earnings_irr_filter_v1 and owner_earnings_irr_score_v1: absolute
valuation (H11, the Buffett-proxy idea): the annual return implied by today's
price with owner earnings = mean EPS of the last fiscal years, growth
min(cap, ROE x retention) fading to terminal growth, sold at an exit multiple
(see valuation.py). The filter keeps names with implied return >= min_irr
(buy rule, e.g. 12%; or hold rule, e.g. 6%); the score ranks by it."""

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
from factor_investor.components.valuation import DcfParams, owner_earnings_returns


class OwnerEarningsParams(ComponentParams):
    years_avg: int = Field(default=3, ge=1)
    growth_cap: float = Field(default=0.10, ge=0)
    growth_fallback: float = 0.06
    horizon: int = Field(default=10, ge=1)
    exit_multiple: float = Field(default=12.0, gt=0)
    terminal_growth: float = 0.03


class OwnerEarningsFilterParams(OwnerEarningsParams):
    min_irr: float


def _returns(view: View, instruments: pl.DataFrame, p: OwnerEarningsParams) -> pl.DataFrame:
    returns: pl.DataFrame = owner_earnings_returns(
        view,
        instruments,
        p.years_avg,
        p.growth_cap,
        p.growth_fallback,
        DcfParams(p.horizon, p.exit_multiple, p.terminal_growth),
    )
    return returns


@register_component
class OwnerEarningsIrrFilter(FilterComponent):
    id = "owner_earnings_irr_filter_v1"
    Params = OwnerEarningsFilterParams
    extra_sources = ("valuation.py",)

    def run(self, view: View, instruments: pl.DataFrame) -> pl.DataFrame:
        p = self.params
        assert isinstance(p, OwnerEarningsFilterParams)
        return (
            _returns(view, instruments, p)
            .filter(pl.col("irr") >= p.min_irr)
            .select("instrument_id")
        )


@register_component
class OwnerEarningsIrrScore(ScoreComponent):
    id = "owner_earnings_irr_score_v1"
    Params = OwnerEarningsParams
    extra_sources = ("valuation.py",)

    def run(self, view: View, instruments: pl.DataFrame) -> pl.DataFrame:
        p = self.params
        assert isinstance(p, OwnerEarningsParams)
        returns = _returns(view, instruments, p)
        pct = (pl.col("irr").rank("average") - 0.5) / pl.col("irr").count()
        return (
            instruments.select(pl.col("instrument_id").cast(pl.Int32))
            .join(
                returns.select("instrument_id", pct.alias("score")), on="instrument_id", how="left"
            )
            .cast(SCORE_SCHEMA)  # type: ignore[arg-type]
        )
