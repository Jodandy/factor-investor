"""Sleeves: an ensemble of strategies, each with its own share of capital."""

from datetime import date, timedelta

import polars as pl
import pytest

from factor_investor.ensemble.sleeves import combine_sleeves, rebalance_days

DAYS = [date(2024, 1, 1) + timedelta(days=i) for i in range(200)]


def returns(daily: float | list[float]) -> pl.DataFrame:
    values = daily if isinstance(daily, list) else [daily] * len(DAYS)
    return pl.DataFrame({"date": DAYS, "portfolio_return": values})


def value(frame: pl.DataFrame) -> float:
    return float((1 + frame["portfolio_return"]).product())


def test_one_sleeve_is_the_member() -> None:
    member = returns(0.001)
    combined = combine_sleeves([member], [1.0], set(), cost_bps=10)
    assert value(combined) == pytest.approx(value(member))


def test_without_rebalancing_sleeves_drift() -> None:
    a, b = returns(0.01), returns(0.0)
    combined = combine_sleeves([a, b], [0.5, 0.5], set(), cost_bps=10)
    assert value(combined) == pytest.approx(0.5 * 1.01**200 + 0.5)


def test_rebalancing_restores_weights_and_charges_the_money_moved() -> None:
    a = returns([0.1] + [0.0] * 199)  # +10% on day 0, then flat
    b = returns(0.0)
    combined = combine_sleeves([a, b], [0.5, 0.5], {DAYS[0]}, cost_bps=10)
    # end of day 0: sleeves 0.55 and 0.5; 0.025 moves out of a into b (traded 0.05)
    expected = 1.05 * (1 - 0.001 * 0.05 / 1.05)
    assert value(combined) == pytest.approx(expected)


def test_rebalance_days_are_the_last_trading_day_of_each_period() -> None:
    days = [
        date(2024, 3, 28),
        date(2024, 3, 29),
        date(2024, 4, 2),
        date(2024, 6, 28),
        date(2024, 7, 1),
    ]
    assert rebalance_days(days, "quarterly") == {date(2024, 3, 29), date(2024, 6, 28)}
    assert rebalance_days(days, "monthly") == {
        date(2024, 3, 29),
        date(2024, 4, 2),
        date(2024, 6, 28),
    }


def test_members_must_share_dates_and_weights_sum_to_one() -> None:
    with pytest.raises(ValueError, match="weights"):
        combine_sleeves([returns(0.0), returns(0.0)], [0.5, 0.6], set(), cost_bps=10)
    shorter = returns(0.0).head(100)
    with pytest.raises(ValueError, match="dates"):
        combine_sleeves([returns(0.0), shorter], [0.5, 0.5], set(), cost_bps=10)
