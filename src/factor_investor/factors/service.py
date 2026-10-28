"""Factor service for building base metrics."""

import logging
from dataclasses import dataclass
from datetime import date

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from factor_investor.db import get_session
from factor_investor.factors.base_metrics import (
    calculate_fundamental_metrics,
    calculate_price_metrics,
)
from factor_investor.factors.models import FundamentalMetric, PriceMetric

logger = logging.getLogger(__name__)


@dataclass
class BuildStats:
    """Statistics from base metrics build."""

    dates_processed: int
    fundamental_metrics_inserted: int
    price_metrics_inserted: int


class FactorService:
    """Service for building base metrics."""

    def build_base_metrics(
        self,
        from_date: date | None = None,
        to_date: date | None = None,
        force_rebuild: bool = False,
        metrics: list[str] | None = None,
    ) -> BuildStats:
        """Build fundamental + price base metrics for all month-ends.

        Similar to build_universe() - iterate over month-end dates.

        Args:
            from_date: Start date (default: 2006-01-01)
            to_date: End date (default: today)
            force_rebuild: Delete existing data and rebuild
            metrics: Optional list of specific metrics to build (e.g., ['ev_ebitda', 'operating_cash_flow']).
                    If None, builds all metrics. Useful for incremental updates.

        Returns:
            Build statistics
        """
        if from_date is None:
            from_date = date(2006, 1, 1)
        if to_date is None:
            to_date = date.today()

        logger.info(f"Building base metrics from {from_date} to {to_date}")

        from factor_investor.dates import month_end_dates

        month_ends = month_end_dates(from_date, to_date)

        logger.info(f"Found {len(month_ends)} month-end dates to process")

        with get_session() as session:
            if force_rebuild:
                logger.warning("Force rebuild: deleting existing base metrics...")
                session.execute(delete(FundamentalMetric))
                session.execute(delete(PriceMetric))
                session.commit()

            total_fund_metrics = 0
            total_price_metrics = 0

            for idx, month_end in enumerate(month_ends):
                try:
                    # Calculate fundamental metrics
                    fund_metrics = calculate_fundamental_metrics(
                        session, month_end, metrics_filter=metrics
                    )

                    # Batch insert
                    if fund_metrics:
                        batch_size = 100  # Reduced to avoid parameter limits
                        for i in range(0, len(fund_metrics), batch_size):
                            batch = fund_metrics[i : i + batch_size]
                            stmt = pg_insert(FundamentalMetric).values(batch)
                            stmt = stmt.on_conflict_do_nothing(constraint="uq_fundamental_metrics")
                            session.execute(stmt)
                        total_fund_metrics += len(fund_metrics)

                    # Calculate price metrics
                    price_metrics = calculate_price_metrics(session, month_end, metrics_filter=metrics)

                    # Batch insert
                    if price_metrics:
                        batch_size = 100  # Reduced to avoid parameter limits
                        for i in range(0, len(price_metrics), batch_size):
                            batch = price_metrics[i : i + batch_size]
                            stmt = pg_insert(PriceMetric).values(batch)
                            stmt = stmt.on_conflict_do_nothing(constraint="uq_price_metrics")
                            session.execute(stmt)
                        total_price_metrics += len(price_metrics)

                    # Commit after each month-end date
                    session.commit()

                    # Progress logging after successful commit
                    if (idx + 1) % 10 == 0:
                        logger.info(f"  Progress: {idx + 1}/{len(month_ends)} dates processed")

                except Exception as e:
                    logger.error(f"Error building base metrics for {month_end}: {e}")
                    session.rollback()
                    continue

        stats = BuildStats(
            dates_processed=len(month_ends),
            fundamental_metrics_inserted=total_fund_metrics,
            price_metrics_inserted=total_price_metrics,
        )

        logger.info(
            f"Base metrics build complete: {total_fund_metrics:,} fundamental, "
            f"{total_price_metrics:,} price metrics across {len(month_ends)} dates"
        )

        return stats
