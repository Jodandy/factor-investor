"""Point-in-time fundamentals build service."""

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from factor_investor.db import get_session
from factor_investor.ingest.models import ReportQuarter, ReportR12, ReportYear
from factor_investor.pit.config import ReportDelayConfig, load_config
from factor_investor.pit.metrics import BASE_METRICS, DERIVED_METRICS, MetricInputs
from factor_investor.pit.models import FundamentalPIT

logger = logging.getLogger(__name__)


@dataclass
class BuildStats:
    """Statistics from building the PIT table."""

    total_reports_processed: int
    base_metrics_inserted: int
    derived_metrics_inserted: int
    fallback_dates_used: int
    actual_dates_used: int

    @property
    def total_metrics_inserted(self) -> int:
        """Total metrics inserted (base + derived)."""
        return self.base_metrics_inserted + self.derived_metrics_inserted

    @property
    def fallback_percentage(self) -> float:
        """Percentage of reports using fallback dates."""
        total = self.fallback_dates_used + self.actual_dates_used
        if total == 0:
            return 0.0
        return 100.0 * self.fallback_dates_used / total


class PITService:
    """Service for building and querying point-in-time fundamentals."""

    def __init__(self, config: ReportDelayConfig | None = None):
        """Initialize PIT service.

        Args:
            config: Report delay configuration. If None, loads from settings.toml.
        """
        self.config = config or load_config()

    def calculate_known_from(
        self,
        report_date: date | None,
        period_end: date,
        period_type: str,
    ) -> tuple[date, bool]:
        """Calculate when a report became known to the market.

        Priority:
        1. Use report_date if plausible: not the 1899-12-30/31 placeholder and
           at least min_publication_days after period_end (Börsdata sets
           report_date == period_end on ~9% of annual reports; trusting it
           would be lookahead)
        2. Fallback: period_end + delay_days + trading_day_buffer

        Args:
            report_date: Publication date from Börsdata (may be None or placeholder)
            period_end: Fiscal period end date
            period_type: 'year', 'quarter', or 'r12'

        Returns:
            Tuple of (known_from_date, used_fallback)
        """
        # Filter Börsdata's "missing" indicator (1899-12-30/31) and dates too
        # close to (or before) the period end to be real publication dates
        earliest_plausible = period_end + timedelta(days=self.config.min_publication_days)
        if report_date and report_date.year != 1899 and report_date >= earliest_plausible:
            # Use actual publication date + trading buffer
            known_from = report_date + timedelta(days=self.config.trading_day_buffer)
            return (known_from, False)

        # Fallback: conservative estimate
        delay = self.config.annual if period_type == "year" else self.config.quarterly
        total_delay = delay + self.config.trading_day_buffer
        known_from = period_end + timedelta(days=total_delay)
        return (known_from, True)

    def build_pit(
        self,
        instrument_ids: list[int] | None = None,
        force_rebuild: bool = False,
    ) -> BuildStats:
        """Build point-in-time fundamentals table.

        Args:
            instrument_ids: Specific instruments to build (None = all)
            force_rebuild: Clear existing data before building

        Returns:
            Build statistics
        """
        logger.info("Starting PIT build...")

        stats = BuildStats(
            total_reports_processed=0,
            base_metrics_inserted=0,
            derived_metrics_inserted=0,
            fallback_dates_used=0,
            actual_dates_used=0,
        )

        with get_session() as session:
            # Clear existing data if requested
            if force_rebuild:
                logger.info("Clearing existing PIT data...")
                self._clear_pit_table(session, instrument_ids)
                session.commit()  # Commit the clear operation

            # Extract base metrics from all three report tables
            logger.info("Extracting base metrics from reports...")
            self._extract_reports(session, ReportYear, "year", instrument_ids, stats)
            self._extract_reports(session, ReportQuarter, "quarter", instrument_ids, stats)
            self._extract_reports(session, ReportR12, "r12", instrument_ids, stats)

            session.commit()
            logger.info(
                f"Base metrics extraction complete: {stats.base_metrics_inserted:,} metrics from {stats.total_reports_processed:,} reports"
            )

            # Calculate derived metrics
            logger.info("Calculating derived metrics...")
            derived_count = self._calculate_derived_metrics(session, instrument_ids)
            stats.derived_metrics_inserted = derived_count
            session.commit()

            logger.info(f"Derived metrics calculation complete: {derived_count:,} metrics")

        logger.info(f"PIT build complete: {stats.total_metrics_inserted:,} total metrics")
        logger.info(
            f"Publication date usage: {stats.actual_dates_used:,} actual ({100 - stats.fallback_percentage:.1f}%), "
            f"{stats.fallback_dates_used:,} fallback ({stats.fallback_percentage:.1f}%)"
        )

        return stats

    def _clear_pit_table(
        self,
        session: Session,
        instrument_ids: list[int] | None,
    ) -> None:
        """Clear existing PIT data."""
        # Set a timeout for the clear operation
        session.execute(text("SET statement_timeout = '60s'"))

        if instrument_ids:
            session.execute(
                text("DELETE FROM fundamentals_pit WHERE instrument_id = ANY(:ids)"),
                {"ids": instrument_ids},
            )
        else:
            session.execute(text("TRUNCATE fundamentals_pit"))

        # Reset timeout
        session.execute(text("SET statement_timeout = 0"))

    def _extract_reports(
        self,
        session: Session,
        report_model: type[ReportYear | ReportQuarter | ReportR12],
        period_type: str,
        instrument_ids: list[int] | None,
        stats: BuildStats,
    ) -> None:
        """Extract base metrics from a report table.

        Args:
            session: Database session
            report_model: SQLAlchemy model (ReportYear, ReportQuarter, or ReportR12)
            period_type: 'year', 'quarter', or 'r12'
            instrument_ids: Filter to specific instruments
            stats: Build statistics to update
        """
        # Build query
        query = select(report_model)
        if instrument_ids:
            query = query.where(report_model.ins_id.in_(instrument_ids))

        reports = session.execute(query).scalars().all()

        logger.info(f"Processing {len(reports):,} {period_type} reports...")

        batch_size = 100  # Reduced to avoid parameter limits (each report = ~42 metrics)
        batch = []

        for i, report in enumerate(reports):
            stats.total_reports_processed += 1

            # Calculate known_from date
            known_from, used_fallback = self.calculate_known_from(
                report.report_date,  # type: ignore[attr-defined]
                report.report_end_date,  # type: ignore[attr-defined]
                period_type,
            )

            if used_fallback:
                stats.fallback_dates_used += 1
            else:
                stats.actual_dates_used += 1

            # Extract base metrics
            for metric_name in BASE_METRICS:
                value = getattr(report, metric_name, None)

                # Skip if NULL
                if value is None:
                    continue

                batch.append(
                    {
                        "instrument_id": report.ins_id,  # type: ignore[attr-defined]
                        "metric": metric_name,
                        "period_end": report.report_end_date,  # type: ignore[attr-defined]
                        "period_type": period_type,
                        "value": value,
                        "known_from": known_from,
                    }
                )
                stats.base_metrics_inserted += 1

            # Insert batch
            if len(batch) >= batch_size:
                self._insert_batch(session, batch)
                batch = []

            # Progress logging and commit every 10k reports
            if (i + 1) % 10000 == 0:
                session.commit()  # Commit progress incrementally
                logger.info(
                    f"  Progress: {i + 1:,}/{len(reports):,} {period_type} reports processed"
                )

        # Insert remaining
        if batch:
            self._insert_batch(session, batch)

        # Commit any remaining data
        session.commit()

    def _insert_batch(self, session: Session, batch: list[dict[str, Any]]) -> None:
        """Insert a batch of metrics using bulk insert with conflict handling."""
        stmt = insert(FundamentalPIT).values(batch)
        stmt = stmt.on_conflict_do_nothing(constraint="uq_fundamentals_pit")  # Skip duplicates
        session.execute(stmt)

    def _calculate_derived_metrics(
        self,
        session: Session,
        instrument_ids: list[int] | None,
    ) -> int:
        """Calculate derived metrics from base metrics.

        For each (instrument, period_end, period_type, known_from) combination:
        1. Fetch all base metric values
        2. Calculate derived metrics
        3. Insert into fundamentals_pit

        Returns:
            Number of derived metrics inserted
        """
        # Get unique (instrument_id, period_end, period_type, known_from) combinations
        query = text("""
            SELECT DISTINCT instrument_id, period_end, period_type, known_from
            FROM fundamentals_pit
        """)

        if instrument_ids:
            query = text("""
                SELECT DISTINCT instrument_id, period_end, period_type, known_from
                FROM fundamentals_pit
                WHERE instrument_id = ANY(:ids)
            """)

        params = {"ids": instrument_ids} if instrument_ids else {}
        combinations = session.execute(query, params).fetchall()

        logger.info(f"Calculating derived metrics for {len(combinations):,} report combinations...")

        derived_count = 0
        batch = []
        batch_size = 100  # Reduced to avoid parameter limits (each combination = multiple derived metrics)

        for i, (ins_id, period_end, period_type, known_from) in enumerate(combinations):
            # Fetch base metrics for this combination
            base_values_query = select(FundamentalPIT).where(
                FundamentalPIT.instrument_id == ins_id,
                FundamentalPIT.period_end == period_end,
                FundamentalPIT.period_type == period_type,
                FundamentalPIT.known_from == known_from,
                FundamentalPIT.metric.in_(BASE_METRICS),
            )

            base_rows = session.execute(base_values_query).scalars().all()

            # Build inputs dictionary
            inputs: MetricInputs = {}
            for row in base_rows:
                inputs[row.metric] = row.value  # type: ignore

            # Calculate each derived metric
            for metric_name, calc_func in DERIVED_METRICS.items():
                value = calc_func(inputs)

                # Skip if calculation returned None
                if value is None:
                    continue

                batch.append(
                    {
                        "instrument_id": ins_id,
                        "metric": metric_name,
                        "period_end": period_end,
                        "period_type": period_type,
                        "value": value,
                        "known_from": known_from,
                    }
                )
                derived_count += 1

            # Insert batch
            if len(batch) >= batch_size:
                self._insert_batch(session, batch)
                batch = []

            # Progress logging and commit every 5k combinations
            if (i + 1) % 5000 == 0:
                session.commit()  # Commit progress incrementally
                logger.info(f"  Progress: {i + 1:,}/{len(combinations):,} combinations processed")

        # Insert remaining
        if batch:
            self._insert_batch(session, batch)

        # Commit any remaining data
        session.commit()

        return derived_count
