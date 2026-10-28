"""Month-end snapshot and rebalancing dates."""

from datetime import date

from factor_investor.dates import month_end_dates


def test_weekend_month_end_moves_to_friday() -> None:
    """Crypto and FX trade on weekends; a Sunday must never be a snapshot date."""
    assert month_end_dates(date(2025, 11, 1), date(2025, 11, 30)) == [date(2025, 11, 28)]
    assert month_end_dates(date(2026, 5, 1), date(2026, 5, 31)) == [date(2026, 5, 29)]


def test_weekday_month_end_is_kept() -> None:
    """Dec 31 is a weekday even though Nordic exchanges are closed; each
    instrument then uses its last price on or before that date."""
    assert month_end_dates(date(2025, 12, 1), date(2025, 12, 31)) == [date(2025, 12, 31)]


def test_month_without_completed_month_end_is_excluded() -> None:
    assert month_end_dates(date(2026, 1, 15), date(2026, 4, 10)) == [
        date(2026, 1, 30),
        date(2026, 2, 27),
        date(2026, 3, 31),
    ]


def test_one_weekday_per_month_over_full_history() -> None:
    dates = month_end_dates(date(2006, 1, 1), date(2026, 9, 30))

    assert len(dates) == 249
    assert all(d.weekday() < 5 for d in dates)
    assert len({(d.year, d.month) for d in dates}) == len(dates)
