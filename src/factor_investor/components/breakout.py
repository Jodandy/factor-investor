"""breakout_v1: the latest price is at or above the highest price of the
previous `days` days (a new high)."""

import numpy as np
from pydantic import Field

from factor_investor.components.base import (
    ComponentParams,
    DailyPriceView,
    SignalComponent,
    register_component,
)


class BreakoutParams(ComponentParams):
    days: int = Field(default=50, ge=2)
    min_coverage: float = Field(default=0.8, gt=0, le=1)


@register_component
class Breakout(SignalComponent):
    id = "breakout_v1"
    Params = BreakoutParams

    def run(self, view: DailyPriceView, instruments: list[int]) -> set[int]:
        p = self.params
        assert isinstance(p, BreakoutParams)
        window = view.prices(instruments, p.days + 1)
        on = set()
        for j, instrument in enumerate(instruments):
            previous, latest = window[:-1, j], window[-1, j]
            valid = previous[~np.isnan(previous)]
            if np.isnan(latest) or len(valid) < p.min_coverage * p.days:
                continue
            if latest >= valid.max():
                on.add(instrument)
        return on
