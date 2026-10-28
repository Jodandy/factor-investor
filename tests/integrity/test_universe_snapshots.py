"""Universe snapshots after build-universe (needs the database)."""

from datetime import date

from sqlalchemy import text

from factor_investor.db import get_session
from factor_investor.settings import stock_instrument_types

SWEDEN = 1


def _rows(query: str, **params: object) -> list[tuple]:
    with get_session() as session:
        return list(session.execute(text(query), params).fetchall())


def test_snapshot_dates_are_weekdays() -> None:
    rows = _rows("SELECT DISTINCT date FROM universe_constituents")

    assert rows
    assert all(d.weekday() < 5 for (d,) in rows)


def test_no_nearly_empty_snapshots() -> None:
    """Weekend month-ends once produced snapshots with only crypto and FX."""
    rows = _rows(
        """
        SELECT date, count(*) FILTER (WHERE is_eligible)
        FROM universe_constituents WHERE date >= '2007-01-01' GROUP BY date
        """
    )

    assert min(n for _, n in rows) > 1000


def test_only_stock_types_in_universe() -> None:
    rows = _rows(
        """
        SELECT DISTINCT i.instrument_type
        FROM universe_constituents u JOIN instruments i ON i.ins_id = u.instrument_id
        """
    )

    assert {t for (t,) in rows} <= set(stock_instrument_types())


def test_closed_market_keeps_its_stocks() -> None:
    """Nasdaq Stockholm is closed on Dec 31; Swedish stocks must stay in."""
    rows = _rows(
        """
        SELECT u.date, count(*)
        FROM universe_constituents u JOIN instruments i ON i.ins_id = u.instrument_id
        WHERE u.is_eligible AND i.country_id = :sweden AND u.date IN (:nov, :dec)
        GROUP BY u.date
        """,
        sweden=SWEDEN,
        nov=date(2025, 11, 28),
        dec=date(2025, 12, 31),
    )
    counts = dict(rows)

    assert counts[date(2025, 12, 31)] >= 0.95 * counts[date(2025, 11, 28)]
