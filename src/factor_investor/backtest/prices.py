"""In-memory price panel for the backtest engine.

The engine needs every instrument's total return index on every trading day.
Querying the database per day takes minutes per backtest, so the
`total_returns` table is exported once to Parquet and loaded into memory.

The Parquet file records the table's row count and newest `created_at` (and
the stock_prices row count, for volume). On load these are compared with the
database, and the file is rebuilt if they differ, so a backtest never reads
prices from before a rebuild.

Extreme one-day moves are withheld until confirmed (`confirm_extreme_moves`),
so one-day data errors are never traded or used to value a position.
"""

import json
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from functools import cache
from pathlib import Path

import numpy as np
import polars as pl
import psycopg
import pyarrow.parquet as pq
from numba import njit
from sqlalchemy import text

from factor_investor.db import get_engine, get_session

logger = logging.getLogger(__name__)

PANEL_PATH = Path("data/cache/prices/total_returns.parquet")
SOURCE_KEY = "factor_investor.source"

PRICE_SCHEMA = {"instrument_id": pl.Int32, "price": pl.Float64}

# price_filter_v2: a move beyond MOVE_BAND (up or down) from the last accepted
# price is withheld until the instrument has traded outside the band on
# CONFIRM_DAYS days, or has been quoted outside it MAX_WAIT_DAYS times. A
# confirmed rise beyond SPLIT_BAND is treated as a reverse split missing from
# the price adjustment and scaled away. (v1, never used in a logged run, had
# no split rule.)
PRICE_FILTER_ID = "price_filter_v2"
MOVE_BAND = 3.0
CONFIRM_DAYS = 5
MAX_WAIT_DAYS = 20
SPLIT_BAND = 10.0


@njit(cache=True)
def _filter_prices(
    instrument_ids: np.ndarray,
    prices: np.ndarray,
    traded: np.ndarray,
    band: float,
    confirm_days: int,
    max_wait_days: int,
    split_band: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Per row (sorted by instrument, date): is the price accepted, and the
    accepted price (rescaled after confirmed rises beyond split_band).

    Each decision uses only the instrument's own earlier prices.
    """
    accepted = np.zeros(len(prices), dtype=np.bool_)
    adjusted = prices.copy()
    reference = 0.0
    scale = 1.0
    traded_outside = 0
    quoted_outside = 0
    for i in range(len(prices)):
        if i == 0 or instrument_ids[i] != instrument_ids[i - 1]:
            accepted[i] = True
            reference = prices[i]
            scale = 1.0
            traded_outside = 0
            quoted_outside = 0
            continue
        price = prices[i] * scale
        ratio = price / reference
        if not 1.0 / band <= ratio <= band:
            quoted_outside += 1
            if traded[i]:
                traded_outside += 1
            if traded_outside < confirm_days and quoted_outside < max_wait_days:
                continue
            if ratio > split_band:
                scale *= reference / price
                price = reference
        accepted[i] = True
        adjusted[i] = price
        reference = price
        traded_outside = 0
        quoted_outside = 0
    return accepted, adjusted


def confirm_extreme_moves(
    prices: pl.DataFrame,
    band: float = MOVE_BAND,
    confirm_days: int = CONFIRM_DAYS,
    max_wait_days: int = MAX_WAIT_DAYS,
    split_band: float = SPLIT_BAND,
) -> pl.DataFrame:
    """Drop prices that moved beyond `band` from the last accepted price.

    A move is used once the instrument has traded (volume > 0) outside the
    band on `confirm_days` days, so a repeated quote without trades does not
    confirm a bad print. It is used after `max_wait_days` quotes outside the
    band in any case, so an illiquid stock that really crashed is not held at
    its old price. A spike that comes back inside the band is never used.

    A confirmed rise beyond `split_band` is a reverse split missing from the
    price adjustment (Atos 2025-04-30, x10,217): from then on the series is
    scaled so the move disappears and the position keeps its value. Falls are
    never rescaled, so data errors can only lower returns.

    The decision for a day depends only on prices up to that day, so no later
    data leaks into the backtest. Withheld days look like days without trading
    to the engine. Without a `volume` column every price counts as a trade.
    """
    prices = prices.sort(["instrument_id", "date"])
    traded = (
        (prices["volume"].fill_null(0) > 0).to_numpy()
        if "volume" in prices.columns
        else np.ones(prices.height, dtype=np.bool_)
    )
    keep, adjusted = _filter_prices(
        prices["instrument_id"].to_numpy(),
        prices["price"].to_numpy(),
        traded,
        band,
        confirm_days,
        max_wait_days,
        split_band,
    )
    return prices.with_columns(pl.Series("price", adjusted)).filter(pl.Series(keep))


FX_MAX_AGE_DAYS = 7


def convert_currency(
    prices: pl.DataFrame,
    currencies: pl.DataFrame,
    usd_rates: pl.DataFrame,
    base: str,
    max_age_days: int = FX_MAX_AGE_DAYS,
) -> pl.DataFrame:
    """Prices in each instrument's own currency converted to `base`.

    Args:
        prices: [instrument_id, date, price, ...]; other columns are kept
        currencies: [instrument_id, currency]
        usd_rates: [currency, date, per_usd], units of currency per USD
            (USD itself needs no rows)
        base: Target currency

    Each price uses the last rates quoted on or before its date, at most
    max_age_days old, so no later quote is used. Prices without such a rate
    (or with an unknown currency) are dropped. A total return index converted
    this way is the total return in `base`.
    """
    tolerance = timedelta(days=max_age_days)
    rates = usd_rates.select("currency", "date", "per_usd").sort("date")
    base_rates = rates.filter(pl.col("currency") == base).select(
        "date", pl.col("per_usd").alias("base_per_usd")
    )
    is_usd = pl.col("currency") == "USD"
    return (
        prices.join(currencies, on="instrument_id")
        .sort("date")
        .join_asof(rates, on="date", by="currency", strategy="backward", tolerance=tolerance)
        .join_asof(base_rates, on="date", strategy="backward", tolerance=tolerance)
        .with_columns(
            pl.when(is_usd).then(1.0).otherwise(pl.col("per_usd")).alias("per_usd"),
            (pl.lit(1.0) if base == "USD" else pl.col("base_per_usd")).alias("base_per_usd"),
        )
        .drop_nulls(["per_usd", "base_per_usd"])
        # factor first, so a price already in `base` is multiplied by exactly 1.0
        .with_columns(pl.col("price") * (pl.col("base_per_usd") / pl.col("per_usd")))
        .select(prices.columns)
    )


def _source_fingerprint() -> dict[str, str]:
    with get_session() as session:
        rows, newest = session.execute(
            text("SELECT count(*), max(created_at) FROM total_returns")
        ).one()
        price_rows = session.execute(text("SELECT count(*) FROM stock_prices")).scalar_one()
    return {"rows": str(rows), "newest": str(newest), "price_rows": str(price_rows)}


def build_price_panel(path: Path = PANEL_PATH) -> Path:
    """Export total_returns to Parquet (instrument_id, date, price, volume).

    Volume comes from stock_prices and is used only to confirm extreme moves.
    """
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
                "COPY (SELECT t.instrument_id, t.date, t.total_return_index, s.volume "
                "FROM total_returns t LEFT JOIN stock_prices s "
                "ON s.ins_id = t.instrument_id AND s.date = t.date) TO STDOUT (FORMAT csv)"
            ) as copy,
        ):
            for chunk in copy:
                f.write(chunk)
    finally:
        raw.close()

    panel = pl.scan_csv(
        csv_path,
        has_header=False,
        new_columns=["instrument_id", "date", "price", "volume"],
        schema_overrides={
            "instrument_id": pl.Int32,
            "date": pl.Date,
            "price": pl.Float64,
            "volume": pl.Int64,
        },
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
        """Build from a frame with columns [instrument_id, date, price] and
        optionally volume.

        Non-positive prices (a total return index that rounded to zero) are
        not tradable and are dropped, and extreme moves are withheld until
        confirmed (`confirm_extreme_moves`). Dropped days stay in the calendar.
        """
        prices = prices.select(
            pl.col("instrument_id").cast(pl.Int32),
            pl.col("date"),
            pl.col("price").cast(pl.Float64),
            *([pl.col("volume")] if "volume" in prices.columns else []),
        )
        trading_days = sorted(prices["date"].unique().to_list())
        by_day = {
            key[0]: frame.select("instrument_id", "price")
            for key, frame in confirm_extreme_moves(prices.filter(pl.col("price") > 0))
            .partition_by("date", as_dict=True)
            .items()
        }
        return cls(trading_days=trading_days, _by_day=by_day)

    def trading_days_between(self, from_date: date, to_date: date) -> list[date]:
        return [d for d in self.trading_days if from_date <= d <= to_date]

    def prices_on(self, as_of_date: date) -> pl.DataFrame:
        """[instrument_id, price] for instruments that traded on as_of_date."""
        return self._by_day.get(as_of_date, pl.DataFrame(schema=PRICE_SCHEMA))


def _currency_frames() -> tuple[pl.DataFrame, pl.DataFrame]:
    """Each instrument's price currency, and the USD rate history."""
    from factor_investor.universe.fx import usd_rate_history

    with get_session() as session:
        currencies = session.execute(
            text("SELECT ins_id, stock_price_currency FROM instruments")
        ).all()
    return (
        pl.DataFrame(
            currencies, schema={"instrument_id": pl.Int32, "currency": pl.Utf8}, orient="row"
        ),
        pl.DataFrame(
            usd_rate_history(),
            schema={"currency": pl.Utf8, "date": pl.Date, "per_usd": pl.Float64},
            orient="row",
        ),
    )


@cache
def load_price_panel(path: Path = PANEL_PATH, currency: str | None = None) -> PricePanel:
    """Load the panel, rebuilding the Parquet file if the database has changed.

    Prices are in each instrument's own currency, or converted to `currency`
    (`convert_currency`) for portfolios that span currencies.

    Cached per process: the check runs once, then every backtest in the
    process shares the same panel.
    """
    if not _is_current(path):
        build_price_panel(path)
    logger.info(f"Loading price panel from {path}")
    frame = pl.read_parquet(path)
    if currency is not None:
        frame = convert_currency(frame, *_currency_frames(), base=currency)
    return PricePanel.from_frame(frame)
