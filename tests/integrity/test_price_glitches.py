"""Extreme price moves are withheld until confirmed, using only past prices.

Börsdata's price history has one-day spikes that reverse (Transferator B x12.2,
Kvix x14.6). A backtest must not trade at those prices, but it may not use
later prices to decide that an earlier one was wrong either. So a move beyond
the band is withheld (the instrument has no price) until the new level has
held for CONFIRM_DAYS days with trades, or MAX_WAIT_DAYS prices in all; a
spike that reverses is never used.

A confirmed rise above SPLIT_BAND is a reverse split missing from the price
adjustment (Atos 2025-04-30: x10,217, its 1:10,000 reverse split): the series
continues from the new level scaled back to the old one, so the position keeps
its value. Falls are never rescaled (real losses, or fake losses from missing
forward splits), so errors can only lower returns.
"""

from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest

from factor_investor.backtest.prices import (
    CONFIRM_DAYS,
    MAX_WAIT_DAYS,
    MOVE_BAND,
    PRICE_FILTER_ID,
    SPLIT_BAND,
    PricePanel,
    confirm_extreme_moves,
)

START = date(2020, 1, 1)


def series(
    *prices: float, instrument_id: int = 1, volumes: list[int] | None = None
) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "instrument_id": [instrument_id] * len(prices),
            "date": [START + timedelta(days=i) for i in range(len(prices))],
            "price": list(prices),
            "volume": volumes or [1000] * len(prices),
        },
        schema={
            "instrument_id": pl.Int32,
            "date": pl.Date,
            "price": pl.Float64,
            "volume": pl.Int64,
        },
    )


def kept(frame: pl.DataFrame) -> list[float]:
    return confirm_extreme_moves(frame)["price"].to_list()


def test_settings() -> None:
    assert MOVE_BAND == 3.0
    assert CONFIRM_DAYS == 5
    assert MAX_WAIT_DAYS == 20
    assert SPLIT_BAND == 10.0
    assert PRICE_FILTER_ID == "price_filter_v2"


def test_normal_moves_are_kept() -> None:
    prices = (10.0, 12.0, 8.0, 20.0, 7.0)
    assert kept(series(*prices)) == list(prices)


def test_spike_that_reverses_is_withheld() -> None:
    assert kept(series(10.0, 10.0, 122.0, 10.5, 10.0)) == [10.0, 10.0, 10.5, 10.0]


def test_crash_that_reverses_is_withheld() -> None:
    assert kept(series(10.0, 1.0, 1.2, 9.0, 9.5)) == [10.0, 9.0, 9.5]


def test_new_level_is_used_once_it_has_held() -> None:
    """A real crash: withheld for CONFIRM_DAYS - 1 prices, used from the CONFIRM_DAYS-th."""
    prices = (10.0, 2.0, 2.1, 1.9, 2.0, 2.2, 2.3)
    assert kept(series(*prices)) == [10.0, 2.2, 2.3]


def test_confirmed_rise_beyond_split_band_is_rescaled() -> None:
    """Atos-like: x10,000 that holds. The level is kept from before the jump
    and later moves are applied on top of it."""
    prices = (10.0, 10.0, 100_000.0, 100_000.0, 100_000.0, 100_000.0, 100_000.0, 110_000.0)
    assert kept(series(*prices)) == pytest.approx([10.0, 10.0, 10.0, 11.0])


def test_confirmed_rise_within_split_band_is_kept() -> None:
    prices = (10.0, 50.0, 50.0, 50.0, 50.0, 50.0, 55.0)
    assert kept(series(*prices)) == [10.0, 50.0, 55.0]


def test_confirmed_fall_beyond_split_band_is_kept() -> None:
    prices = (100.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.1)
    assert kept(series(*prices)) == [100.0, 1.0, 1.1]


def test_quotes_without_trades_do_not_confirm_a_move() -> None:
    """Kvix 2024-10: a bad 0.70 print repeated for days with zero volume."""
    prices = (10.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 9.0)
    volumes = [1000, 500, 0, 0, 0, 0, 0, 1000]
    assert kept(series(*prices, volumes=volumes)) == [10.0, 9.0]


def test_move_is_used_after_max_wait_even_without_trades() -> None:
    """An illiquid stock that crashes on quotes alone must not be valued at its
    old price for months (the engine would sell it there when it goes stale)."""
    n = MAX_WAIT_DAYS + 2
    prices = (10.0,) + (1.0,) * n
    volumes = [1000] + [0] * n
    assert kept(series(*prices, volumes=volumes)) == [10.0, 1.0, 1.0, 1.0]


def test_missing_volume_counts_as_traded() -> None:
    """Synthetic panels have no volume column; every price is treated as a trade."""
    frame = series(10.0, 2.0, 2.0, 2.0, 2.0, 2.0).drop("volume")
    assert confirm_extreme_moves(frame)["price"].to_list() == [10.0, 2.0]


def test_each_instrument_is_judged_on_its_own_prices() -> None:
    frame = pl.concat(
        [series(10.0, 50.0, 10.0, instrument_id=1), series(100.0, 101.0, 99.0, instrument_id=2)]
    )
    result = confirm_extreme_moves(frame.sample(fraction=1.0, shuffle=True, seed=1))
    assert sorted(result.rows()) == sorted(
        [
            (1, START, 10.0, 1000),
            (1, START + timedelta(days=2), 10.0, 1000),
            *series(100.0, 101.0, 99.0, instrument_id=2).rows(),
        ]
    )


def glitchy_series(seed: int, n: int = 200) -> pl.DataFrame:
    rng = np.random.default_rng(seed)
    path = 10 * np.cumprod(1 + rng.normal(0, 0.05, n))
    for i in rng.choice(n, 12, replace=False):
        path[i] *= rng.choice([0.05, 0.2, 5.0, 20.0])
    for i in rng.choice(n - 20, 2, replace=False):
        path[i:] *= rng.choice([0.1, 10.0])
    volumes = [int(v) for v in rng.choice([0, 0, 500], n)]
    return series(*(float(p) for p in path), volumes=volumes)


@pytest.mark.parametrize("seed", range(20))
def test_decision_on_a_day_never_depends_on_later_prices(seed: int) -> None:
    """Truncation: filtering the history up to day t gives exactly the same
    prices up to t as filtering the full history."""
    full = glitchy_series(seed)
    filtered_full = confirm_extreme_moves(full)
    assert filtered_full.height < full.height  # the test series do contain glitches
    for cut in range(1, full.height + 1):
        cutoff = full["date"][cut - 1]
        prefix = confirm_extreme_moves(full.head(cut))
        assert prefix.equals(filtered_full.filter(pl.col("date") <= cutoff)), cut


def test_panel_withholds_spikes_but_keeps_the_day_in_the_calendar() -> None:
    frame = series(10.0, 120.0, 10.0)
    panel = PricePanel.from_frame(frame)
    assert panel.trading_days == frame["date"].to_list()
    assert panel.prices_on(START + timedelta(days=1)).is_empty()
    assert panel.prices_on(START).columns == ["instrument_id", "price"]
    assert panel.prices_on(START + timedelta(days=2)).rows() == [(1, 10.0)]
