"""Snapshot prices: each instrument's last price on or before the snapshot
date, never after it (needs the database)."""

from datetime import date, timedelta

from factor_investor.universe.queries import get_latest_prices

INVESTOR_B = 113


def test_closed_market_uses_previous_trading_day() -> None:
    """Nasdaq Stockholm is closed on Dec 31; Investor B must still get a price."""
    prices = get_latest_prices(date(2025, 12, 31), [INVESTOR_B])

    assert prices["date"].to_list() == [date(2025, 12, 30)]


def test_never_uses_prices_after_snapshot_date() -> None:
    as_of = date(2025, 12, 31)
    prices = get_latest_prices(as_of, max_age_days=7)

    assert len(prices) > 5000
    assert prices["date"].max() <= as_of
    assert prices["date"].min() >= as_of - timedelta(days=7)
    assert prices["instrument_id"].is_unique().all()


def test_prices_older_than_max_age_are_not_used() -> None:
    """Jan 6 is a Swedish holiday: the last price is Jan 5."""
    as_of = date(2026, 1, 6)

    assert len(get_latest_prices(as_of, [INVESTOR_B], max_age_days=0)) == 0
    assert get_latest_prices(as_of, [INVESTOR_B], max_age_days=1)["date"].to_list() == [
        date(2026, 1, 5)
    ]
