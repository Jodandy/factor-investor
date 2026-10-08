"""Query functions for universe and total returns data."""

from datetime import date

import polars as pl
from sqlalchemy import text

from factor_investor.db import get_session


def get_universe(
    as_of_date: date,
    is_eligible: bool | None = None,
    instrument_ids: list[int] | None = None,
) -> pl.DataFrame:
    """Get universe constituents as of a specific date.

    Args:
        as_of_date: Date to query universe for
        is_eligible: Filter by eligibility (None = all, True = only eligible, False = only excluded)
        instrument_ids: Optional list of instrument IDs to filter

    Returns:
        DataFrame with columns: instrument_id, date, market_cap_local, median_turnover_60d,
        price, years_of_history, is_eligible, exclusion_reason, liquidity_bucket
    """
    query_parts = ["SELECT * FROM universe_constituents WHERE date = :as_of_date"]

    params: dict[str, date | bool | str] = {"as_of_date": as_of_date}

    if is_eligible is not None:
        query_parts.append("AND is_eligible = :is_eligible")
        params["is_eligible"] = is_eligible

    if instrument_ids:
        ids_str = ",".join(str(i) for i in instrument_ids)
        query_parts.append(f"AND instrument_id IN ({ids_str})")

    query_parts.append("ORDER BY market_cap_local DESC NULLS LAST")

    query = " ".join(query_parts)

    with get_session() as session:
        result = session.execute(text(query), params)
        rows = result.fetchall()

        if not rows:
            return pl.DataFrame(
                schema={
                    "instrument_id": pl.Int32,
                    "date": pl.Date,
                    "market_cap_local": pl.Float64,
                    "median_turnover_60d": pl.Float64,
                    "price": pl.Float64,
                    "years_of_history": pl.Float64,
                    "is_eligible": pl.Boolean,
                    "exclusion_reason": pl.Utf8,
                    "liquidity_bucket": pl.Int32,
                }
            )

        # Convert to DataFrame
        return pl.DataFrame(
            {
                "instrument_id": [row[1] for row in rows],
                "date": [row[2] for row in rows],
                "market_cap_local": [float(row[3]) if row[3] else None for row in rows],
                "median_turnover_60d": [float(row[4]) if row[4] else None for row in rows],
                "price": [float(row[5]) if row[5] else None for row in rows],
                "years_of_history": [float(row[6]) if row[6] else None for row in rows],
                "is_eligible": [row[7] for row in rows],
                "exclusion_reason": [row[8] for row in rows],
                "liquidity_bucket": [row[9] for row in rows],
            }
        )


def get_prices_on_date(
    as_of_date: date,
    instrument_ids: list[int] | None = None,
) -> pl.DataFrame:
    """Get prices for all instruments on a specific date.

    Args:
        as_of_date: Date to get prices for
        instrument_ids: Optional list of instrument IDs to filter

    Returns:
        DataFrame with columns: instrument_id, date, price
    """
    query_parts = ["SELECT instrument_id, date, close_price as price FROM total_returns WHERE date = :as_of_date"]

    params: dict[str, date] = {"as_of_date": as_of_date}

    if instrument_ids:
        ids_str = ",".join(str(i) for i in instrument_ids)
        query_parts.append(f"AND instrument_id IN ({ids_str})")

    query = " ".join(query_parts)

    with get_session() as session:
        result = session.execute(text(query), params)
        rows = result.fetchall()

        if not rows:
            return pl.DataFrame(schema={"instrument_id": pl.Int32, "date": pl.Date, "price": pl.Float64})

        return pl.DataFrame(
            {
                "instrument_id": [row[0] for row in rows],
                "date": [row[1] for row in rows],
                "price": [float(row[2]) if row[2] else None for row in rows],
            }
        )


def get_total_returns(
    instrument_ids: list[int],
    from_date: date,
    to_date: date,
) -> pl.DataFrame:
    """Get total return series for instruments.

    Args:
        instrument_ids: List of instrument IDs
        from_date: Start date (inclusive)
        to_date: End date (inclusive)

    Returns:
        DataFrame with columns: instrument_id, date, close_price, total_return_index,
        dividend_on_date
    """
    if not instrument_ids:
        return pl.DataFrame(
            schema={
                "instrument_id": pl.Int32,
                "date": pl.Date,
                "close_price": pl.Float64,
                "total_return_index": pl.Float64,
                "dividend_on_date": pl.Float64,
            }
        )

    ids_str = ",".join(str(i) for i in instrument_ids)

    query = f"""
        SELECT
            instrument_id,
            date,
            close_price,
            total_return_index,
            dividend_on_date
        FROM total_returns
        WHERE instrument_id IN ({ids_str})
          AND date >= :from_date
          AND date <= :to_date
        ORDER BY instrument_id, date
    """

    with get_session() as session:
        result = session.execute(text(query), {"from_date": from_date, "to_date": to_date})
        rows = result.fetchall()

        if not rows:
            return pl.DataFrame(
                schema={
                    "instrument_id": pl.Int32,
                    "date": pl.Date,
                    "close_price": pl.Float64,
                    "total_return_index": pl.Float64,
                    "dividend_on_date": pl.Float64,
                }
            )

        return pl.DataFrame(
            {
                "instrument_id": [row[0] for row in rows],
                "date": [row[1] for row in rows],
                "close_price": [float(row[2]) if row[2] else None for row in rows],
                "total_return_index": [float(row[3]) if row[3] else None for row in rows],
                "dividend_on_date": [float(row[4]) if row[4] else None for row in rows],
            }
        )
