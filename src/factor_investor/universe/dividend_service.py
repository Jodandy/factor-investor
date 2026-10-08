"""Service for extracting dividends from reports and building total return series."""

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from factor_investor.db import get_session
from factor_investor.ingest.models import StockPrice
from factor_investor.universe.models import Dividend, TotalReturn

logger = logging.getLogger(__name__)


@dataclass
class BuildStats:
    """Statistics from total return build operation."""

    total_instruments: int
    dividends_extracted: int
    total_returns_calculated: int
    instruments_with_dividends: int
    instruments_skipped: int = 0


class DividendService:
    """Service for extracting dividends from reports and building total return series."""

    def __init__(self) -> None:
        """Initialize dividend service."""
        self.estimation_lag_days = 30  # report_date + 30 days for estimated ex-date

    def extract_dividends_from_reports(self) -> int:
        """Extract dividends from reports and estimate ex-dates.

        Reads dividend amounts from annual reports and estimates ex-date as
        report_date + 30 days (typical Nordic pattern from report to ex-date).

        Returns:
            Number of dividends extracted and inserted
        """
        logger.info("Extracting dividends from reports...")

        with get_session() as session:
            # Get annual dividends from reports
            query = text("""
                SELECT
                    r.ins_id,
                    r.report_end_date,
                    r.report_date,
                    r.dividend,
                    i.stock_price_currency as currency
                FROM reports_year r
                JOIN instruments i ON r.ins_id = i.ins_id
                WHERE r.dividend IS NOT NULL AND r.dividend > 0
                  AND r.report_date IS NOT NULL
                  AND r.report_date >= '2015-01-01'
                  AND NOT EXISTS (
                      SELECT 1 FROM dividends d
                      WHERE d.instrument_id = r.ins_id
                        AND d.ex_date BETWEEN r.report_date AND r.report_date + INTERVAL '90 days'
                  )
                ORDER BY r.ins_id, r.report_end_date
            """)

            result = session.execute(query)
            rows = result.fetchall()

            dividends = []
            for row in rows:
                ins_id, _period_end, report_date, div_amount, currency = row

                # Estimate ex-date as report_date + 30 days
                ex_date = report_date + timedelta(days=self.estimation_lag_days)

                dividends.append(
                    {
                        "instrument_id": ins_id,
                        "ex_date": ex_date,
                        "payment_date": None,
                        "amount": Decimal(str(div_amount)),
                        "currency": currency,
                        "is_estimated_ex_date": True,
                        "source": "report_estimated",
                    }
                )

            if dividends:
                count = len(dividends)
                logger.info(f"Inserting {count:,} dividends in batches...")

                # Insert in batches to avoid SQL query length limits
                batch_size = 100  # Reduced to avoid parameter limits
                for i in range(0, len(dividends), batch_size):
                    batch = dividends[i : i + batch_size]
                    stmt = pg_insert(Dividend).values(batch)
                    stmt = stmt.on_conflict_do_nothing(constraint="uq_dividends_ins_ex")
                    session.execute(stmt)

                    if (i + batch_size) % 10000 == 0:
                        logger.info(f"  Inserted {i + batch_size:,}/{count:,} dividends")

                session.commit()
                logger.info(f"Extracted {count:,} dividends from reports")
                return count

        return 0

    def build_total_returns(
        self, instrument_ids: list[int] | None = None, force_rebuild: bool = False
    ) -> BuildStats:
        """Build total return series with reinvested dividends.

        Process:
        1. Extract dividends from reports (if not already done)
        2. Get daily prices from stock_prices
        3. Get dividends from dividends table
        4. Calculate cumulative TR index: TR[t] = TR[t-1] * (price[t] + div[t]) / price[t-1]
        5. Insert into total_returns table

        Args:
            instrument_ids: List of instrument IDs to build (None = all with price data)
            force_rebuild: If True, delete existing data and rebuild

        Returns:
            Statistics from build operation
        """
        logger.info("Starting total return series build...")

        # First, extract dividends from reports
        dividends_extracted = self.extract_dividends_from_reports()

        # Pre-load ALL dividends into memory for fast lookup (optimization)
        logger.info("Pre-loading dividends into memory for fast lookup...")
        with get_session() as div_session:
            all_divs_query = select(Dividend.instrument_id, Dividend.ex_date, Dividend.amount)
            div_result = div_session.execute(all_divs_query)

            # Build dict: instrument_id -> list of (ex_date, amount)
            dividends_by_instrument: dict[int, list[tuple[date, Decimal]]] = {}
            for ins_id, ex_date, amount in div_result:
                if ins_id not in dividends_by_instrument:
                    dividends_by_instrument[ins_id] = []
                dividends_by_instrument[ins_id].append((ex_date, amount))

            logger.info(f"Pre-loaded dividends for {len(dividends_by_instrument):,} instruments")

        with get_session() as session:
            # Get list of instruments to process
            if instrument_ids is None:
                result = session.execute(
                    text("SELECT DISTINCT ins_id FROM stock_prices ORDER BY ins_id")
                )
                instrument_ids = [row[0] for row in result.fetchall()]

            total_instruments = len(instrument_ids)
            logger.info(f"Building total returns for {total_instruments:,} instruments")

            if force_rebuild:
                logger.warning("Force rebuild: deleting existing total returns...")
                session.execute(delete(TotalReturn))
                session.commit()

            total_returns_calculated = 0
            instruments_with_dividends = 0
            instruments_skipped = 0

            # Process in larger batches for better performance
            batch_size = 500

            for idx, ins_id in enumerate(instrument_ids):
                if (idx + 1) % batch_size == 0:
                    logger.info(
                        f"  Progress: {idx + 1:,}/{total_instruments:,} instruments processed"
                    )

                try:
                    # Get dividends for this instrument from pre-loaded dict
                    instrument_divs = dividends_by_instrument.get(ins_id, [])

                    # Calculate TR for this instrument
                    tr_count, has_divs = self._calculate_total_return_for_instrument(
                        session, ins_id, instrument_divs
                    )
                    total_returns_calculated += tr_count
                    if has_divs:
                        instruments_with_dividends += 1
                except Exception as e:
                    logger.error(f"Error calculating TR for instrument {ins_id}: {e}")
                    instruments_skipped += 1
                    session.rollback()  # Rollback this instrument, continue with next
                    continue

                # Commit in batches to avoid massive transactions
                if (idx + 1) % batch_size == 0:
                    session.commit()
                    logger.info(f"  Committed batch up to instrument {idx + 1}")

            # Final commit for remaining instruments
            session.commit()

        stats = BuildStats(
            total_instruments=total_instruments,
            dividends_extracted=dividends_extracted,
            total_returns_calculated=total_returns_calculated,
            instruments_with_dividends=instruments_with_dividends,
            instruments_skipped=instruments_skipped,
        )

        logger.info(
            f"Total return build complete: {total_returns_calculated:,} rows calculated "
            f"for {total_instruments:,} instruments "
            f"({instruments_with_dividends:,} with dividends, {dividends_extracted:,} dividends extracted)"
        )

        return stats

    def _calculate_total_return_for_instrument(
        self, session: Session, ins_id: int, dividends: list[tuple[date, Decimal]]
    ) -> tuple[int, bool]:
        """Calculate total return series for a single instrument.

        Args:
            session: Database session
            ins_id: Instrument ID
            dividends: Pre-loaded list of (ex_date, amount) tuples for this instrument

        Returns:
            Tuple of (number of TR rows calculated, has_dividends)
        """
        # Get prices
        prices_query = (
            select(StockPrice.date, StockPrice.close)
            .where(StockPrice.ins_id == ins_id)
            .order_by(StockPrice.date)
        )
        price_result = session.execute(prices_query)
        price_rows = price_result.fetchall()

        if not price_rows:
            return (0, False)

        # Create dividend lookup dict from pre-loaded data
        div_dict: dict[date, Decimal] = {}
        for ex_date, amount in dividends:
            div_dict[ex_date] = amount

        has_dividends = len(div_dict) > 0

        # Calculate TR index
        tr_rows = []
        tr_index = Decimal("100.0")  # Base 100 on first date

        for i, (trade_date, close_price) in enumerate(price_rows):
            if close_price is None or close_price <= 0:
                continue  # Skip invalid prices

            dividend = div_dict.get(trade_date, Decimal("0"))

            if i == 0:
                # First date: base index = 100
                tr_index = Decimal("100.0")
            else:
                # Calculate return: (price[t] + div[t]) / price[t-1]
                prev_price = price_rows[i - 1][1]
                if prev_price and prev_price > 0:
                    total_return = (close_price + dividend) / prev_price
                    tr_index = tr_index * total_return
                else:
                    # Can't calculate if previous price is missing/invalid
                    continue

            tr_rows.append(
                {
                    "instrument_id": ins_id,
                    "date": trade_date,
                    "close_price": close_price,
                    "total_return_index": tr_index,
                    "total_return_index_sek": None,  # Will be filled by FX service later
                    "dividend_on_date": dividend if dividend > 0 else None,
                }
            )

        # Batch insert
        if tr_rows:
            stmt = pg_insert(TotalReturn).values(tr_rows)
            stmt = stmt.on_conflict_do_nothing(constraint="uq_total_returns_ins_date")
            session.execute(stmt)

        return (len(tr_rows), has_dividends)
