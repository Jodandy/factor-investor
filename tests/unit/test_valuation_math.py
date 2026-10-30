"""Relative upside from own multiple history; owner-earnings DCF and its IRR."""

import math

import numpy as np
import pytest

from factor_investor.components.valuation import (
    DcfParams,
    dcf_value,
    implied_return,
    multiple_upside,
)


def test_upside_to_the_median_and_upper_band_of_own_history() -> None:
    history = np.array([10.0, 12.0, 14.0, 16.0, 18.0])  # median 14, 75th percentile 16
    mid, high = multiple_upside(7.0, history)
    assert mid == pytest.approx(14 / 7 - 1)
    assert high == pytest.approx(16 / 7 - 1)


def test_non_positive_multiples_are_not_valid() -> None:
    assert multiple_upside(-5.0, np.array([10.0, 12.0, 14.0])) == (None, None)
    # non-positive history values (losses) are left out
    mid, _ = multiple_upside(10.0, np.array([-3.0, 10.0, 20.0, 30.0]))
    assert mid == pytest.approx(20 / 10 - 1)
    assert multiple_upside(10.0, np.array([])) == (None, None)


def test_dcf_without_growth_is_an_annuity_plus_exit() -> None:
    p = DcfParams(horizon=10, exit_multiple=12.0, terminal_growth=0.0)
    r, oe = 0.08, 5.0
    annuity = sum(oe / (1 + r) ** t for t in range(1, 11))
    exit_value = oe * 12 / (1 + r) ** 10
    assert dcf_value(oe, growth=0.0, rate=r, params=p) == pytest.approx(annuity + exit_value)


def test_growth_fades_linearly_to_terminal() -> None:
    p = DcfParams(horizon=3, exit_multiple=10.0, terminal_growth=0.03)
    # growth 9%, 6%, 3% in years 1..3
    cf1, cf2, cf3 = 1.09, 1.09 * 1.06, 1.09 * 1.06 * 1.03
    expected = cf1 + cf2 + cf3 + cf3 * 10
    assert dcf_value(1.0, growth=0.09, rate=0.0, params=p) == pytest.approx(expected)


def test_implied_return_inverts_the_value() -> None:
    p = DcfParams()
    for rate in (-0.05, 0.0, 0.07, 0.15, 0.4):
        price = dcf_value(4.0, growth=0.06, rate=rate, params=p)
        assert implied_return(4.0, 0.06, price, p) == pytest.approx(rate, abs=1e-6)


def test_implied_return_is_clamped_at_the_edges() -> None:
    p = DcfParams()
    assert implied_return(10.0, 0.05, 0.01, p) == 1.0  # absurdly cheap
    assert implied_return(0.01, 0.0, 1e9, p) == -0.25  # absurdly expensive
    assert math.isnan(implied_return(-1.0, 0.05, 100.0, p))  # no positive earnings
