"""Calculate fundamental and price base metrics."""

import logging
from datetime import date, timedelta
from decimal import Decimal

import polars as pl
from sqlalchemy import text
from sqlalchemy.orm import Session

from factor_investor.pit import as_of

logger = logging.getLogger(__name__)


def valuation_ratios(price: float, row: dict) -> dict[str, float]:
    """Valuation ratios from a point-in-time report row and a price.

    Börsdata units: totals (revenues, free_cash_flow, net_debt,
    operating_income) and number_of_shares are in millions, so
    market cap in millions = price * number_of_shares. earnings_per_share,
    book_value_per_share and dividend (DPS) are per share. Report values are
    already converted to the trading currency.

    Ratios with a zero, negative or missing denominator are omitted, except
    yields, which are well-defined for negative or zero numerators.

    Args:
        price: Share price
        row: Report values keyed by metric name

    Returns:
        Dict of metric name -> value (only computable ratios)
    """
    max_ratio = 1_000_000  # Larger values are data errors

    def num(key: str) -> float | None:
        value = row.get(key)
        return float(value) if value is not None else None

    ratios: dict[str, float] = {}
    if price <= 0:
        return ratios

    eps = num("earnings_per_share")
    if eps is not None and eps > 0:
        ratios["pe_ratio"] = price / eps

    book_value = num("book_value_per_share")
    if book_value is not None and book_value > 0:
        ratios["pb_ratio"] = price / book_value

    dividend = num("dividend")
    if dividend is not None and dividend >= 0:
        ratios["dividend_yield"] = dividend / price

    shares = num("number_of_shares")
    if shares is not None and shares > 0:
        market_cap = price * shares  # millions

        revenues = num("revenues")
        if revenues is not None and revenues > 0:
            ratios["ps_ratio"] = market_cap / revenues

        fcf = num("free_cash_flow")
        if fcf is not None:
            ratios["fcf_yield"] = fcf / market_cap
            if fcf > 0:
                ratios["p_fcf"] = market_cap / fcf

        net_debt = num("net_debt")
        operating_income = num("operating_income")
        if net_debt is not None and operating_income is not None and operating_income > 0:
            ratios["ev_ebit"] = (market_cap + net_debt) / operating_income

    return {name: value for name, value in ratios.items() if abs(value) < max_ratio}


def calculate_fundamental_metrics(
    session: Session,
    rebal_date: date,
    instrument_ids: list[int] | None = None,
    metrics_filter: list[str] | None = None,
) -> list[dict]:
    """Calculate fundamental base metrics for a rebalancing date.

    Metrics:
    - Valuation: P/E, P/B, P/S, EV/EBIT, EV/EBITDA, EV/Sales, P/FCF, FCF yield, div yield
    - From PIT: ROIC, ROE, ROA, margins, FCF, debt ratios, etc. (already calculated)

    Process:
    1. Get PIT fundamentals as_of(rebal_date)
    2. Get prices as_of(rebal_date)
    3. Calculate valuation ratios (P/E = price / eps, etc.)
    4. Return list of metric dicts for bulk insert

    Args:
        session: Database session
        rebal_date: Rebalancing date (typically month-end)
        instrument_ids: Optional filter for specific instruments
        metrics_filter: Optional list of specific metrics to calculate (e.g., ['pe_ratio', 'pb_ratio']).
                       If None, calculates all metrics.

    Returns:
        List of metric dictionaries for bulk insert
    """
    metrics = []

    # Helper function to check if metric should be calculated
    def should_calculate(metric_name: str) -> bool:
        """Check if metric should be calculated based on filter."""
        if metrics_filter is None:
            return True  # No filter = calculate all
        return metric_name in metrics_filter

    # Get PIT fundamentals
    pit_metrics = [
        # Base metrics for valuation
        "earnings_per_share",
        "book_value_per_share",
        "revenues",
        "operating_income",
        "free_cash_flow",
        "net_debt",
        "dividend",
        "number_of_shares",
        "total_assets",
        "total_equity",
        # Profitability metrics (pass through)
        "roe",
        "roic",
        "roic_pretax",
        "roa",
        "gross_margin",
        "operating_margin",
        "net_margin",
        "fcf_margin",
        "asset_turnover",
        "current_ratio",
        "net_debt_to_ebit",
        "solvency",
        # For Piotroski F-score
        "cash_flow_from_operating_activities",
        # For growth (current period)
        "profit_to_equity_holders",
    ]
    pit_df_long = as_of(rebal_date, instrument_ids=instrument_ids, metrics=pit_metrics)

    if len(pit_df_long) == 0:
        logger.warning(f"No PIT data for {rebal_date}")
        return metrics

    # CRITICAL: Filter to correct period_type
    # For valuation metrics, we need trailing twelve months (TTM) data, not quarterly
    # Priority: r12 (rolling 12 months) > year > quarter (fallback only)
    # as_of() returns ALL period_types, we must select the right one

    # Step 1: Prefer r12 (trailing twelve months)
    pit_df_r12 = pit_df_long.filter(pl.col("period_type") == "r12")

    # Step 2: For metrics without r12, use year
    pit_df_year = pit_df_long.filter(pl.col("period_type") == "year")

    # Step 3: Combine - r12 takes precedence
    # Get unique (instrument_id, metric) pairs that have r12
    r12_pairs = pit_df_r12.select(["instrument_id", "metric"]).unique()

    # For instruments without r12, use year
    pit_df_filtered = pl.concat([
        pit_df_r12,
        pit_df_year.join(
            r12_pairs,
            on=["instrument_id", "metric"],
            how="anti"  # Only keep rows NOT in r12
        )
    ])

    if len(pit_df_filtered) == 0:
        logger.warning(f"No r12/year PIT data for {rebal_date}")
        return metrics

    # VALIDATION: Verify data is sorted correctly (period_end DESC)
    # Check a sample of instruments to ensure first row has latest period_end
    for ins_id in pit_df_filtered["instrument_id"].unique().head(10).to_list():
        ins_data = pit_df_filtered.filter(pl.col("instrument_id") == ins_id)
        if len(ins_data) > 1:
            first_period = ins_data[0, "period_end"]
            last_period = ins_data[-1, "period_end"]
            assert first_period >= last_period, (
                f"Data NOT sorted correctly for instrument {ins_id}: "
                f"first={first_period}, last={last_period}"
            )

    # Log coverage
    total_instruments = pit_df_long.select("instrument_id").n_unique()
    filtered_instruments = pit_df_filtered.select("instrument_id").n_unique()
    logger.debug(
        f"Filtered to r12/year: {filtered_instruments}/{total_instruments} instruments "
        f"({filtered_instruments/total_instruments*100:.1f}%)"
    )

    # Pivot to wide format: one row per instrument with columns for each metric
    # Note: as_of() returns data sorted by period_end DESC (most recent first)
    # So we use .first() to get the most recent value for each metric
    #
    # CRITICAL: Also get period_end to validate data freshness
    pit_df = (
        pit_df_filtered.group_by(["instrument_id", "metric"])
        .agg([
            pl.col("value").first().alias("value"),
            pl.col("known_from").first().alias("known_from"),
            pl.col("period_end").first().alias("period_end"),
        ])
        .pivot(values="value", index="instrument_id", on="metric")
    )

    # Get known_from and period_end separately (take max for each instrument)
    # This represents when the most recent data became available
    metadata_df = (
        pit_df_filtered.group_by("instrument_id").agg([
            pl.col("known_from").max().alias("known_from"),
            pl.col("period_end").max().alias("latest_period_end"),
        ])
    )
    pit_df = pit_df.join(metadata_df, on="instrument_id", how="left")

    # VALIDATION: Check data freshness
    # Warn if using data older than 2 years
    max_age_days = 730  # 2 years
    date_cutoff = rebal_date - timedelta(days=max_age_days)

    old_data_count = len(pit_df.filter(pl.col("latest_period_end") < date_cutoff))
    if old_data_count > 0:
        pct_old = (old_data_count / len(pit_df)) * 100
        logger.warning(
            f"{rebal_date}: {old_data_count} instruments ({pct_old:.1f}%) using data older than 2 years "
            f"(period_end < {date_cutoff})"
        )

        # Log a sample of very old data for debugging
        if old_data_count > 0:
            very_old = pit_df.filter(pl.col("latest_period_end") < date_cutoff).head(5)
            for row in very_old.iter_rows(named=True):
                logger.debug(
                    f"  Instrument {row['instrument_id']}: using data from {row['latest_period_end']} "
                    f"(known_from {row['known_from']})"
                )

    # VALIDATION: Spot-check that we're using recent data for key metrics
    # For a sample of instruments, verify period_end is within reasonable range
    sample_size = min(10, len(pit_df))
    if sample_size > 0:
        sample_instruments = pit_df.head(sample_size)
        for row in sample_instruments.iter_rows(named=True):
            period_end = row.get("latest_period_end")
            if period_end:
                age_days = (rebal_date - period_end).days
                # Assert data is not from the future (critical bug indicator)
                assert period_end <= rebal_date, (
                    f"CRITICAL: Future data detected! Instrument {row['instrument_id']} "
                    f"has period_end {period_end} > rebal_date {rebal_date}"
                )
                # Warn if data is extremely stale (>3 years)
                if age_days > 1095:
                    logger.warning(
                        f"Very stale data: Instrument {row['instrument_id']} using data from "
                        f"{period_end} ({age_days} days old)"
                    )

    # Get prices
    from factor_investor.universe.queries import get_prices_on_date

    prices_df = get_prices_on_date(rebal_date, instrument_ids)

    if len(prices_df) == 0:
        logger.warning(f"No price data for {rebal_date}")
        return metrics

    # Join
    joined_df = pit_df.join(prices_df, on="instrument_id", how="inner")

    # Constants for validation
    MAX_RATIO = 1_000_000  # Skip ratios > 1 million (likely data issues)
    MIN_DENOMINATOR = 0.001  # Skip growth if base < 0.001 (prevents extreme ratios)

    # Calculate valuation metrics
    for row in joined_df.iter_rows(named=True):
        ins_id = row["instrument_id"]
        price = row.get("price")
        known_from = row.get("known_from")  # From PIT

        if not price or not known_from:
            continue

        for metric_name, value in valuation_ratios(float(price), row).items():
            if should_calculate(metric_name):
                metrics.append(
                    {
                        "instrument_id": ins_id,
                        "metric": metric_name,
                        "date": rebal_date,
                        "value": value,
                        "known_from": known_from,
                    }
                )

        # Pass-through metrics from PIT
        passthrough_metrics = [
            # Profitability
            "roe", "roic", "roic_pretax", "roa",
            "gross_margin", "operating_margin", "net_margin", "fcf_margin",
            "asset_turnover", "current_ratio", "net_debt_to_ebit", "solvency",
            # For Piotroski F-score
            "cash_flow_from_operating_activities",
            "total_equity",
        ]
        for metric_name in passthrough_metrics:
            if should_calculate(metric_name):
                value = row.get(metric_name)
                if value is not None:
                    float_value = float(value)
                    # Skip extreme values
                    if abs(float_value) < MAX_RATIO:
                        metrics.append(
                            {
                                "instrument_id": ins_id,
                                "metric": metric_name,
                                "date": rebal_date,
                                "value": float_value,
                                "known_from": known_from,
                            }
                        )

    # Calculate growth metrics (1-year growth)
    growth_metrics_map = {
        "revenue_growth_1y": "revenues",
        "profit_growth_1y": "profit_to_equity_holders",
        "fcf_growth_1y": "free_cash_flow",
    }

    for growth_metric, base_metric in growth_metrics_map.items():
        # Skip if not in filter
        if not should_calculate(growth_metric):
            continue

        # Get historical values (1 year ago)
        one_year_ago = rebal_date - timedelta(days=365)
        hist_df_long = as_of(one_year_ago, instrument_ids=instrument_ids, metrics=[base_metric])

        if len(hist_df_long) == 0:
            continue

        # CRITICAL: Filter to r12/year (same as current values)
        hist_df_r12 = hist_df_long.filter(pl.col("period_type") == "r12")
        hist_df_year = hist_df_long.filter(pl.col("period_type") == "year")
        r12_pairs_hist = hist_df_r12.select(["instrument_id", "metric"]).unique()

        hist_df_filtered = pl.concat([
            hist_df_r12,
            hist_df_year.join(r12_pairs_hist, on=["instrument_id", "metric"], how="anti")
        ])

        if len(hist_df_filtered) == 0:
            continue

        # Pivot historical data
        # Note: as_of() returns data sorted by period_end DESC, so .first() gets most recent
        hist_df = (
            hist_df_filtered.group_by(["instrument_id", "metric"])
            .agg([pl.col("value").first()])
            .pivot(values="value", index="instrument_id", on="metric")
        )

        # Join current with historical
        current_values = pit_df.select(["instrument_id", base_metric, "known_from"])
        growth_df = current_values.join(
            hist_df.select(["instrument_id", pl.col(base_metric).alias(f"{base_metric}_1y_ago")]),
            on="instrument_id",
            how="inner",
        )

        # Calculate growth
        for row in growth_df.iter_rows(named=True):
            current = row.get(base_metric)
            past = row.get(f"{base_metric}_1y_ago")
            known_from = row.get("known_from")

            if current and past and abs(float(past)) > MIN_DENOMINATOR:
                growth = (float(current) - float(past)) / abs(float(past))
                # Cap growth at +/- 100x (10,000% growth) to avoid extreme values
                if abs(growth) < 100:
                    metrics.append(
                        {
                            "instrument_id": row["instrument_id"],
                            "metric": growth_metric,
                            "date": rebal_date,
                            "value": growth,
                            "known_from": known_from,
                        }
                    )

    logger.debug(f"Calculated {len(metrics)} fundamental metrics for {rebal_date}")
    return metrics


def calculate_price_metrics(
    session: Session,
    rebal_date: date,
    instrument_ids: list[int] | None = None,
    metrics_filter: list[str] | None = None,
) -> list[dict]:
    """Calculate price base metrics for a rebalancing date.

    Metrics:
    - Returns: 1m, 3m, 6m, 12m, 12-1m momentum
    - Volatility: 60d, 250d
    - Max drawdown: 1y
    - Technical: distance to MA 50d/200d, distance to 52w high

    Process:
    1. Get total returns for past year
    2. Calculate returns, volatility, momentum
    3. Calculate technical indicators
    4. Return list of metric dicts

    Args:
        session: Database session
        rebal_date: Rebalancing date (typically month-end)
        instrument_ids: Optional filter for specific instruments
        metrics_filter: Optional list of specific metrics to calculate (e.g., ['return_1m', 'volatility_60d']).
                       If None, calculates all metrics.

    Returns:
        List of metric dictionaries for bulk insert
    """
    metrics = []

    # Helper function to check if metric should be calculated
    def should_calculate(metric_name: str) -> bool:
        """Check if metric should be calculated based on filter."""
        if metrics_filter is None:
            return True  # No filter = calculate all
        return metric_name in metrics_filter

    # Get instrument IDs if not specified
    if instrument_ids is None:
        # Get all instruments that have prices on rebal_date
        from sqlalchemy import select, text

        query = text("SELECT DISTINCT instrument_id FROM total_returns WHERE date = :rebal_date")
        result = session.execute(query, {"rebal_date": rebal_date})
        instrument_ids = [row[0] for row in result.fetchall()]

        if len(instrument_ids) == 0:
            logger.warning(f"No instruments with price data for {rebal_date}")
            return metrics

    # Get total returns for past year (400 calendar days covers 253 trading days)
    from factor_investor.universe.queries import get_total_returns

    returns_df = get_total_returns(
        instrument_ids=instrument_ids,
        from_date=rebal_date - timedelta(days=400),
        to_date=rebal_date,
    )

    if len(returns_df) == 0:
        logger.warning(f"No price data for {rebal_date}")
        return metrics

    # Calculate per instrument
    for ins_id in returns_df["instrument_id"].unique():
        tr = (
            returns_df.filter(pl.col("instrument_id") == ins_id)
            .sort("date")["total_return_index"]
            .drop_nulls()
        )
        for metric_name, value in price_metrics_from_series(tr).items():
            if should_calculate(metric_name):
                metrics.append(
                    {"instrument_id": ins_id, "metric": metric_name, "date": rebal_date, "value": value}
                )

    logger.debug(f"Calculated {len(metrics)} price metrics for {rebal_date}")
    return metrics


# Lookbacks in the instrument's own trading days
MONTH = 21
YEAR = 252


def price_metrics_from_series(tr: pl.Series) -> dict[str, float]:
    """Price metrics from a total return index, oldest first, ending at the
    calculation date. Metrics needing more history than available are omitted.

    A return over N trading days compares tr[-1] with tr[-(N+1)].

    Args:
        tr: Total return index values (one per trading day)

    Returns:
        Dict of metric name -> value
    """
    n = len(tr)
    metrics: dict[str, float] = {}
    if n == 0:
        return metrics
    last = float(tr[-1])

    def back(days: int) -> float:
        return float(tr[-(days + 1)])

    for name, days in [
        ("return_1m", MONTH),
        ("return_3m", 3 * MONTH),
        ("return_6m", 6 * MONTH),
        ("return_12m", YEAR),
    ]:
        if n > days:
            metrics[name] = last / back(days) - 1

    # 12-1 momentum: 12-month return excluding the most recent month
    if n > YEAR:
        metrics["momentum_12_1m"] = back(MONTH) / back(YEAR) - 1

    for name, days in [("volatility_60d", 60), ("volatility_250d", 250)]:
        if n > days:
            daily = tr.tail(days + 1).pct_change().drop_nulls()
            metrics[name] = float(daily.std()) * (YEAR**0.5)

    if n > YEAR:
        window = tr.tail(YEAR + 1)
        metrics["max_drawdown_1y"] = float((window / window.cum_max() - 1).min())
        metrics["distance_52w_high"] = last / float(window.max()) - 1

    for name, days in [("distance_ma_50d", 50), ("distance_ma_200d", 200)]:
        if n >= days:
            metrics[name] = last / float(tr.tail(days).mean()) - 1

    return metrics
