"""ichimoku_v1: Ichimoku Kinko Hyo on daily closing prices (total return index).

Mid-range = (highest + lowest) / 2 over a window; computed on closes, since
the daily series is a dividend-adjusted close (a common close-only variant).
- conversion line (tenkan): mid-range of the last 9 days
- base line (kijun): mid-range of the last 26 days
- cloud today: span A = (tenkan + kijun) / 2 and span B = 52-day mid-range,
  both as computed 26 days ago (the cloud is drawn 26 days ahead)
- leading cloud: span A and B as computed today
- lagging span (chikou): today's close against the close 26 days ago
Every line uses closes up to the view's date only.

Modes:
- above_cloud: close above the cloud
- full: above the cloud, conversion above base line, leading cloud green
  (span A > span B) and close above the close 26 days ago
- not_below_cloud: close not below the cloud (for exits: off = below it)
"""

from typing import Literal

import numpy as np
from pydantic import Field

from factor_investor.components.base import (
    ComponentParams,
    DailyPriceView,
    SignalComponent,
    register_component,
)

TENKAN, KIJUN, SPAN_B, DISPLACEMENT = 9, 26, 52, 26


def _mid(values: np.ndarray) -> float:
    return float((np.nanmax(values) + np.nanmin(values)) / 2)


def ichimoku_lines(closes: np.ndarray) -> dict[str, float]:
    """Lines at the last close; needs SPAN_B + DISPLACEMENT closes."""
    past = closes[: len(closes) - DISPLACEMENT]
    tenkan, kijun = _mid(closes[-TENKAN:]), _mid(closes[-KIJUN:])
    return {
        "tenkan": tenkan,
        "kijun": kijun,
        "span_a": (_mid(past[-TENKAN:]) + _mid(past[-KIJUN:])) / 2,
        "span_b": _mid(past[-SPAN_B:]),
        "span_a_now": (tenkan + kijun) / 2,
        "span_b_now": _mid(closes[-SPAN_B:]),
        "lagging_reference": float(past[-1]),
    }


class IchimokuParams(ComponentParams):
    mode: Literal["above_cloud", "full", "not_below_cloud"]
    min_coverage: float = Field(default=0.8, gt=0, le=1)


@register_component
class Ichimoku(SignalComponent):
    id = "ichimoku_v1"
    Params = IchimokuParams

    def run(self, view: DailyPriceView, instruments: list[int]) -> set[int]:
        p = self.params
        assert isinstance(p, IchimokuParams)
        days = SPAN_B + DISPLACEMENT
        window = view.prices(instruments, days)
        on = set()
        for j, instrument in enumerate(instruments):
            closes = window[:, j]
            close = closes[-1]
            if np.isnan(close) or np.isnan(closes[-DISPLACEMENT - 1]):
                continue
            if np.count_nonzero(~np.isnan(closes)) < p.min_coverage * days:
                continue
            lines = ichimoku_lines(closes)
            top = max(lines["span_a"], lines["span_b"])
            bottom = min(lines["span_a"], lines["span_b"])
            if p.mode == "not_below_cloud":
                ok = close >= bottom
            else:
                ok = close > top
                if p.mode == "full":
                    ok = ok and (
                        lines["tenkan"] > lines["kijun"]
                        and lines["span_a_now"] > lines["span_b_now"]
                        and close > lines["lagging_reference"]
                    )
            if ok:
                on.add(instrument)
        return on
