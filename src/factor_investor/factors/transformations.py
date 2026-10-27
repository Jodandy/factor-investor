"""Factor transformations.

Transformations convert base metrics over TIME dimension:
- level: Latest value (no transformation)
- mean: N-year average
- cagr: N-year compound annual growth rate
- median: N-year median
- trend: Linear regression slope
- stability_cv: Coefficient of variation (std/mean)

All transformations work on time series data and return transformed values.
"""

import logging
from datetime import date, timedelta

import numpy as np
import polars as pl
from scipy import stats

logger = logging.getLogger(__name__)


# Base metrics are sampled monthly, so the first point in a window can be up to
# about a month after the window start.
WINDOW_START_TOLERANCE_DAYS = 45


def _covers_window(window_data: pl.DataFrame, window_start: date) -> bool:
    """True if the data reaches back to (about) the start of the window.

    Counting data points is not enough: with monthly samples, a 5-year window
    would otherwise accept 5 months of history.
    """
    if len(window_data) == 0:
        return False
    earliest = window_data["date"].min()
    return earliest <= window_start + timedelta(days=WINDOW_START_TOLERANCE_DAYS)


def transform_level(base_df: pl.DataFrame) -> pl.DataFrame:
    """No-op: return latest value as-is.

    This is used when you want the current/latest value without any
    time-based transformation.

    Args:
        base_df: DataFrame with columns [instrument_id, date, value]

    Returns:
        Same DataFrame (no transformation)

    Example:
        >>> df = pl.DataFrame({
        ...     'instrument_id': [1, 1, 1],
        ...     'date': [date(2022,1,1), date(2023,1,1), date(2024,1,1)],
        ...     'value': [10.0, 12.0, 15.0]
        ... })
        >>> transform_level(df)  # Returns same df
    """
    return base_df


def transform_mean(base_df: pl.DataFrame, window_years: int) -> pl.DataFrame:
    """Calculate N-year mean for each instrument.

    For each instrument at date D:
    1. Get all values from [D - N years, D]
    2. Calculate mean
    3. Return value

    Args:
        base_df: DataFrame with columns [instrument_id, date, value]
        window_years: Window length in years (e.g., 3, 5, 7, 10)

    Returns:
        DataFrame with mean values (same schema as input)

    Example:
        >>> # instrument 1 has values: 10, 12, 15 over 3 years
        >>> # mean = (10 + 12 + 15) / 3 = 12.33
        >>> transform_mean(df, window_years=3)
    """
    if len(base_df) == 0:
        return pl.DataFrame(
            schema={
                "instrument_id": pl.Int32,
                "date": pl.Date,
                "value": pl.Float64,
            }
        )

    result = []

    for ins_id in base_df["instrument_id"].unique():
        ins_data = base_df.filter(pl.col("instrument_id") == ins_id).sort("date")

        for row in ins_data.iter_rows(named=True):
            curr_date = row["date"]
            window_start = curr_date - timedelta(days=window_years * 365)

            # Get window data
            window_data = ins_data.filter(
                (pl.col("date") >= window_start) & (pl.col("date") <= curr_date)
            )

            # Require at least N years of data (at least N data points)
            if _covers_window(window_data, window_start):
                mean_value = window_data["value"].mean()
                result.append(
                    {"instrument_id": ins_id, "date": curr_date, "value": mean_value}
                )

    if len(result) == 0:
        return pl.DataFrame(
            schema={
                "instrument_id": pl.Int32,
                "date": pl.Date,
                "value": pl.Float64,
            }
        )

    return pl.DataFrame(result)


def transform_min(base_df: pl.DataFrame, window_years: int) -> pl.DataFrame:
    """Calculate N-year minimum for each instrument.

    This is a CONSERVATIVE measure - selects worst year in the window.
    Useful for quality screening: "what's the WORST this company performed?"

    Args:
        base_df: DataFrame with columns [instrument_id, date, value]
        window_years: Window length in years

    Returns:
        DataFrame with minimum values

    Example:
        >>> # ROIC over 5 years: -5%, 3%, 8%, 12%, 10%
        >>> # Min = -5% (worst year)
        >>> # Good for conservative screening
    """
    if len(base_df) == 0:
        return pl.DataFrame(
            schema={
                "instrument_id": pl.Int32,
                "date": pl.Date,
                "value": pl.Float64,
            }
        )

    result = []

    for ins_id in base_df["instrument_id"].unique():
        ins_data = base_df.filter(pl.col("instrument_id") == ins_id).sort("date")

        for row in ins_data.iter_rows(named=True):
            curr_date = row["date"]
            window_start = curr_date - timedelta(days=window_years * 365)

            window_data = ins_data.filter(
                (pl.col("date") >= window_start) & (pl.col("date") <= curr_date)
            )

            if _covers_window(window_data, window_start):
                min_value = window_data["value"].min()
                result.append(
                    {"instrument_id": ins_id, "date": curr_date, "value": min_value}
                )

    if len(result) == 0:
        return pl.DataFrame(
            schema={
                "instrument_id": pl.Int32,
                "date": pl.Date,
                "value": pl.Float64,
            }
        )

    return pl.DataFrame(result)


def transform_max(base_df: pl.DataFrame, window_years: int) -> pl.DataFrame:
    """Calculate N-year maximum for each instrument.

    Useful for identifying peak performance.

    Args:
        base_df: DataFrame with columns [instrument_id, date, value]
        window_years: Window length in years

    Returns:
        DataFrame with maximum values
    """
    if len(base_df) == 0:
        return pl.DataFrame(
            schema={
                "instrument_id": pl.Int32,
                "date": pl.Date,
                "value": pl.Float64,
            }
        )

    result = []

    for ins_id in base_df["instrument_id"].unique():
        ins_data = base_df.filter(pl.col("instrument_id") == ins_id).sort("date")

        for row in ins_data.iter_rows(named=True):
            curr_date = row["date"]
            window_start = curr_date - timedelta(days=window_years * 365)

            window_data = ins_data.filter(
                (pl.col("date") >= window_start) & (pl.col("date") <= curr_date)
            )

            if _covers_window(window_data, window_start):
                max_value = window_data["value"].max()
                result.append(
                    {"instrument_id": ins_id, "date": curr_date, "value": max_value}
                )

    if len(result) == 0:
        return pl.DataFrame(
            schema={
                "instrument_id": pl.Int32,
                "date": pl.Date,
                "value": pl.Float64,
            }
        )

    return pl.DataFrame(result)


def transform_median(base_df: pl.DataFrame, window_years: int) -> pl.DataFrame:
    """Calculate N-year median for each instrument.

    Median is more robust to outliers than mean.

    Args:
        base_df: DataFrame with columns [instrument_id, date, value]
        window_years: Window length in years

    Returns:
        DataFrame with median values
    """
    if len(base_df) == 0:
        return pl.DataFrame(
            schema={
                "instrument_id": pl.Int32,
                "date": pl.Date,
                "value": pl.Float64,
            }
        )

    result = []

    for ins_id in base_df["instrument_id"].unique():
        ins_data = base_df.filter(pl.col("instrument_id") == ins_id).sort("date")

        for row in ins_data.iter_rows(named=True):
            curr_date = row["date"]
            window_start = curr_date - timedelta(days=window_years * 365)

            window_data = ins_data.filter(
                (pl.col("date") >= window_start) & (pl.col("date") <= curr_date)
            )

            if _covers_window(window_data, window_start):
                median_value = window_data["value"].median()
                result.append(
                    {"instrument_id": ins_id, "date": curr_date, "value": median_value}
                )

    if len(result) == 0:
        return pl.DataFrame(
            schema={
                "instrument_id": pl.Int32,
                "date": pl.Date,
                "value": pl.Float64,
            }
        )

    return pl.DataFrame(result)


def transform_cagr(base_df: pl.DataFrame, window_years: int) -> pl.DataFrame:
    """Calculate N-year CAGR (Compound Annual Growth Rate).

    CAGR = (end_value / start_value) ^ (1 / years) - 1

    This measures the annualized growth rate over the period.

    Args:
        base_df: DataFrame with columns [instrument_id, date, value]
        window_years: Window length in years

    Returns:
        DataFrame with CAGR values

    Example:
        >>> # Value goes from 100 to 133.1 over 3 years
        >>> # CAGR = (133.1/100)^(1/3) - 1 = 10%
    """
    if len(base_df) == 0:
        return pl.DataFrame(
            schema={
                "instrument_id": pl.Int32,
                "date": pl.Date,
                "value": pl.Float64,
            }
        )

    result = []

    for ins_id in base_df["instrument_id"].unique():
        ins_data = base_df.filter(pl.col("instrument_id") == ins_id).sort("date")

        for row in ins_data.iter_rows(named=True):
            curr_date = row["date"]
            window_start = curr_date - timedelta(days=window_years * 365)

            # Get start and end values
            start_data = ins_data.filter(
                (pl.col("date") >= window_start)
                & (pl.col("date") <= window_start + timedelta(days=90))  # 3-month window
            )
            end_value = row["value"]

            if len(start_data) > 0 and end_value and end_value > 0:
                start_value = start_data[0]["value"]
                if start_value and start_value > 0:
                    cagr = (end_value / start_value) ** (1 / window_years) - 1
                    result.append(
                        {"instrument_id": ins_id, "date": curr_date, "value": cagr}
                    )

    if len(result) == 0:
        return pl.DataFrame(
            schema={
                "instrument_id": pl.Int32,
                "date": pl.Date,
                "value": pl.Float64,
            }
        )

    return pl.DataFrame(result)


def transform_trend(base_df: pl.DataFrame, window_years: int) -> pl.DataFrame:
    """Calculate linear regression slope over N years.

    This measures the TREND (increasing/decreasing) over time.
    Positive slope = improving, negative = deteriorating.

    Args:
        base_df: DataFrame with columns [instrument_id, date, value]
        window_years: Window length in years

    Returns:
        DataFrame with slope values (annualized)

    Example:
        >>> # If ROE goes from 10% to 15% linearly over 5 years
        >>> # Slope ≈ 1% per year
    """
    if len(base_df) == 0:
        return pl.DataFrame(
            schema={
                "instrument_id": pl.Int32,
                "date": pl.Date,
                "value": pl.Float64,
            }
        )

    result = []

    for ins_id in base_df["instrument_id"].unique():
        ins_data = base_df.filter(pl.col("instrument_id") == ins_id).sort("date")

        for row in ins_data.iter_rows(named=True):
            curr_date = row["date"]
            window_start = curr_date - timedelta(days=window_years * 365)

            window_data = ins_data.filter(
                (pl.col("date") >= window_start) & (pl.col("date") <= curr_date)
            )

            # Need at least 3 points for trend
            if len(window_data) >= 3 and _covers_window(window_data, window_start):
                # Convert dates to years since start for regression
                dates_np = np.array(
                    [(d - window_start).days / 365.25 for d in window_data["date"]]
                )
                values_np = window_data["value"].to_numpy()

                # Linear regression
                slope, intercept, r_value, p_value, std_err = stats.linregress(
                    dates_np, values_np
                )

                # Slope is in units per year
                result.append(
                    {"instrument_id": ins_id, "date": curr_date, "value": slope}
                )

    if len(result) == 0:
        return pl.DataFrame(
            schema={
                "instrument_id": pl.Int32,
                "date": pl.Date,
                "value": pl.Float64,
            }
        )

    return pl.DataFrame(result)


def transform_stability_cv(base_df: pl.DataFrame, window_years: int) -> pl.DataFrame:
    """Calculate coefficient of variation (CV) over N years.

    CV = std / mean

    Lower CV = more stable/consistent.
    Higher CV = more volatile/erratic.

    This is useful for identifying companies with stable profitability.

    Args:
        base_df: DataFrame with columns [instrument_id, date, value]
        window_years: Window length in years

    Returns:
        DataFrame with CV values (lower = better stability)

    Example:
        >>> # Gross margin varies: 25%, 26%, 24%, 25%, 26%
        >>> # Mean = 25.2%, Std = 0.84%
        >>> # CV = 0.84 / 25.2 = 0.033 (very stable!)
    """
    if len(base_df) == 0:
        return pl.DataFrame(
            schema={
                "instrument_id": pl.Int32,
                "date": pl.Date,
                "value": pl.Float64,
            }
        )

    result = []

    for ins_id in base_df["instrument_id"].unique():
        ins_data = base_df.filter(pl.col("instrument_id") == ins_id).sort("date")

        for row in ins_data.iter_rows(named=True):
            curr_date = row["date"]
            window_start = curr_date - timedelta(days=window_years * 365)

            window_data = ins_data.filter(
                (pl.col("date") >= window_start) & (pl.col("date") <= curr_date)
            )

            if _covers_window(window_data, window_start):
                mean_val = window_data["value"].mean()
                std_val = window_data["value"].std()

                if mean_val and abs(mean_val) > 0.001:  # Avoid division by zero
                    cv = abs(std_val / mean_val)
                    result.append(
                        {"instrument_id": ins_id, "date": curr_date, "value": cv}
                    )

    if len(result) == 0:
        return pl.DataFrame(
            schema={
                "instrument_id": pl.Int32,
                "date": pl.Date,
                "value": pl.Float64,
            }
        )

    return pl.DataFrame(result)


def transform_percentile_history(
    base_df: pl.DataFrame, window_years: int
) -> pl.DataFrame:
    """Calculate current value as percentile vs own N-year history.

    Returns 0-100, where:
    - 100 = current value is highest in N years (strong)
    - 50 = current value is median
    - 0 = current value is lowest in N years (weak)

    Useful for identifying if a metric is at historical highs/lows.

    Args:
        base_df: DataFrame with columns [instrument_id, date, value]
        window_years: Window length for historical comparison

    Returns:
        DataFrame with percentile values (0-100)

    Example:
        >>> # ROIC over 5 years: 8%, 10%, 12%, 14%, 16%
        >>> # Current (16%) is highest = 100th percentile
    """
    if len(base_df) == 0:
        return pl.DataFrame(
            schema={
                "instrument_id": pl.Int32,
                "date": pl.Date,
                "value": pl.Float64,
            }
        )

    result = []

    for ins_id in base_df["instrument_id"].unique():
        ins_data = base_df.filter(pl.col("instrument_id") == ins_id).sort("date")

        for row in ins_data.iter_rows(named=True):
            curr_date = row["date"]
            curr_value = row["value"]
            window_start = curr_date - timedelta(days=window_years * 365)

            window_data = ins_data.filter(
                (pl.col("date") >= window_start) & (pl.col("date") <= curr_date)
            )

            if _covers_window(window_data, window_start) and curr_value is not None:
                # Calculate percentile rank
                values_np = window_data["value"].to_numpy()
                percentile = (
                    stats.percentileofscore(values_np, curr_value, kind="rank")
                )

                result.append(
                    {"instrument_id": ins_id, "date": curr_date, "value": percentile}
                )

    if len(result) == 0:
        return pl.DataFrame(
            schema={
                "instrument_id": pl.Int32,
                "date": pl.Date,
                "value": pl.Float64,
            }
        )

    return pl.DataFrame(result)
