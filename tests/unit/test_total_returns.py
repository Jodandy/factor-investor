"""Tests for total return index construction and dividend ex-date estimation."""

from datetime import date
from decimal import Decimal

import pytest

from factor_investor.universe.dividend_service import (
    DividendService,
    compute_total_return_index,
)

# Thu, Fri, Mon, Tue
PRICES = [
    (date(2024, 3, 7), Decimal("100")),
    (date(2024, 3, 8), Decimal("100")),
    (date(2024, 3, 11), Decimal("95")),
    (date(2024, 3, 12), Decimal("95")),
]


def by_date(rows: list[dict]) -> dict[date, dict]:
    return {r["date"]: r for r in rows}


def test_dividend_on_trading_day_is_reinvested() -> None:
    rows = by_date(compute_total_return_index(PRICES, [(date(2024, 3, 11), Decimal("5"))]))

    assert rows[date(2024, 3, 11)]["dividend_on_date"] == Decimal("5")
    # Price drops by exactly the dividend: total return is flat
    assert rows[date(2024, 3, 12)]["total_return_index"] == pytest.approx(Decimal("100"))


def test_dividend_on_weekend_moves_to_next_trading_day() -> None:
    """Estimated ex-dates often fall on non-trading days; they must not be lost."""
    rows = by_date(compute_total_return_index(PRICES, [(date(2024, 3, 9), Decimal("5"))]))

    assert rows[date(2024, 3, 11)]["dividend_on_date"] == Decimal("5")
    assert rows[date(2024, 3, 12)]["total_return_index"] == pytest.approx(Decimal("100"))


def test_dividends_on_same_trading_day_are_summed() -> None:
    divs = [(date(2024, 3, 9), Decimal("2")), (date(2024, 3, 11), Decimal("3"))]
    rows = by_date(compute_total_return_index(PRICES, divs))

    assert rows[date(2024, 3, 11)]["dividend_on_date"] == Decimal("5")


def test_dividend_after_last_price_is_ignored() -> None:
    rows = compute_total_return_index(PRICES, [(date(2024, 3, 20), Decimal("5"))])

    assert all(r["dividend_on_date"] is None for r in rows)
    assert rows[-1]["total_return_index"] == pytest.approx(Decimal("95"))


class TestExDateEstimate:
    def test_based_on_publication_date(self) -> None:
        ex_date = DividendService().estimate_ex_date(
            report_date=date(2024, 2, 5), period_end=date(2023, 12, 31)
        )
        assert ex_date == date(2024, 3, 7)  # known_from (2024-02-06) + 30

    def test_implausible_publication_date_uses_pit_fallback(self) -> None:
        """Same placeholder handling as the PIT layer: no dividend before the
        report announcing it could have been known."""
        ex_date = DividendService().estimate_ex_date(
            report_date=date(2023, 12, 31), period_end=date(2023, 12, 31)
        )
        assert ex_date == date(2024, 4, 30)  # period_end + 91 + 30

    def test_missing_publication_date_uses_pit_fallback(self) -> None:
        ex_date = DividendService().estimate_ex_date(
            report_date=None, period_end=date(2023, 12, 31)
        )
        assert ex_date == date(2024, 4, 30)
