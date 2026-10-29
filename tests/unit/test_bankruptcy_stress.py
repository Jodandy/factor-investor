"""Synthetic bankruptcies for the survivorship stress test (pure functions)."""

from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest

from factor_investor.stress.bankruptcy import apply_failures, failure_events, uniform

MONTHS = [date(2010 + m // 12, m % 12 + 1, 28) for m in range(120)]


def panel(n: int, weak_share: float = 0.25) -> pl.DataFrame:
    """Every instrument alive every month; the first weak_share of ids are weak."""
    return pl.DataFrame(
        [(d, i, i < n * weak_share) for d in MONTHS for i in range(n)],
        schema={"date": pl.Date, "instrument_id": pl.Int32, "weak": pl.Boolean},
        orient="row",
    )


def test_uniform_is_deterministic_and_in_range() -> None:
    assert uniform(1, 5, date(2020, 1, 31)) == uniform(1, 5, date(2020, 1, 31))
    assert uniform(1, 5, date(2020, 1, 31)) != uniform(2, 5, date(2020, 1, 31))
    values = [uniform(1, i, date(2020, 1, 31)) for i in range(2000)]
    assert min(values) >= 0 and max(values) < 1
    assert abs(np.mean(values) - 0.5) < 0.03


def test_same_inputs_same_events_other_seed_other_events() -> None:
    p = panel(300)
    a = failure_events(p, rate=0.05, weak_multiplier=4.0, seed=1)
    assert a.equals(failure_events(p, rate=0.05, weak_multiplier=4.0, seed=1))
    assert not a.equals(failure_events(p, rate=0.05, weak_multiplier=4.0, seed=2))


def test_average_annual_rate_and_weak_names_fail_more_often() -> None:
    n, weak_share = 2000, 0.25
    events = failure_events(panel(n, weak_share), rate=0.03, weak_multiplier=4.0, seed=7)
    # exposure: months each name was alive (up to and including its failure month)
    failed_at = dict(events.select("instrument_id", "date").rows())
    alive = {i: sum(1 for d in MONTHS if d <= failed_at.get(i, MONTHS[-1])) for i in range(n)}
    observed_monthly = len(events) / sum(alive.values())
    assert 1 - (1 - observed_monthly) ** 12 == pytest.approx(0.03, rel=0.15)

    def rate(ids: list[int]) -> float:
        return sum(i in failed_at for i in ids) / sum(alive[i] for i in ids)

    weak, strong = list(range(int(n * weak_share))), list(range(int(n * weak_share), n))
    assert rate(weak) / rate(strong) == pytest.approx(4.0, rel=0.25)


def test_each_instrument_fails_at_most_once() -> None:
    events = failure_events(panel(500), rate=0.2, weak_multiplier=4.0, seed=3)
    assert events["instrument_id"].n_unique() == len(events)


def test_zero_rate_gives_no_events() -> None:
    assert failure_events(panel(100), rate=0.0, weak_multiplier=4.0, seed=1).is_empty()


def test_failure_wipes_out_the_price_from_the_next_day() -> None:
    days = [date(2020, 1, 27) + timedelta(days=i) for i in range(10)]
    prices = pl.DataFrame(
        {
            "instrument_id": [1] * 10 + [2] * 10,
            "date": days * 2,
            "price": [float(100 + i) for i in range(10)] * 2,
            "volume": [0] * 20,
        },
        schema={
            "instrument_id": pl.Int32,
            "date": pl.Date,
            "price": pl.Float64,
            "volume": pl.Int64,
        },
    )
    events = pl.DataFrame(
        {"instrument_id": [1], "date": [date(2020, 1, 31)]},
        schema={"instrument_id": pl.Int32, "date": pl.Date},
    )
    stressed = apply_failures(prices, events).sort("instrument_id", "date")
    one = stressed.filter(pl.col("instrument_id") == 1)
    before = one.filter(pl.col("date") <= date(2020, 1, 31))
    after = one.filter(pl.col("date") > date(2020, 1, 31))
    assert before["price"].to_list() == [100.0, 101.0, 102.0, 103.0, 104.0]
    assert after["price"].to_list() == [pytest.approx(104.0 * 1e-6)] * 5
    assert after["volume"].to_list() == [1] * 5  # traded: the price filter confirms the loss
    assert stressed.filter(pl.col("instrument_id") == 2).equals(
        prices.filter(pl.col("instrument_id") == 2)
    )
