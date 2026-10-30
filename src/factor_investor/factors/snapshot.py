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


HISTORY_SCHEMA = {"instrument_id": pl.Int32, "date": pl.Date, "value": pl.Float64}


def metric_history(metric: str, from_date: date, as_of_date: date) -> pl.DataFrame:
    """[instrument_id, date, value] for every snapshot date in (from_date, as_of_date].

    Each snapshot only holds what was known on its own date (fundamentals:
    known_from <= date), so the history never contains later information.
    """
    query = text("""
        SELECT instrument_id, date, value FROM fundamental_metrics
        WHERE metric = :metric AND date > :from_date AND date <= :as_of
          AND known_from <= date AND value IS NOT NULL
        UNION ALL
        SELECT instrument_id, date, value FROM price_metrics
        WHERE metric = :metric AND date > :from_date AND date <= :as_of AND value IS NOT NULL
    """)
    with get_session() as session:
        rows = session.execute(
            query, {"metric": metric, "from_date": from_date, "as_of": as_of_date}
        ).all()
    return pl.DataFrame(
        [(i, d, float(v)) for i, d, v in rows], schema=HISTORY_SCHEMA, orient="row"
    ).sort("instrument_id", "date")


def _distinct_metrics(table: str) -> list[str]:
    # loose index scan over the metric index: fast on tens of millions of rows
    query = text(f"""
        WITH RECURSIVE m AS (
            SELECT min(metric) AS v FROM {table}
            UNION ALL
            SELECT (SELECT min(metric) FROM {table} WHERE metric > m.v) FROM m WHERE v IS NOT NULL
        )
        SELECT v FROM m WHERE v IS NOT NULL
    """)
    with get_session() as session:
        return [row[0] for row in session.execute(query).all()]


def known_metrics() -> frozenset[str]:
    """Every metric name in fundamental_metrics and price_metrics."""
    return frozenset(_distinct_metrics("fundamental_metrics") + _distinct_metrics("price_metrics"))


def metric_history_all(metric: str) -> pl.DataFrame:
    """[instrument_id, date, value] for every snapshot date (each holding only
    what was known on its own date). One query instead of one per date; callers
    must restrict it to dates up to their own (the point-in-time view does)."""
    query = text("""
        SELECT instrument_id, date, value FROM fundamental_metrics
        WHERE metric = :metric AND known_from <= date AND value IS NOT NULL
        UNION ALL
        SELECT instrument_id, date, value FROM price_metrics
        WHERE metric = :metric AND value IS NOT NULL
    """)
    with get_session() as session:
        rows = session.execute(query, {"metric": metric}).all()
    if not rows:
        return pl.DataFrame(schema=HISTORY_SCHEMA)
    ids, dates, values = zip(*rows, strict=True)
    return pl.DataFrame(
        {"instrument_id": ids, "date": dates, "value": [float(v) for v in values]},
        schema=HISTORY_SCHEMA,
    ).sort("date", "instrument_id")


ANNUAL_SCHEMA = {
    "instrument_id": pl.Int32,
    "period_end": pl.Date,
    "known_from": pl.Date,
    "value": pl.Float64,
}


def annual_reports_all(metric: str) -> pl.DataFrame:
    """Every annual report value of `metric` with the date it became known
    (fundamentals_pit, period_type year). Callers keep known_from <= their date."""
    query = text("""
        SELECT instrument_id, period_end, known_from, value FROM fundamentals_pit
        WHERE metric = :metric AND period_type = 'year' AND value IS NOT NULL
    """)
    with get_session() as session:
        rows = session.execute(query, {"metric": metric}).all()
    return pl.DataFrame(
        [(i, p, k, float(v)) for i, p, k, v in rows], schema=ANNUAL_SCHEMA, orient="row"
    )
