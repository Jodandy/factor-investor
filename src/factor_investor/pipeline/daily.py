"""Daily prices for the daily clock (timing signals, exits).

A DailyPrices matrix holds one area's total return index per trading day
(the same filtered panel the engine trades on, converted to the area's
currency for regions). A DailyView binds it to a date: windows end on that
date, so a component never sees a later price.
"""

from bisect import bisect_right
from dataclasses import dataclass
from datetime import date
from functools import cache

import numpy as np
import polars as pl


@dataclass(frozen=True)
class DailyPrices:
    dates: list[date]
    index: dict[int, int]  # instrument_id -> column
    matrix: np.ndarray  # (days, instruments), NaN where no price

    @classmethod
    def from_frame(cls, prices: pl.DataFrame) -> "DailyPrices":
        """From [instrument_id, date, price]."""
        wide = prices.pivot(on="instrument_id", index="date", values="price").sort("date")
        columns = [c for c in wide.columns if c != "date"]
        return cls(
            dates=wide["date"].to_list(),
            index={int(c): i for i, c in enumerate(columns)},
            matrix=wide.select(columns).to_numpy().astype(np.float64)
            if columns
            else np.empty((len(wide), 0)),
        )

    def window(self, as_of: date, instruments: list[int], days: int) -> np.ndarray:
        """(days, len(instruments)): the last `days` rows dated on or before
        as_of; NaN for missing prices, unknown instruments and days before
        the data starts."""
        end = bisect_right(self.dates, as_of)
        start = max(0, end - days)
        out = np.full((days, len(instruments)), np.nan)
        rows = self.matrix[start:end]
        for j, instrument in enumerate(instruments):
            column = self.index.get(instrument)
            if column is not None:
                out[days - len(rows) :, j] = rows[:, column]
        return out


@dataclass(frozen=True)
class DailyView:
    """Daily prices as known on as_of."""

    daily: DailyPrices
    as_of: date

    def prices(self, instruments: list[int], days: int) -> np.ndarray:
        return self.daily.window(self.as_of, instruments, days)


@cache
def daily_prices(area_code: str) -> DailyPrices:
    """The area's domestic instruments from the engine's price panel (cached per process)."""
    from factor_investor.backtest.prices import (
        PANEL_PATH,
        _currency_frames,
        _is_current,
        build_price_panel,
        confirm_extreme_moves,
        convert_currency,
    )
    from factor_investor.benchmarks.run import AREAS
    from factor_investor.benchmarks.universe import Region, _instrument_markets

    area = AREAS[area_code]
    markets = area.markets if isinstance(area, Region) else (area,)
    domestic = pl.lit(False)
    for m in markets:
        domestic = domestic | (
            (pl.col("country_id") == m.country_id)
            & (pl.col("currency") == m.currency)
            & (pl.col("isin_country") == m.code)
        )
    ids = _instrument_markets().filter(domestic)["instrument_id"]
    if not _is_current(PANEL_PATH):
        build_price_panel(PANEL_PATH)
    frame = (
        pl.scan_parquet(PANEL_PATH)
        .filter(pl.col("instrument_id").is_in(ids.implode()) & (pl.col("price") > 0))
        .collect()
    )
    if isinstance(area, Region):
        frame = convert_currency(frame, *_currency_frames(), base=area.currency)
    return DailyPrices.from_frame(
        confirm_extreme_moves(frame).select("instrument_id", "date", "price")
    )
