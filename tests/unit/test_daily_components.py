"""Daily prices and daily-clock components (timing signals, exits)."""

from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest

from factor_investor.components.base import build_component
from factor_investor.pipeline.daily import DailyPrices, DailyView

START = date(2020, 1, 1)
DAYS = [START + timedelta(days=i) for i in range(300)]


def frame(series: dict[int, list[float | None]]) -> pl.DataFrame:
    rows = [
        (i, DAYS[t], p)
        for i, values in series.items()
        for t, p in enumerate(values)
        if p is not None
    ]
    return pl.DataFrame(
        rows, schema={"instrument_id": pl.Int32, "date": pl.Date, "price": pl.Float64}, orient="row"
    )


def test_window_holds_the_last_days_up_to_as_of_only() -> None:
    prices = DailyPrices.from_frame(frame({1: [float(t) for t in range(300)], 2: [5.0] * 300}))
    window = prices.window(DAYS[99], [1, 2, 3], 10)
    assert window.shape == (10, 3)
    assert window[:, 0].tolist() == [float(t) for t in range(90, 100)]
    assert np.isnan(window[:, 2]).all()  # unknown instrument


def test_window_is_identical_on_data_truncated_at_as_of() -> None:
    rng = np.random.default_rng(1)
    full = frame({i: list(100 * np.cumprod(1 + rng.normal(0, 0.02, 300))) for i in range(5)})
    as_of = DAYS[180]
    truncated = DailyPrices.from_frame(full.filter(pl.col("date") <= as_of))
    complete = DailyPrices.from_frame(full)
    for days in (5, 50, 200):
        np.testing.assert_array_equal(
            complete.window(as_of, list(range(5)), days),
            truncated.window(as_of, list(range(5)), days),
        )


def signals(
    component: str, params: dict[str, object], series: dict[int, list[float | None]], at: int
) -> set[int]:
    view = DailyView(DailyPrices.from_frame(frame(series)), DAYS[at])
    return build_component(component, params).run(view, sorted(series))  # type: ignore[attr-defined, no-any-return]


def test_price_above_moving_average() -> None:
    rising = [float(t) for t in range(300)]
    falling = [float(300 - t) for t in range(300)]
    short = [None] * 250 + [float(t) for t in range(50)]  # too little history
    assert signals("price_above_ma_v1", {"days": 200}, {1: rising, 2: falling, 3: short}, 299) == {
        1
    }


def test_breakout_needs_a_new_high() -> None:
    flat_then_jump = [10.0] * 299 + [11.0]
    flat = [10.0] * 300
    below = [12.0] * 250 + [11.0] * 50
    assert signals("breakout_v1", {"days": 50}, {1: flat_then_jump, 2: flat, 3: below}, 299) == {
        1,
        2,
    }


def test_signals_use_no_later_prices() -> None:
    """A jump after as_of must not change the signal on as_of."""
    base = [10.0] * 300
    jump = [10.0] * 200 + [20.0] * 100
    assert signals("breakout_v1", {"days": 50}, {1: jump}, 199) == signals(
        "breakout_v1", {"days": 50}, {1: base}, 199
    )


def test_trailing_stop() -> None:
    positions = pl.DataFrame(
        {
            "instrument_id": [1, 2, 3],
            "entry_price": [100.0, 100.0, 100.0],
            "high": [150.0, 150.0, 100.0],
            "price": [112.0, 113.0, 76.0],
        },
        schema={
            "instrument_id": pl.Int32,
            "entry_price": pl.Float64,
            "high": pl.Float64,
            "price": pl.Float64,
        },
    )
    stop = build_component("trailing_stop_v1", {"pct": 0.25})
    assert stop.run(positions) == {1}  # type: ignore[attr-defined]
    # 2 is 24.7% below its high; 3 is 24% below entry (= its high): both kept


def test_invalid_params() -> None:
    with pytest.raises(ValueError):
        build_component("trailing_stop_v1", {"pct": 1.5})
    with pytest.raises(ValueError):
        build_component("price_above_ma_v1", {"days": 1})
