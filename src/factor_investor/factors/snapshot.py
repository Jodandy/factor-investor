"""Base metrics as of one month-end snapshot.

`build-base-metrics` stores one value per instrument and month-end date (the
dates of `month_end_dates`): fundamental metrics from reports known on that
date (`known_from <= date`), price metrics from total returns up to that date.
This reads one snapshot as is, without transformation or normalization.
"""

from datetime import date

import polars as pl
from sqlalchemy import text

from factor_investor.db import get_session

SNAPSHOT_SCHEMA = {"instrument_id": pl.Int32, "value": pl.Float64}


def metric_snapshot(metric: str, as_of_date: date) -> pl.DataFrame:
    """[instrument_id, value] for `metric` on the snapshot date as_of_date.

    Fundamental rows are also required to have known_from <= as_of_date, so a
    report published after the date can never be read, even if a build were
    wrong. Empty if the date is not a snapshot date or the metric is unknown.
    """
    query = text("""
        SELECT instrument_id, value FROM fundamental_metrics
        WHERE metric = :metric AND date = :as_of AND known_from <= :as_of
          AND value IS NOT NULL
        UNION ALL
        SELECT instrument_id, value FROM price_metrics
        WHERE metric = :metric AND date = :as_of AND value IS NOT NULL
    """)
    with get_session() as session:
        rows = session.execute(query, {"metric": metric, "as_of": as_of_date}).all()
    return pl.DataFrame(
        [(i, float(v)) for i, v in rows], schema=SNAPSHOT_SCHEMA, orient="row"
    ).sort("instrument_id")
