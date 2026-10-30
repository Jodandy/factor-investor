"""Valuation math shared by the relative- and absolute-valuation components
(H11, after the ValBands / Buffett-proxy script). Components using it list
this file in `extra_sources`, so it is part of their source hash.

Relative: a multiple's upside to the median (fair value mid) and the 75th
percentile (upper band) of its own history: fair value = historical multiple x
today's metric, so upside = historical multiple / today's multiple - 1.
Non-positive multiples (losses, negative equity) are not valid.

Absolute: owner earnings grow from `growth` in year 1 linearly to
`terminal_growth` in year `horizon`, then are sold at `exit_multiple`; the
value is the discounted sum. The implied return is the discount rate that
makes the value equal the price (bisection on [-25%, 100%], clamped there).
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

LOW_RATE, HIGH_RATE = -0.25, 1.0


def multiple_upside(current: float, history: np.ndarray) -> tuple[float | None, float | None]:
    """(upside to the median, upside to the 75th percentile) of the positive history."""
    valid = history[history > 0] if len(history) else history
    if current is None or not current > 0 or len(valid) == 0:
        return None, None
    return float(np.median(valid) / current - 1), float(np.percentile(valid, 75) / current - 1)


@dataclass(frozen=True)
class DcfParams:
    horizon: int = 10
    exit_multiple: float = 12.0
    terminal_growth: float = 0.03


def dcf_value(owner_earnings: float, growth: float, rate: float, params: DcfParams) -> float:
    n = params.horizon
    value, cash_flow = 0.0, owner_earnings
    for t in range(1, n + 1):
        g = growth + (params.terminal_growth - growth) * (t - 1) / (n - 1) if n > 1 else growth
        cash_flow *= 1 + g
        value += cash_flow / (1 + rate) ** t
    return value + cash_flow * params.exit_multiple / (1 + rate) ** n


def implied_return(owner_earnings: float, growth: float, price: float, params: DcfParams) -> float:
    """Annual return at this price; NaN without positive earnings or price."""
    if not owner_earnings > 0 or not price > 0:
        return math.nan
    if dcf_value(owner_earnings, growth, HIGH_RATE, params) > price:
        return HIGH_RATE
    if dcf_value(owner_earnings, growth, LOW_RATE, params) < price:
        return LOW_RATE
    low, high = LOW_RATE, HIGH_RATE
    for _ in range(60):
        mid = (low + high) / 2
        if dcf_value(owner_earnings, growth, mid, params) > price:
            low = mid
        else:
            high = mid
    return (low + high) / 2


# --- computed through a point-in-time view -----------------------------------

RELATIVE_METRICS = ("pe_ratio", "ps_ratio", "pb_ratio", "p_fcf", "ev_ebit")


def relative_upsides(
    view: Any,
    instruments: Any,
    metrics: Sequence[str],
    years: int,
    min_observations: int,
    min_metrics: int,
) -> Any:
    """[instrument_id, upside_mid, upside_high]: the mean over valid metrics of
    each multiple's upside to its own history (monthly snapshots in the
    `years` before the view's date, current excluded); null with fewer than
    `min_metrics` valid multiples."""
    import polars as pl

    ids = instruments.select(pl.col("instrument_id").cast(pl.Int32))
    per_metric = []
    for metric in metrics:
        history = (
            view.metric_history(metric, years)
            .filter((pl.col("date") < view.as_of) & (pl.col("value") > 0))
            .group_by("instrument_id")
            .agg(
                pl.col("value").median().alias("mid"),
                pl.col("value").quantile(0.75, interpolation="linear").alias("high"),
                pl.len().alias("n"),
            )
            .filter(pl.col("n") >= min_observations)
        )
        current = view.metric(metric).filter(pl.col("value") > 0).rename({"value": "current"})
        per_metric.append(
            ids.join(current, on="instrument_id")
            .join(history, on="instrument_id")
            .select(
                "instrument_id",
                (pl.col("mid") / pl.col("current") - 1).alias("upside_mid"),
                (pl.col("high") / pl.col("current") - 1).alias("upside_high"),
            )
        )
    stacked = pl.concat(per_metric) if per_metric else pl.DataFrame(schema=ids.schema)
    combined = (
        stacked.group_by("instrument_id")
        .agg(pl.col("upside_mid").mean(), pl.col("upside_high").mean(), pl.len().alias("n"))
        .filter(pl.col("n") >= min_metrics)
        .drop("n")
    )
    return ids.join(combined, on="instrument_id", how="left")


def owner_earnings_returns(
    view: Any,
    instruments: Any,
    years_avg: int,
    growth_cap: float,
    growth_fallback: float,
    params: DcfParams,
) -> Any:
    """[instrument_id, irr]: implied annual return at the view's price with
    owner earnings = mean EPS of the last `years_avg` fiscal years (net
    income; the script's default) and growth = min(cap, ROE x retention) from
    the latest fiscal year (retention = 1 - dividend / EPS), or
    `growth_fallback` when that cannot be computed. Null without positive
    owner earnings or a price."""
    import polars as pl

    ids = instruments.select(pl.col("instrument_id").cast(pl.Int32))
    eps = (
        view.annual("earnings_per_share", years_avg)
        .group_by("instrument_id")
        .agg(pl.col("value").mean().alias("oe"))
    )
    latest = {
        m: view.annual(m, 1).select("instrument_id", pl.col("value").alias(m))
        for m in ("earnings_per_share", "dividend", "roe")
    }
    frame = view.frame(ids, frozenset({"price"})).join(eps, on="instrument_id", how="left")
    for values in latest.values():
        frame = frame.join(values, on="instrument_id", how="left")
    out = []
    for row in frame.iter_rows(named=True):
        growth = growth_fallback
        e, d, roe = row["earnings_per_share"], row["dividend"], row["roe"]
        if e is not None and e > 0 and roe is not None:
            retention = min(1.0, max(0.0, 1 - (d or 0.0) / e))
            growth = min(growth_cap, max(0.0, roe * retention))
        oe, price = row["oe"], row["price"]
        irr = (
            implied_return(oe, growth, price, params)
            if oe is not None and price is not None
            else math.nan
        )
        out.append((row["instrument_id"], None if math.isnan(irr) else irr))
    return pl.DataFrame(out, schema={"instrument_id": pl.Int32, "irr": pl.Float64}, orient="row")
