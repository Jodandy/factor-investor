"""Tests for valuation ratios computed from report data and price.

Börsdata units: totals (revenues, FCF, net debt, operating income) are in
millions; number_of_shares is in millions; earnings_per_share,
book_value_per_share and dividend are per share. All in trading currency.
"""

import pytest

from factor_investor.factors.base_metrics import valuation_ratios

# AAK full year 2024 (Börsdata), price 300 SEK
AAK = {
    "earnings_per_share": 13.62,
    "book_value_per_share": 20149.0 / 259.559,
    "revenues": 45228.0,
    "operating_income": 4896.0,
    "free_cash_flow": 1754.0,
    "net_debt": 1696.0,
    "dividend": 5.0,
    "number_of_shares": 259.559,
}
PRICE = 300.0
MARKET_CAP_M = PRICE * 259.559  # millions


def test_pe_and_pb() -> None:
    ratios = valuation_ratios(PRICE, AAK)

    assert ratios["pe_ratio"] == pytest.approx(300 / 13.62)
    assert ratios["pb_ratio"] == pytest.approx(MARKET_CAP_M / 20149.0)


def test_ps_uses_consistent_units() -> None:
    assert valuation_ratios(PRICE, AAK)["ps_ratio"] == pytest.approx(MARKET_CAP_M / 45228.0)


def test_ev_ebit_includes_net_debt() -> None:
    expected = (MARKET_CAP_M + 1696.0) / 4896.0
    assert valuation_ratios(PRICE, AAK)["ev_ebit"] == pytest.approx(expected)


def test_fcf_ratios() -> None:
    ratios = valuation_ratios(PRICE, AAK)

    assert ratios["p_fcf"] == pytest.approx(MARKET_CAP_M / 1754.0)
    assert ratios["fcf_yield"] == pytest.approx(1754.0 / MARKET_CAP_M)


def test_dividend_yield_uses_dividend_per_share() -> None:
    assert valuation_ratios(PRICE, AAK)["dividend_yield"] == pytest.approx(5.0 / 300)


def test_missing_or_nonpositive_denominators_are_skipped() -> None:
    ratios = valuation_ratios(PRICE, {**AAK, "earnings_per_share": -1.0, "revenues": None})

    assert "pe_ratio" not in ratios
    assert "ps_ratio" not in ratios
    assert "pb_ratio" in ratios


def test_zero_dividend_gives_zero_yield() -> None:
    assert valuation_ratios(PRICE, {**AAK, "dividend": 0.0})["dividend_yield"] == 0.0
