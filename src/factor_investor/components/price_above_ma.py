"""price_above_ma_v1: the latest price is above its moving average (trend)."""

import numpy as np
from pydantic import Field

from factor_investor.components.base import (
    ComponentParams,
    DailyPriceView,
    SignalComponent,
    register_component,
)


class PriceAboveMaParams(ComponentParams):
    days: int = Field(default=200, ge=2)
    # share of the window that must have prices (new or illiquid listings: no signal)
    min_coverage: float = Field(default=0.8, gt=0, le=1)


@register_component
class PriceAboveMa(SignalComponent):
    id = "price_above_ma_v1"
    Params = PriceAboveMaParams

    def run(self, view: DailyPriceView, instruments: list[int]) -> set[int]:
        p = self.params
        assert isinstance(p, PriceAboveMaParams)
        window = view.prices(instruments, p.days)
        on = set()
        for j, instrument in enumerate(instruments):
            column = window[:, j]
            valid = column[~np.isnan(column)]
            if len(valid) >= p.min_coverage * p.days and valid[-1] > valid.mean():
                on.add(instrument)
        return on
