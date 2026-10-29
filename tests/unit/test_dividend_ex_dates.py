"""Report dividends moved to real ex-dates from the dividend calendar."""

from datetime import date, timedelta
from decimal import Decimal

from factor_investor.universe.dividend_service import (
    CalendarDividend,
    ReportDividend,
    assign_ex_dates,
)

LAG = 30


def report(known_from: date, amount: str) -> ReportDividend:
    return ReportDividend(known_from, Decimal(amount))


def paid(ex_date: date, amount: str) -> CalendarDividend:
    return CalendarDividend(ex_date, Decimal(amount))


def test_report_amount_on_calendar_ex_date() -> None:
    """Investor B FY2009: report 1.00 (split-adjusted), calendar 4.00 as paid on
    2010-04-15. The report amount goes on the real ex-date."""
    result = assign_ex_dates(
        [report(date(2010, 1, 22), "1.00")], [paid(date(2010, 4, 15), "4.00")], LAG
    )
    assert result == [(date(2010, 4, 15), Decimal("1.00"), False)]


def test_instalments_split_in_proportion_to_calendar_amounts() -> None:
    result = assign_ex_dates(
        [report(date(2026, 1, 20), "1.40")],
        [paid(date(2026, 5, 8), "4.0"), paid(date(2026, 11, 6), "1.6")],
        LAG,
    )
    assert result == [
        (date(2026, 5, 8), Decimal("1.00"), False),
        (date(2026, 11, 6), Decimal("0.40"), False),
    ]


def test_ex_dates_before_publication_are_not_used() -> None:
    """A dividend is never credited before the report announcing it is known."""
    result = assign_ex_dates(
        [report(date(2020, 2, 10), "2.0")],
        [paid(date(2020, 1, 15), "2.0"), paid(date(2020, 5, 1), "2.0")],
        LAG,
    )
    assert result == [(date(2020, 5, 1), Decimal("2.0"), False)]


def test_window_ends_at_next_report() -> None:
    result = assign_ex_dates(
        [report(date(2020, 2, 10), "1.0"), report(date(2021, 2, 10), "3.0")],
        [paid(date(2020, 5, 1), "5"), paid(date(2021, 5, 1), "7")],
        LAG,
    )
    assert result == [
        (date(2020, 5, 1), Decimal("1.0"), False),
        (date(2021, 5, 1), Decimal("3.0"), False),
    ]


def test_window_is_capped_when_next_report_is_missing() -> None:
    """A report two years later must not pull the second year's payment into this one."""
    known = date(2020, 2, 10)
    result = assign_ex_dates(
        [report(known, "1.0")],
        [paid(date(2020, 5, 1), "1"), paid(known + timedelta(days=500), "1")],
        LAG,
    )
    assert result == [(date(2020, 5, 1), Decimal("1.0"), False)]


def test_no_calendar_entry_falls_back_to_estimate() -> None:
    known = date(2008, 2, 10)
    result = assign_ex_dates([report(known, "2.5")], [], LAG)
    assert result == [(known + timedelta(days=LAG), Decimal("2.5"), True)]


def test_zero_calendar_amounts_are_ignored() -> None:
    known = date(2010, 2, 1)
    result = assign_ex_dates([report(known, "2.0")], [paid(date(2010, 4, 15), "0")], LAG)
    assert result == [(known + timedelta(days=LAG), Decimal("2.0"), True)]


def test_ordinary_and_extra_on_same_day_become_one_dividend() -> None:
    """Volvo B 2026-04-09: ordinary 8.5 and extra 4.5 on the same ex-date."""
    result = assign_ex_dates(
        [report(date(2026, 1, 28), "13.0")],
        [paid(date(2026, 4, 9), "8.5"), paid(date(2026, 4, 9), "4.5")],
        LAG,
    )
    assert result == [(date(2026, 4, 9), Decimal("13.0"), False)]


def test_reports_published_the_same_day_are_not_double_counted() -> None:
    known = date(2015, 3, 1)
    result = assign_ex_dates(
        [report(known, "1.0"), report(known, "2.0")], [paid(date(2015, 5, 1), "2")], LAG
    )
    total = sum(amount for _, amount, _ in result)
    assert total == Decimal("3.0")
    assert (date(2015, 5, 1), Decimal("2.0"), False) in result
