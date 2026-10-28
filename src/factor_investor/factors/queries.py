"""Factor queries with lazy calculation and caching.

This module provides the main interface for getting factor values:
- get_factor(): Get single factor (with lazy calculation + cache)
- get_factors_batch(): Get multiple factors efficiently

Factor ID Format:
-----------------
{base_metric}_{transformation}_{window}y_{normalization}

Examples:
- roic_mean_5y_pct          -> ROIC, 5-year mean, percentile normalized
- pe_ratio_level_raw         -> P/E ratio, latest value, no normalization
- return_12m_raw             -> 12-month return, no transformation, no normalization
- gross_margin_stability_cv_5y_zscore -> Gross margin, 5y CV, z-score normalized

Components:
- base_metric: Name from fundamental_metrics or price_metrics table
- transformation: level, mean, median, cagr, trend, stability_cv, percentile_history
- window: For windowed transformations (3y, 5y, 7y, 10y)
- normalization: raw, pct, zscore, rank, quantile
"""

import logging
import re
from datetime import date
from pathlib import Path

import polars as pl
from sqlalchemy import select

from factor_investor.db import get_session
from factor_investor.factors import normalizations, transformations
from factor_investor.factors.models import FundamentalMetric, PriceMetric

logger = logging.getLogger(__name__)

# Cache directory for transformed/normalized factors. Bump the version when
# factor logic changes so stale values are never read. The cache must also be
# cleared after rebuilding base data (clear_cache()).
CACHE_VERSION = 5
CACHE_DIR = Path(f"data/factors/cache/v{CACHE_VERSION}")
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def get_factor(
    factor_id: str,
    as_of_date: date,
    instrument_ids: list[int] | None = None,
    use_cache: bool = True,
) -> pl.DataFrame:
    """Get factor values with lazy calculation + cache.

    This is the MAIN function for retrieving factors. It:
    1. Checks cache first (fast path)
    2. If cache miss: loads base metric, applies transformation + normalization
    3. Saves to cache for next time
    4. Returns result

    Args:
        factor_id: Factor ID (e.g., "roic_mean_5y_pct")
        as_of_date: Date to get factor values for
        instrument_ids: Optional filter applied to the result. Values are always
            computed (and normalized) over the full cross-section.
        use_cache: If False, always recalculate (for testing)

    Returns:
        DataFrame with columns [instrument_id, date, value]

    Example:
        >>> df = get_factor("roic_mean_5y_pct", date(2024, 1, 31))
        >>> print(df)
        ┌─────────────────┬────────────┬───────┐
        │ instrument_id   │ date       │ value │
        ├─────────────────┼────────────┼───────┤
        │ 2               │ 2024-01-31 │ 75.3  │  (75th percentile)
        │ 3               │ 2024-01-31 │ 92.1  │  (92nd percentile)
        └─────────────────┴────────────┴───────┘
    """
    # Check cache
    cache_path = CACHE_DIR / factor_id / f"date={as_of_date}.parquet"

    if use_cache and cache_path.exists():
        logger.debug(f"Cache hit: {factor_id} @ {as_of_date}")
        df = pl.read_parquet(cache_path)

        if instrument_ids:
            df = df.filter(pl.col("instrument_id").is_in(instrument_ids))

        return df

    logger.debug(f"Cache miss: {factor_id} @ {as_of_date}, calculating...")

    # Parse factor_id
    parsed = _parse_factor_id(factor_id)
    base_metric = parsed["base_metric"]
    transformation = parsed["transformation"]
    window_years = parsed["window_years"]
    normalization = parsed["normalization"]

    logger.debug(
        f"  Parsed: base={base_metric}, trans={transformation}, "
        f"window={window_years}, norm={normalization}"
    )

    # Load base metric for all instruments: normalization is cross-sectional,
    # and the cache must hold the full cross-section
    base_df = _get_base_metric(base_metric, as_of_date)

    if len(base_df) == 0:
        logger.warning(f"No base metric data for {base_metric} @ {as_of_date}")
        return pl.DataFrame(
            schema={
                "instrument_id": pl.Int32,
                "date": pl.Date,
                "value": pl.Float64,
            }
        )

    logger.debug(f"  Loaded {len(base_df)} rows of base metric")

    # Apply transformation
    transformed_df = _apply_transformation(base_df, transformation, window_years)

    if len(transformed_df) == 0:
        logger.warning(
            f"No data after transformation {transformation} (window={window_years}y)"
        )
        return pl.DataFrame(
            schema={
                "instrument_id": pl.Int32,
                "date": pl.Date,
                "value": pl.Float64,
            }
        )

    logger.debug(f"  After transformation: {len(transformed_df)} rows")

    # Filter to only as_of_date (transformations return all historical dates)
    transformed_df = transformed_df.filter(pl.col("date") == as_of_date)

    if len(transformed_df) == 0:
        logger.warning(f"No data for {as_of_date} after filtering transformed data")
        return pl.DataFrame(
            schema={
                "instrument_id": pl.Int32,
                "date": pl.Date,
                "value": pl.Float64,
            }
        )

    logger.debug(f"  After filtering to {as_of_date}: {len(transformed_df)} rows")

    # Normalize only over the eligible universe (percentile "in the universe")
    eligible = _eligible_instruments(as_of_date)
    if eligible is not None:
        transformed_df = transformed_df.filter(pl.col("instrument_id").is_in(list(eligible)))

    # Apply normalization
    result_df = _apply_normalization(transformed_df, normalization)

    logger.debug(f"  After normalization: {len(result_df)} rows")

    # Save to cache
    if use_cache:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        result_df.write_parquet(cache_path)
        logger.debug(f"  Cached to {cache_path}")

    if instrument_ids:
        result_df = result_df.filter(pl.col("instrument_id").is_in(instrument_ids))

    return result_df


def get_factors_batch(
    factor_ids: list[str],
    as_of_date: date,
    instrument_ids: list[int] | None = None,
) -> dict[str, pl.DataFrame]:
    """Get multiple factors efficiently.

    This is useful when you need many factors for backtesting.
    It can optimize by:
    - Reusing base metrics across factors
    - Parallel calculation (future optimization)

    Args:
        factor_ids: List of factor IDs
        as_of_date: Date to get factor values for
        instrument_ids: Optional filter

    Returns:
        Dict mapping factor_id -> DataFrame

    Example:
        >>> factors = get_factors_batch(
        ...     ["roic_mean_5y_pct", "pe_ratio_level_raw"],
        ...     date(2024, 1, 31)
        ... )
        >>> roic_df = factors["roic_mean_5y_pct"]
        >>> pe_df = factors["pe_ratio_level_raw"]
    """
    result = {}

    for factor_id in factor_ids:
        result[factor_id] = get_factor(factor_id, as_of_date, instrument_ids)

    return result


def clear_cache(factor_id: str | None = None, as_of_date: date | None = None) -> int:
    """Clear factor cache.

    Args:
        factor_id: If provided, only clear this factor. Otherwise clear all.
        as_of_date: If provided, only clear this date. Otherwise clear all dates.

    Returns:
        Number of files deleted

    Example:
        >>> # Clear all cache
        >>> clear_cache()

        >>> # Clear specific factor
        >>> clear_cache(factor_id="roic_mean_5y_pct")

        >>> # Clear specific date for all factors
        >>> clear_cache(as_of_date=date(2024, 1, 31))
    """
    deleted = 0

    if factor_id and as_of_date:
        # Clear specific factor + date
        cache_path = CACHE_DIR / factor_id / f"date={as_of_date}.parquet"
        if cache_path.exists():
            cache_path.unlink()
            deleted = 1
    elif factor_id:
        # Clear all dates for this factor
        factor_dir = CACHE_DIR / factor_id
        if factor_dir.exists():
            for file in factor_dir.glob("*.parquet"):
                file.unlink()
                deleted += 1
    elif as_of_date:
        # Clear this date for all factors
        for factor_dir in CACHE_DIR.iterdir():
            if factor_dir.is_dir():
                cache_path = factor_dir / f"date={as_of_date}.parquet"
                if cache_path.exists():
                    cache_path.unlink()
                    deleted += 1
    else:
        # Clear everything
        for factor_dir in CACHE_DIR.iterdir():
            if factor_dir.is_dir():
                for file in factor_dir.glob("*.parquet"):
                    file.unlink()
                    deleted += 1

    logger.info(f"Cleared {deleted} cache files")
    return deleted


# ============================================================================
# Internal helper functions
# ============================================================================


def _parse_factor_id(factor_id: str) -> dict:
    """Parse factor ID into components.

    Handles formats:
    - base_metric_transformation_Ny_normalization (e.g., roic_mean_5y_pct)
    - base_metric_transformation_normalization (e.g., pe_ratio_level_raw)
    - base_metric_normalization (e.g., return_12m_raw)

    Returns:
        Dict with keys: base_metric, transformation, window_years, normalization
    """
    parts = factor_id.split("_")

    # Try to find normalization (last part)
    # Valid normalizations: raw, pct, zscore, rank, quantile
    valid_norms = {"raw", "pct", "zscore", "rank", "quantile"}
    normalization = None

    if parts[-1] in valid_norms:
        normalization = parts[-1]
        remaining = parts[:-1]
    else:
        raise ValueError(
            f"Invalid factor_id '{factor_id}': must end with normalization "
            f"(raw, pct, zscore, rank, quantile)"
        )

    # Try to find window (format: Ny where N is number)
    window_years = None
    window_idx = None

    for i, part in enumerate(remaining):
        if re.match(r"^\d+y$", part):  # Matches "5y", "10y", etc.
            window_years = int(part[:-1])
            window_idx = i
            break

    if window_idx is not None:
        # Has window: base_metric_transformation_Ny
        transformation = remaining[window_idx - 1] if window_idx > 0 else "level"
        base_metric = "_".join(remaining[:window_idx - 1]) if window_idx > 1 else remaining[0]
    else:
        # No window: base_metric_transformation OR just base_metric
        if len(remaining) >= 2:
            # Assume last part is transformation
            transformation = remaining[-1]
            base_metric = "_".join(remaining[:-1])
        else:
            # Just base_metric (e.g., "return_12m_raw")
            transformation = "level"
            base_metric = "_".join(remaining)

    return {
        "base_metric": base_metric,
        "transformation": transformation,
        "window_years": window_years,
        "normalization": normalization,
    }


def _eligible_instruments(as_of_date: date) -> set[int] | None:
    """Instruments eligible in the universe on as_of_date.

    Returns None (no restriction, with a warning) if the universe has not
    been built for that date.
    """
    from factor_investor.universe.queries import get_universe

    universe = get_universe(as_of_date, is_eligible=True)
    if len(universe) == 0:
        logger.warning(f"No universe for {as_of_date}; normalizing over all instruments")
        return None
    return set(universe["instrument_id"].to_list())


def select_latest_ttm(pit_df: pl.DataFrame) -> pl.DataFrame:
    """Pick the latest trailing-twelve-month value per instrument.

    Only r12 and year rows are used: quarter rows hold 3-month figures, or
    6-month figures for semi-annual reporters (Börsdata stores H1/H2 in
    Q2/Q4), so they are not comparable. r12 wins ties with year.

    Args:
        pit_df: as_of() output with [instrument_id, period_type, period_end, value]

    Returns:
        DataFrame with [instrument_id, value]
    """
    period_priority = {"r12": 1, "year": 2}
    return (
        pit_df.filter(pl.col("period_type").is_in(list(period_priority)))
        .with_columns(
            pl.col("period_type").replace_strict(period_priority, return_dtype=pl.Int32).alias(
                "priority"
            )
        )
        .sort(["instrument_id", "period_end", "priority"], descending=[False, True, False])
        .group_by("instrument_id", maintain_order=True)
        .agg(pl.col("value").first())
    )


def _get_base_metric(
    metric: str,
    as_of_date: date,
    instrument_ids: list[int] | None = None,
) -> pl.DataFrame:
    """Load base metric from PostgreSQL.

    Loads ALL historical data up to as_of_date to support transformations.
    For fundamental metrics, uses fundamentals_pit with proper PIT logic.
    For price metrics, uses price_metrics table.

    Args:
        metric: Base metric name (e.g., "roic", "pe_ratio", "return_12m")
        as_of_date: Load all data up to this date
        instrument_ids: Optional filter

    Returns:
        DataFrame with columns [instrument_id, date, value]
    """
    from datetime import timedelta

    # Load historical data (10 years max, should be enough for any transformation)
    from_date = as_of_date - timedelta(days=10 * 365)

    # Try fundamentals_pit first (CORRECT PIT data)
    # Get month-end dates in the window
    from factor_investor.dates import month_end_dates

    month_ends = month_end_dates(from_date, as_of_date)

    if len(month_ends) > 0:
        # Try loading from fundamentals_pit with proper PIT logic
        from factor_investor.pit.queries import as_of as pit_as_of

        all_data = []
        for month_end in month_ends:
            try:
                # Get PIT data for this month-end
                pit_df = pit_as_of(
                    as_of_date=month_end,
                    instrument_ids=instrument_ids,
                    metrics=[metric],
                    history_years=1,  # Only need latest value for each date
                )

                if len(pit_df) > 0:
                    latest_per_instrument = (
                        select_latest_ttm(pit_df)
                        .with_columns(pl.lit(month_end).alias("date"))
                        .select(["instrument_id", "date", "value"])
                    )

                    all_data.append(latest_per_instrument)
            except Exception as e:
                logger.debug(f"No fundamentals_pit data for {metric} on {month_end}: {e}")
                continue

        if len(all_data) > 0:
            result_df = pl.concat(all_data)
            logger.debug(f"Loaded {len(result_df)} rows from fundamentals_pit for {metric}")
            return result_df

    # Try price_metrics
        query = (
            select(
                PriceMetric.instrument_id,
                PriceMetric.date,
                PriceMetric.value,
            )
            .where(
                PriceMetric.metric == metric,
                PriceMetric.date >= from_date,
                PriceMetric.date <= as_of_date,
            )
            .order_by(PriceMetric.instrument_id, PriceMetric.date)
        )

        if instrument_ids:
            query = query.where(PriceMetric.instrument_id.in_(instrument_ids))

        result = session.execute(query)
        rows = result.fetchall()

        if len(rows) > 0:
            return pl.DataFrame(
                {
                    "instrument_id": [r[0] for r in rows],
                    "date": [r[1] for r in rows],
                    "value": [float(r[2]) if r[2] is not None else None for r in rows],
                }
            )

        # Not found
        return pl.DataFrame(
            schema={
                "instrument_id": pl.Int32,
                "date": pl.Date,
                "value": pl.Float64,
            }
        )


def _apply_transformation(
    base_df: pl.DataFrame, transformation: str, window_years: int | None
) -> pl.DataFrame:
    """Apply transformation to base metric.

    Args:
        base_df: Base metric data
        transformation: Transformation name
        window_years: Window for windowed transformations

    Returns:
        Transformed DataFrame
    """
    if transformation == "level" or transformation is None:
        return transformations.transform_level(base_df)

    elif transformation == "mean":
        if window_years is None:
            raise ValueError("mean transformation requires window_years")
        return transformations.transform_mean(base_df, window_years)

    elif transformation == "median":
        if window_years is None:
            raise ValueError("median transformation requires window_years")
        return transformations.transform_median(base_df, window_years)

    elif transformation == "min":
        if window_years is None:
            raise ValueError("min transformation requires window_years")
        return transformations.transform_min(base_df, window_years)

    elif transformation == "max":
        if window_years is None:
            raise ValueError("max transformation requires window_years")
        return transformations.transform_max(base_df, window_years)

    elif transformation == "cagr":
        if window_years is None:
            raise ValueError("cagr transformation requires window_years")
        return transformations.transform_cagr(base_df, window_years)

    elif transformation == "trend":
        if window_years is None:
            raise ValueError("trend transformation requires window_years")
        return transformations.transform_trend(base_df, window_years)

    elif transformation == "stability" or transformation == "cv":
        if window_years is None:
            raise ValueError("stability_cv transformation requires window_years")
        return transformations.transform_stability_cv(base_df, window_years)

    elif transformation == "percentile":
        if window_years is None:
            raise ValueError("percentile_history transformation requires window_years")
        return transformations.transform_percentile_history(base_df, window_years)

    else:
        raise ValueError(f"Unknown transformation: {transformation}")


def _apply_normalization(df: pl.DataFrame, normalization: str) -> pl.DataFrame:
    """Apply normalization to transformed data.

    Args:
        df: Transformed data
        normalization: Normalization name

    Returns:
        Normalized DataFrame
    """
    if normalization == "raw":
        return normalizations.normalize_raw(df)

    elif normalization == "pct":
        return normalizations.normalize_percentile(df)

    elif normalization == "zscore":
        return normalizations.normalize_zscore(df, winsorize=True)

    elif normalization == "rank":
        return normalizations.normalize_rank(df)

    elif normalization == "quantile":
        return normalizations.normalize_quantile(df, n_quantiles=5)

    else:
        raise ValueError(f"Unknown normalization: {normalization}")
