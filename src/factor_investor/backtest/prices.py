"""In-memory price panel for the backtest engine.

The engine needs every instrument's total return index on every trading day.
Querying the database per day takes minutes per backtest, so the
`total_returns` table is exported once to Parquet and loaded into memory.

The Parquet file records the table's row count and newest `created_at`. On
load these are compared with the database, and the file is rebuilt if they
differ, so a backtest never reads prices from before a rebuild.
"""

import json
import logging
from dataclasses import dataclass
from datetime import date
from functools import cache
from pathlib import Path

import polars as pl
import psycopg
import pyarrow.parquet as pq
from sqlalchemy import text

from factor_investor.db import get_engine, get_session

logger = logging.getLogger(__name__)

PANEL_PATH = Path("data/cache/prices/total_returns.parquet")
SOURCE_KEY = "factor_investor.source"

PRICE_SCHEMA = {"instrument_id": pl.Int32, "price": pl.Float64}


def _source_fingerprint() -> dict[str, str]:
    with get_session() as session:
        rows, newest = session.execute(
            text("SELECT count(*), max(created_at) FROM total_returns")
        ).one()
    return {"rows": str(rows), "newest": str(newest)}


def build_price_panel(path: Path = PANEL_PATH) -> Path:
    """Export total_returns to Parquet (instrument_id, date, total_return_index)."""
    fingerprint = _source_fingerprint()
    path.parent.mkdir(parents=True, exist_ok=True)
    csv_path = path.with_suffix(".csv")

    logger.info(f"Exporting {fingerprint['rows']} total return rows to {path}")
    raw = get_engine().raw_connection()
    try:
        conn = raw.driver_connection
        assert isinstance(conn, psycopg.Connection)
        with (
            conn.cursor() as cur,
            csv_path.open("wb") as f,
            cur.copy(
                "COPY (SELECT instrument_id, date, total_return_index FROM total_returns) "
                "TO STDOUT (FORMAT csv)"
            ) as copy,
        ):
            for chunk in copy:
                f.write(chunk)
    finally:
        raw.close()

    panel = pl.scan_csv(
        csv_path,
        has_header=False,
        new_columns=["instrument_id", "date", "price"],
        schema_overrides={"instrument_id": pl.Int32, "date": pl.Date, "price": pl.Float64},
    ).sort(["date", "instrument_id"])
    table = panel.collect().to_arrow()
    table = table.replace_schema_metadata({SOURCE_KEY: json.dumps(fingerprint)})

    pq.write_table(table, path)
    csv_path.unlink()
    logger.info(f"Price panel written: {table.num_rows} rows")
    return path


def _is_current(path: Path) -> bool:
    if not path.exists():
        return False
    metadata = pq.read_schema(path).metadata or {}
    stored = metadata.get(SOURCE_KEY.encode())
    return stored is not None and json.loads(stored) == _source_fingerprint()


@dataclass(frozen=True)
class PricePanel:
    """Total return index per instrument and trading day, held in memory."""

    trading_days: list[date]
    _by_day: dict[date, pl.DataFrame]

    @classmethod
    def from_frame(cls, prices: pl.DataFrame) -> "PricePanel":
        """Build from a frame with columns [instrument_id, date, price].

        Non-positive prices (a total return index that rounded to zero) are
        not tradable and are dropped; their days stay in the calendar.
        """
        prices = prices.select(
            pl.col("instrument_id").cast(pl.Int32),
            pl.col("date"),
            pl.col("price").cast(pl.Float64),
        )
        trading_days = sorted(prices["date"].unique().to_list())
        by_day = {
            key[0]: frame.drop("date")
            for key, frame in prices.filter(pl.col("price") > 0)
            .partition_by("date", as_dict=True)
            .items()
        }
        return cls(trading_days=trading_days, _by_day=by_day)

    def trading_days_between(self, from_date: date, to_date: date) -> list[date]:
        return [d for d in self.trading_days if from_date <= d <= to_date]

    def prices_on(self, as_of_date: date) -> pl.DataFrame:
        """[instrument_id, price] for instruments that traded on as_of_date."""
        return self._by_day.get(as_of_date, pl.DataFrame(schema=PRICE_SCHEMA))


@cache
def load_price_panel(path: Path = PANEL_PATH) -> PricePanel:
    """Load the panel, rebuilding the Parquet file if the database has changed.

    Cached per process: the check runs once, then every backtest in the
    process shares the same panel.
    """
    if not _is_current(path):
        build_price_panel(path)
    logger.info(f"Loading price panel from {path}")
    return PricePanel.from_frame(pl.read_parquet(path))
