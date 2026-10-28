"""Service for building investable universe."""

import logging
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from factor_investor.db import get_session
from factor_investor.ingest.models import Instrument, StockPrice
from factor_investor.pit import as_of
from factor_investor.universe.config import UniverseConfig, load_universe_config
from factor_investor.universe.models import UniverseConstituent

logger = logging.getLogger(__name__)


@dataclass
class BuildStats:
    """Statistics from universe build operation."""

    total_dates: int
    total_eligible: int
    total_excluded: int
    exclusion_breakdown: dict[str, int]


class UniverseService:
    """Service for building investable universe."""

    def __init__(self, config: UniverseConfig | None = None) -> None:
        """Initialize universe service.

        Args:
            config: Universe configuration (None = load from settings.toml)
        """
        self.config = config or load_universe_config()

    def build_universe_monthly(
        self,
        from_date: date | None = None,
        to_date: date | None = None,
        force_rebuild: bool = False,
    ) -> BuildStats:
        """Build universe for all month-end dates in range.

        Args:
            from_date: Start date (default: 2006-01-01)
            to_date: End date (default: today)
            force_rebuild: If True, delete existing data and rebuild

        Returns:
            Statistics from build operation
        """
        if from_date is None:
            from_date = date(2006, 1, 1)
        if to_date is None:
            to_date = date.today()

        logger.info(f"Building monthly universe from {from_date} to {to_date}")

        # Get all month-end dates in range
        month_ends = self._get_month_end_dates(from_date, to_date)
        logger.info(f"Found {len(month_ends)} month-end dates to process")

        with get_session() as session:
            if force_rebuild:
                logger.warning("Force rebuild: deleting existing universe data...")
                session.execute(delete(UniverseConstituent))
                session.commit()

            total_eligible = 0
            total_excluded = 0
            exclusion_breakdown: dict[str, int] = {}

            for idx, month_end in enumerate(month_ends):
                if (idx + 1) % 10 == 0:
                    logger.info(f"  Progress: {idx + 1}/{len(month_ends)} dates processed")

                try:
                    eligible, excluded, breakdown = self._build_universe_for_date(
                        session, month_end
                    )
                    total_eligible += eligible
                    total_excluded += excluded

                    # Aggregate breakdown
                    for reason, count in breakdown.items():
                        exclusion_breakdown[reason] = exclusion_breakdown.get(reason, 0) + count

                    session.commit()
                except Exception as e:
                    logger.error(f"Error building universe for {month_end}: {e}")
                    session.rollback()
                    continue

        stats = BuildStats(
            total_dates=len(month_ends),
            total_eligible=total_eligible,
            total_excluded=total_excluded,
            exclusion_breakdown=exclusion_breakdown,
        )

        logger.info(
            f"Universe build complete: {total_eligible:,} eligible, "
            f"{total_excluded:,} excluded across {len(month_ends)} dates"
        )

        return stats

    def _get_month_end_dates(self, from_date: date, to_date: date) -> list[date]:
        """Get all month-end dates in range that have price data.

        Returns list of last trading day of each month.
        """
        month_ends = []
        current = date(from_date.year, from_date.month, 1)

        while current <= to_date:
            # Get last day of month
            last_day = monthrange(current.year, current.month)[1]
            month_end = date(current.year, current.month, last_day)

            # Find last trading day (go backward up to 7 days to find a day with prices)
            with get_session() as session:
                for offset in range(8):
                    check_date = month_end - timedelta(days=offset)
                    if check_date < from_date:
                        break

                    # Check if this date has price data
                    result = session.execute(
                        select(func.count())
                        .select_from(StockPrice)
                        .where(StockPrice.date == check_date)
                    )
                    count = result.scalar()

                    if count and count > 0:
                        month_ends.append(check_date)
                        break

            # Move to next month
            if current.month == 12:
                current = date(current.year + 1, 1, 1)
            else:
                current = date(current.year, current.month + 1, 1)

        return month_ends

    def _build_universe_for_date(
        self, session: Session, as_of_date: date
    ) -> tuple[int, int, dict[str, int]]:
        """Build universe constituents for a specific date.

        Args:
            session: Database session
            as_of_date: Date to build universe for

        Returns:
            Tuple of (eligible_count, excluded_count, exclusion_breakdown)
        """
        logger.debug(f"Building universe for {as_of_date}")

        # Get all instruments with price data on this date
        instruments_query = (
            select(
                Instrument.ins_id,
                Instrument.stock_price_currency,
                Instrument.country_id,
                Instrument.market_id,
                Instrument.sector_id,
                Instrument.listing_date,
                StockPrice.close.label("price"),
            )
            .join(StockPrice, Instrument.ins_id == StockPrice.ins_id)
            .where(StockPrice.date == as_of_date)
        )

        result = session.execute(instruments_query)
        instruments = result.fetchall()

        logger.debug(f"Found {len(instruments)} instruments with price data")

        # Process each instrument
        universe_rows = []
        eligible_count = 0
        excluded_count = 0
        exclusion_breakdown: dict[str, int] = {}

        for ins in instruments:
            ins_id = ins.ins_id
            price = ins.price

            # Check listing date
            if ins.listing_date and ins.listing_date > as_of_date:
                excluded_count += 1
                exclusion_breakdown["not_listed_yet"] = (
                    exclusion_breakdown.get("not_listed_yet", 0) + 1
                )
                universe_rows.append(
                    self._create_universe_row(
                        ins_id, as_of_date, price, False, "not_listed_yet", None, None, None, None
                    )
                )
                continue

            # Excluded countries: skip the expensive calculations below
            if ins.country_id in self.config.exclude_country_ids:
                excluded_count += 1
                exclusion_breakdown["excluded_country"] = (
                    exclusion_breakdown.get("excluded_country", 0) + 1
                )
                universe_rows.append(
                    self._create_universe_row(
                        ins_id, as_of_date, price, False, "excluded_country", None, None, None, None
                    )
                )
                continue

            # Calculate market cap
            market_cap = self._calculate_market_cap(session, ins_id, as_of_date, price)

            # Calculate turnover
            median_turnover = self._calculate_median_turnover(session, ins_id, as_of_date)

            # Calculate history
            years_of_history = self._calculate_years_of_history(session, ins_id, as_of_date)

            # Apply minimal data quality filter
            # Philosophy: Include almost everything, strategies apply their own criteria
            is_eligible = True
            exclusion_reason = None

            # Only exclude extreme data quality issues
            exclusion_reason = self._exclusion_reason(ins.country_id, price)
            if exclusion_reason:
                is_eligible = False

            # Assign liquidity bucket (for cost modeling, not exclusion)
            liquidity_bucket = None
            if median_turnover:
                liquidity_bucket = self._assign_liquidity_bucket(median_turnover)

            # Update counts
            if is_eligible:
                eligible_count += 1
            else:
                excluded_count += 1
                if exclusion_reason:
                    # Simplify reason for aggregation
                    reason_type = (
                        exclusion_reason.split("_")[0] + "_" + exclusion_reason.split("_")[1]
                    )
                    if "too_low" in exclusion_reason or "insufficient" in exclusion_reason:
                        reason_type = exclusion_reason.rsplit("_", 1)[0]
                    exclusion_breakdown[reason_type] = exclusion_breakdown.get(reason_type, 0) + 1

            universe_rows.append(
                self._create_universe_row(
                    ins_id,
                    as_of_date,
                    price,
                    is_eligible,
                    exclusion_reason,
                    market_cap,
                    median_turnover,
                    years_of_history,
                    liquidity_bucket,
                )
            )

        # Batch insert in smaller chunks to avoid SQL query length limits
        if universe_rows:
            batch_size = 100  # Reduced to avoid parameter limits
            total = len(universe_rows)

            for i in range(0, total, batch_size):
                batch = universe_rows[i : i + batch_size]
                stmt = pg_insert(UniverseConstituent).values(batch)
                stmt = stmt.on_conflict_do_nothing(constraint="uq_universe_ins_date")
                session.execute(stmt)

                if total > batch_size and (i + batch_size) % 5000 == 0:
                    logger.debug(f"    Inserted {i + batch_size}/{total} rows for {as_of_date}")

        logger.debug(
            f"Universe for {as_of_date}: {eligible_count} eligible, {excluded_count} excluded"
        )

        return (eligible_count, excluded_count, exclusion_breakdown)

    def _exclusion_reason(self, country_id: int, price: Decimal | None) -> str | None:
        """Reason an instrument is not eligible, or None if eligible."""
        if country_id in self.config.exclude_country_ids:
            return "excluded_country"
        if price and price < Decimal(str(self.config.min_price)):
            return f"price_too_low_{price}"
        return None

    def _calculate_market_cap(
        self, _session: Session, ins_id: int, as_of_date: date, price: Decimal | None
    ) -> Decimal | None:
        """Calculate market cap using PIT share count.

        Args:
            session: Database session
            ins_id: Instrument ID
            as_of_date: Date to calculate for
            price: Current price

        Returns:
            Market cap in local currency (None if data missing)
        """
        if not price or price <= 0:
            return None

        # Get PIT share count (in millions)
        pit_df = as_of(as_of_date, instrument_ids=[ins_id], metrics=["number_of_shares"])

        if len(pit_df) == 0:
            return None

        # Get most recent share count
        shares_df = pit_df.filter(pit_df["metric"] == "number_of_shares").sort(
            "period_end", descending=True
        )

        if len(shares_df) == 0 or shares_df["value"][0] is None:
            return None

        shares_millions = Decimal(str(shares_df["value"][0]))
        market_cap = price * shares_millions * Decimal("1000000")  # Convert millions to actual

        return market_cap

    def _calculate_median_turnover(
        self, session: Session, ins_id: int, as_of_date: date
    ) -> Decimal | None:
        """Calculate 60-day median daily turnover.

        Args:
            session: Database session
            ins_id: Instrument ID
            as_of_date: Date to calculate for

        Returns:
            Median turnover in local currency (None if insufficient data)
        """
        # Get 60 trading days of turnover (price * volume)
        lookback_start = as_of_date - timedelta(days=90)  # Extra days to ensure 60 trading days

        query = text("""
            SELECT close * volume as turnover
            FROM stock_prices
            WHERE ins_id = :ins_id
              AND date <= :as_of_date
              AND date >= :lookback_start
              AND close IS NOT NULL
              AND volume IS NOT NULL
            ORDER BY date DESC
            LIMIT 60
        """)

        result = session.execute(
            query, {"ins_id": ins_id, "as_of_date": as_of_date, "lookback_start": lookback_start}
        )
        turnovers = [Decimal(str(row[0])) for row in result.fetchall()]

        if len(turnovers) < 40:  # Need at least 40 days
            return None

        # Calculate median
        sorted_turnovers = sorted(turnovers)
        n = len(sorted_turnovers)
        if n % 2 == 0:
            median = (sorted_turnovers[n // 2 - 1] + sorted_turnovers[n // 2]) / Decimal("2")
        else:
            median = sorted_turnovers[n // 2]

        return median

    def _calculate_years_of_history(
        self, session: Session, ins_id: int, as_of_date: date
    ) -> Decimal | None:
        """Calculate years of price history.

        Args:
            session: Database session
            ins_id: Instrument ID
            as_of_date: Date to calculate for

        Returns:
            Years of history (None if no data)
        """
        query = select(func.min(StockPrice.date)).where(StockPrice.ins_id == ins_id)
        result = session.execute(query)
        first_date = result.scalar()

        if not first_date:
            return None

        days_of_history = (as_of_date - first_date).days
        years = Decimal(str(days_of_history)) / Decimal("365.25")

        return years

    def _assign_liquidity_bucket(self, median_turnover: Decimal) -> int:
        """Assign liquidity bucket based on median turnover.

        Args:
            median_turnover: 60-day median daily turnover

        Returns:
            Liquidity bucket (1=most liquid, 5=least liquid)
        """
        thresholds = self.config.liquidity_bucket_thresholds

        for bucket, threshold in enumerate(thresholds, start=1):
            if median_turnover >= Decimal(str(threshold)):
                return bucket

        return 5  # Least liquid bucket

    def _create_universe_row(
        self,
        ins_id: int,
        as_of_date: date,
        price: Decimal | None,
        is_eligible: bool,
        exclusion_reason: str | None,
        market_cap: Decimal | None,
        median_turnover: Decimal | None,
        years_of_history: Decimal | None,
        liquidity_bucket: int | None,
    ) -> dict[str, Any]:
        """Create a universe constituent row dict.

        Args:
            All the universe metrics

        Returns:
            Dict ready for database insert
        """
        return {
            "instrument_id": ins_id,
            "date": as_of_date,
            "market_cap_local": market_cap,
            "median_turnover_60d": median_turnover,
            "price": price,
            "years_of_history": years_of_history,
            "is_eligible": is_eligible,
            "exclusion_reason": exclusion_reason,
            "liquidity_bucket": liquidity_bucket,
        }
