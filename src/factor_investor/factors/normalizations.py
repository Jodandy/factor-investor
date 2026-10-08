"""Factor normalizations.

Normalizations convert factors in CROSS-SECTIONAL dimension (across universe):
- raw: No normalization (original values)
- percentile: Percentile rank in universe (0-100)
- zscore: Z-score normalization with optional winsorization
- rank: Simple ranking (1 to N)

All normalizations work on a single date's cross-section of instruments.
"""

import logging

import numpy as np
import polars as pl

logger = logging.getLogger(__name__)


def normalize_raw(df: pl.DataFrame) -> pl.DataFrame:
    """No-op: return as-is (no normalization).

    Use this when you want the actual values (e.g., for filtering/screening).

    Args:
        df: DataFrame with columns [instrument_id, date, value]

    Returns:
        Same DataFrame

    Example:
        >>> # Use roic_mean_5y_raw for filtering: ROIC > 15%
        >>> normalize_raw(df)  # Returns same df
    """
    return df


def normalize_percentile(df: pl.DataFrame) -> pl.DataFrame:
    """Calculate percentile rank (0-100) in universe.

    For each date, rank all instruments by value and convert to percentile.

    Returns:
        - 100 = highest value in universe on this date
        - 50 = median
        - 0 = lowest value

    This is the MOST COMMON normalization for factor combining.

    Args:
        df: DataFrame with columns [instrument_id, date, value]

    Returns:
        DataFrame with percentile values (0-100)

    Example:
        >>> # 100 instruments, instrument X has 80th highest ROIC
        >>> # percentile = 80
    """
    if len(df) == 0:
        return pl.DataFrame(
            schema={
                "instrument_id": pl.Int32,
                "date": pl.Date,
                "value": pl.Float64,
            }
        )

    result = []

    for date_val in df["date"].unique():
        date_data = df.filter(pl.col("date") == date_val).sort("value")

        if len(date_data) == 0:
            continue

        # Rank and convert to percentile
        # Use method='average' to handle ties
        date_data = date_data.with_columns(
            (pl.col("value").rank(method="average") / len(date_data) * 100).alias(
                "percentile"
            )
        )

        result.append(
            date_data.select(
                ["instrument_id", "date", pl.col("percentile").alias("value")]
            )
        )

    if len(result) == 0:
        return pl.DataFrame(
            schema={
                "instrument_id": pl.Int32,
                "date": pl.Date,
                "value": pl.Float64,
            }
        )

    return pl.concat(result)


def normalize_zscore(df: pl.DataFrame, winsorize: bool = True) -> pl.DataFrame:
    """Calculate z-score with optional winsorization.

    z = (x - mean) / std

    Winsorization clips extreme values at ±3σ to reduce impact of outliers.

    Returns:
        - 0 = mean (average in universe)
        - +1 = one std above mean
        - -1 = one std below mean
        - Clipped at ±3 if winsorize=True

    Args:
        df: DataFrame with columns [instrument_id, date, value]
        winsorize: If True, clip at ±3σ (recommended)

    Returns:
        DataFrame with z-score values

    Example:
        >>> # Mean ROE = 15%, Std = 5%
        >>> # Instrument with ROE = 20%
        >>> # z-score = (20 - 15) / 5 = 1.0
    """
    if len(df) == 0:
        return pl.DataFrame(
            schema={
                "instrument_id": pl.Int32,
                "date": pl.Date,
                "value": pl.Float64,
            }
        )

    result = []

    for date_val in df["date"].unique():
        date_data = df.filter(pl.col("date") == date_val)

        if len(date_data) == 0:
            continue

        mean = date_data["value"].mean()
        std = date_data["value"].std()

        if std and std > 0.001:  # Avoid division by zero
            date_data = date_data.with_columns(
                ((pl.col("value") - mean) / std).alias("zscore")
            )

            if winsorize:
                # Clip at ±3 sigma
                date_data = date_data.with_columns(
                    pl.col("zscore").clip(-3, 3).alias("zscore")
                )

            result.append(
                date_data.select(
                    ["instrument_id", "date", pl.col("zscore").alias("value")]
                )
            )

    if len(result) == 0:
        return pl.DataFrame(
            schema={
                "instrument_id": pl.Int32,
                "date": pl.Date,
                "value": pl.Float64,
            }
        )

    return pl.concat(result)


def normalize_rank(df: pl.DataFrame) -> pl.DataFrame:
    """Calculate simple rank (1 to N) in universe.

    For each date, rank all instruments by value.

    Returns:
        - N = highest value (rank 1st if ascending=False)
        - 1 = lowest value

    Note: Unlike percentile, this is not scaled to 0-100.
    Percentile is generally preferred for factor combining.

    Args:
        df: DataFrame with columns [instrument_id, date, value]

    Returns:
        DataFrame with rank values (1 to N)

    Example:
        >>> # 100 instruments, instrument X has 5th highest ROIC
        >>> # rank = 5
    """
    if len(df) == 0:
        return pl.DataFrame(
            schema={
                "instrument_id": pl.Int32,
                "date": pl.Date,
                "value": pl.Float64,
            }
        )

    result = []

    for date_val in df["date"].unique():
        date_data = df.filter(pl.col("date") == date_val).sort("value")

        if len(date_data) == 0:
            continue

        # Simple ranking (1 to N)
        date_data = date_data.with_columns(
            pl.col("value").rank(method="average").alias("rank_value")
        )

        result.append(
            date_data.select(
                ["instrument_id", "date", pl.col("rank_value").alias("value")]
            )
        )

    if len(result) == 0:
        return pl.DataFrame(
            schema={
                "instrument_id": pl.Int32,
                "date": pl.Date,
                "value": pl.Float64,
            }
        )

    return pl.concat(result)


def normalize_quantile(df: pl.DataFrame, n_quantiles: int = 5) -> pl.DataFrame:
    """Assign instruments to quantiles (1 to N).

    Divides universe into N equal-sized buckets.

    Args:
        df: DataFrame with columns [instrument_id, date, value]
        n_quantiles: Number of quantiles (e.g., 5 for quintiles, 10 for deciles)

    Returns:
        DataFrame with quantile assignments (1 to n_quantiles)

    Example:
        >>> # With 5 quantiles and 100 instruments:
        >>> # Top 20 get quantile=5, next 20 get quantile=4, etc.
        >>> normalize_quantile(df, n_quantiles=5)
    """
    if len(df) == 0:
        return pl.DataFrame(
            schema={
                "instrument_id": pl.Int32,
                "date": pl.Date,
                "value": pl.Float64,
            }
        )

    result = []

    for date_val in df["date"].unique():
        date_data = df.filter(pl.col("date") == date_val).sort("value")

        if len(date_data) == 0:
            continue

        # Calculate quantile breakpoints
        quantiles = np.linspace(0, 100, n_quantiles + 1)
        breakpoints = [date_data["value"].quantile(q / 100) for q in quantiles]

        # Assign each value to a quantile
        def assign_quantile(val):
            for i in range(len(breakpoints) - 1):
                if breakpoints[i] <= val <= breakpoints[i + 1]:
                    return i + 1
            return n_quantiles

        date_data = date_data.with_columns(
            pl.col("value").map_elements(assign_quantile, return_dtype=pl.Float64).alias("quantile")
        )

        result.append(
            date_data.select(
                ["instrument_id", "date", pl.col("quantile").alias("value")]
            )
        )

    if len(result) == 0:
        return pl.DataFrame(
            schema={
                "instrument_id": pl.Int32,
                "date": pl.Date,
                "value": pl.Float64,
            }
        )

    return pl.concat(result)
