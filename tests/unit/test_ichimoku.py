"""ichimoku_v1 on closing prices (tenkan 9, kijun 26, span B 52, displacement 26)."""

from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest

from factor_investor.components.base import build_component
from factor_investor.components.ichimoku import ichimoku_lines
from factor_investor.pipeline.daily import DailyPrices, DailyView

DAYS = [date(2020, 1, 1) + timedelta(days=i) for i in range(200)]


def view(series: dict[int, list[float]], at: int = 199) -> DailyView:
    rows = [(i, DAYS[t], p) for i, values in series.items() for t, p in enumerate(values)]
    frame = pl.DataFrame(
        rows, schema={"instrument_id": pl.Int32, "date": pl.Date, "price": pl.Float64}, orient="row"
    )
    return DailyView(DailyPrices.from_frame(frame), DAYS[at])


def signal(mode: str, series: dict[int, list[float]], at: int = 199) -> set[int]:
    return build_component("ichimoku_v1", {"mode": mode}).run(view(series, at), sorted(series))  # type: ignore[attr-defined, no-any-return]


RISING = [100 * 1.01**t for t in range(200)]
FALLING = [100 * 0.99**t for t in range(200)]
FLAT = [100.0] * 200
REVERSAL = [100 * 1.01**t for t in range(170)] + [100 * 1.01**170 * 0.97**k for k in range(1, 31)]


def test_lines_on_a_known_series() -> None:
    closes = np.arange(1.0, 101.0)  # 1..100
    lines = ichimoku_lines(closes)
    assert lines["tenkan"] == pytest.approx((100 + 92) / 2)
    assert lines["kijun"] == pytest.approx((100 + 75) / 2)
    # spans as computed 26 days ago (close 74): tenkan (74+66)/2, kijun (74+49)/2, B (74+23)/2
    assert lines["span_a"] == pytest.approx(((74 + 66) / 2 + (74 + 49) / 2) / 2)
    assert lines["span_b"] == pytest.approx((74 + 23) / 2)
    assert lines["lagging_reference"] == 74


def test_modes() -> None:
    series = {1: RISING, 2: FALLING, 3: FLAT, 4: REVERSAL}
    assert signal("above_cloud", series) == {1}
    assert signal("full", series) == {1}
    # not below the cloud: rising, and flat (price on the cloud); not falling
    assert 1 in signal("not_below_cloud", series) and 2 not in signal("not_below_cloud", series)


def test_reversal_turns_the_signal_off_after_it_happens() -> None:
    assert signal("above_cloud", {4: REVERSAL}, at=165) == {4}
    assert signal("above_cloud", {4: REVERSAL}, at=199) == set()


def test_too_little_history_gives_no_signal() -> None:
    short = {1: [float("nan")] * 150 + RISING[:50]}
    assert signal("above_cloud", short) == set()


def test_later_prices_do_not_change_the_signal() -> None:
    early = signal("full", {4: REVERSAL}, at=165)
    assert early == signal("full", {4: REVERSAL[:166] + [1.0] * 34}, at=165)


def test_invalid_mode() -> None:
    with pytest.raises(ValueError):
        build_component("ichimoku_v1", {"mode": "sideways"})
