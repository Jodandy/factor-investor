"""Service for extracting dividends from reports and building total return series."""

import logging
from bisect import bisect_left
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from factor_investor.db import get_session
from factor_investor.ingest.models import StockPrice
from factor_investor.pit.service import PITService
from factor_investor.universe.models import Dividend, TotalReturn

logger = logging.getLogger(__name__)


def compute_total_return_index(
    prices: list[tuple[date, Decimal | None]],
    dividends: list[tuple[date, Decimal]],
) -> list[dict]:
    """Build a total return index (base 100) with reinvested dividends.

    TR[t] = TR[t-1] * (price[t] + div[t]) / price[t-1]

    A dividend is applied on the first trading day on or after its ex-date
    (estimated ex-dates often fall on weekends or holidays). Dividends on the
    same trading day are summed. Invalid prices (None or <= 0) are skipped.

    Args:
        prices: (date, close) sorted by date
        dividends: (ex_date, amount per share)

    Returns:
        Rows with date, close_price, total_return_index,
        total_return_index_sek (None), dividend_on_date
    """
    valid = [(d, p) for d, p in prices if p is not None and p > 0]
    trading_days = [d for d, _ in valid]

    div_on_day: dict[date, Decimal] = {}
    for ex_date, amount in dividends:
        idx = bisect_left(trading_days, ex_date)
        if idx < len(trading_days):
            day = trading_days[idx]
            div_on_day[day] = div_on_day.get(day, Decimal("0")) + amount

    rows = []
    tr_index = Decimal("100.0")
    prev_price: Decimal | None = None
    for trade_date, close_price in valid:
        dividend = div_on_day.get(trade_date, Decimal("0"))
        if prev_price is not None:
            tr_index = tr_index * (close_price + dividend) / prev_price
        prev_price = close_price
        rows.append(
            {
                "date": trade_date,
                "close_price": close_price,
                "total_return_index": tr_index,
                "total_return_index_sek": None,  # Will be filled by FX service later
                "dividend_on_date": dividend if dividend > 0 else None,
            }
        )
    return rows


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
        self.estimation_lag_days = 30  # known_from + 30 days for estimated ex-date
        self.pit_service = PITService()

    def estimate_ex_date(self, report_date: date | None, period_end: date) -> date:
        """Estimate ex-date as the report's known_from + 30 days.

        Uses the PIT layer's known_from, so placeholder or missing publication
        dates fall back to the same conservative delay: a dividend is never
        paid before the report announcing it could have been known.
        """
        known_from, _ = self.pit_service.calculate_known_from(report_date, period_end, "year")
        return known_from + timedelta(days=self.estimation_lag_days)

    def extract_dividends_from_reports(self) -> int:
        """Extract dividends from annual reports and estimate ex-dates.

        Replaces all previously estimated dividends (source 'report_estimated')
        so the extraction is idempotent and picks up rule changes.

        Known limitation: one dividend per fiscal year at the estimated date,
        so companies paying quarterly get their year's dividends lumped.

        Returns:
            Number of dividends extracted and inserted
        """
        logger.info("Extracting dividends from reports...")

        with get_session() as session:
            session.execute(delete(Dividend).where(Dividend.source == "report_estimated"))

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
                ORDER BY r.ins_id, r.report_end_date
            """)

            result = session.execute(query)
            rows = result.fetchall()

            dividends = []
            for row in rows:
                ins_id, period_end, report_date, div_amount, currency = row

                ex_date = self.estimate_ex_date(report_date, period_end)

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

        tr_rows = [
            {"instrument_id": ins_id, **row}
            for row in compute_total_return_index(
                [(row[0], row[1]) for row in price_rows], dividends
            )
        ]
        has_dividends = any(row["dividend_on_date"] is not None for row in tr_rows)

        # Batch insert
        if tr_rows:
            stmt = pg_insert(TotalReturn).values(tr_rows)
            stmt = stmt.on_conflict_do_nothing(constraint="uq_total_returns_ins_date")
            session.execute(stmt)

        return (len(tr_rows), has_dividends)
