"""Exchange rates from Börsdata currency pairs (instrument type 6)."""

from datetime import date, timedelta

from sqlalchemy import text

from factor_investor.db import get_session

FX_INSTRUMENT_TYPE = 6


def usd_rates(as_of_date: date, max_age_days: int = 7) -> dict[str, float]:
    """Units of each currency per USD, from the USD/XXX pairs.

    Each rate is the pair's last close on or before as_of_date, at most
    max_age_days old; quotes after as_of_date are never used.

    Returns:
        Currency code -> units per USD (USD itself is 1.0)
    """
    query = text("""
        SELECT DISTINCT ON (i.ins_id) i.name, s.close
        FROM stock_prices s
        JOIN instruments i ON i.ins_id = s.ins_id
        WHERE i.instrument_type = :fx_type
          AND i.name LIKE 'USD/%'
          AND s.date <= :as_of_date
          AND s.date >= :oldest
          AND s.close > 0
        ORDER BY i.ins_id, s.date DESC
    """)
    with get_session() as session:
        rows = session.execute(
            query,
            {
                "fx_type": FX_INSTRUMENT_TYPE,
                "as_of_date": as_of_date,
                "oldest": as_of_date - timedelta(days=max_age_days),
            },
        ).fetchall()

    rates = {name.removeprefix("USD/"): float(close) for name, close in rows}
    rates["USD"] = 1.0
    return rates
