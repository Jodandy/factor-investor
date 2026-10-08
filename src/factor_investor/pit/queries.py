"""Query functions for point-in-time fundamentals."""

import logging
from datetime import date

import polars as pl
from sqlalchemy import text

from factor_investor.db import get_session

logger = logging.getLogger(__name__)


def as_of(
    as_of_date: date,
    instrument_ids: list[int] | None = None,
    metrics: list[str] | None = None,
    history_years: int = 5,
) -> pl.DataFrame:
    """Get point-in-time fundamental values as of a specific date.

    Returns the latest known values for each (instrument, metric, period) where
    known_from <= as_of_date. Includes up to history_years of historical periods
    per instrument.

    Args:
        as_of_date: The date to query (what was known by this date)
        instrument_ids: Filter to specific instruments (None = all)
        metrics: Filter to specific metrics (None = all)
        history_years: Number of historical years to include per instrument (default: 5)

    Returns:
        DataFrame with columns:
        - instrument_id (int)
        - metric (str)
        - period_end (date)
        - period_type (str)
        - value (float)
        - known_from (date)

    Integrity guarantee:
        All returned rows have known_from <= as_of_date

    Example:
        >>> df = as_of(date(2024, 1, 1), instrument_ids=[3], metrics=['roe', 'roic'])
        >>> print(df)
        ┌─────────────────┬────────┬────────────┬─────────────┬──────────┬────────────┐
        │ instrument_id   │ metric │ period_end │ period_type │ value    │ known_from │
        ├─────────────────┼────────┼────────────┼─────────────┼──────────┼────────────┤
        │ 3               │ roe    │ 2023-12-31 │ year        │ 0.15     │ 2024-02-15 │
        │ 3               │ roe    │ 2022-12-31 │ year        │ 0.14     │ 2023-02-14 │
        │ 3               │ roic   │ 2023-12-31 │ year        │ 0.12     │ 2024-02-15 │
        └─────────────────┴────────┴────────────┴─────────────┴──────────┴────────────┘
    """
    # Build SQL query with window functions for efficiency
    instrument_filter = ""
    if instrument_ids:
        # Convert list to SQL array format
        ids_str = ",".join(str(i) for i in instrument_ids)
        instrument_filter = f"AND instrument_id IN ({ids_str})"

    metric_filter = ""
    if metrics:
        # Convert list to SQL array format with quotes
        metrics_str = ",".join(f"'{m}'" for m in metrics)
        metric_filter = f"AND metric IN ({metrics_str})"

    # Calculate max periods to return (years x period types)
    # For year reports: history_years periods
    # For quarter/r12: history_years * 4 periods
    max_year_periods = history_years
    max_quarter_periods = history_years * 4

    query = f"""
    WITH ranked_values AS (
        SELECT
            instrument_id,
            metric,
            period_end,
            period_type,
            value,
            known_from,
            ROW_NUMBER() OVER (
                PARTITION BY instrument_id, metric, period_end, period_type
                ORDER BY known_from DESC
            ) as version_rank
        FROM fundamentals_pit
        WHERE known_from <= :as_of_date
            {instrument_filter}
            {metric_filter}
    ),
    latest_versions AS (
        SELECT *
        FROM ranked_values
        WHERE version_rank = 1  -- Latest known version of each period
    ),
    filtered_periods AS (
        SELECT
            instrument_id,
            metric,
            period_end,
            period_type,
            value,
            known_from,
            ROW_NUMBER() OVER (
                PARTITION BY instrument_id, metric, period_type
                ORDER BY period_end DESC
            ) as period_rank
        FROM latest_versions
    )
    SELECT
        instrument_id,
        metric,
        period_end,
        period_type,
        value,
        known_from
    FROM filtered_periods
    WHERE
        (period_type = 'year' AND period_rank <= :max_year_periods)
        OR (period_type IN ('quarter', 'r12') AND period_rank <= :max_quarter_periods)
    ORDER BY instrument_id, metric, period_type, period_end DESC
    """

    params = {
        "as_of_date": as_of_date,
        "max_year_periods": max_year_periods,
        "max_quarter_periods": max_quarter_periods,
    }

    logger.debug(
        f"Executing as_of query for date={as_of_date}, "
        f"instruments={len(instrument_ids) if instrument_ids else 'all'}, "
        f"metrics={len(metrics) if metrics else 'all'}"
    )

    # Execute query and load into Polars DataFrame
    with get_session() as session:
        # Execute query and load result into Polars
        result = session.execute(text(query), params)
        rows = result.fetchall()

        # Convert to Polars DataFrame
        if not rows:
            # Return empty DataFrame with correct schema
            df = pl.DataFrame(
                schema={
                    "instrument_id": pl.Int32,
                    "metric": pl.Utf8,
                    "period_end": pl.Date,
                    "period_type": pl.Utf8,
                    "value": pl.Float64,
                    "known_from": pl.Date,
                }
            )
        else:
            # Convert rows to DataFrame
            df = pl.DataFrame(
                {
                    "instrument_id": [row[0] for row in rows],
                    "metric": [row[1] for row in rows],
                    "period_end": [row[2] for row in rows],
                    "period_type": [row[3] for row in rows],
                    "value": [float(row[4]) if row[4] is not None else None for row in rows],
                    "known_from": [row[5] for row in rows],
                }
            )

    logger.debug(f"as_of query returned {len(df):,} rows")

    return df
