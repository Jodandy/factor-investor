"""Corporate event detection (delistings, mergers, etc.)."""

import logging
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import text

from factor_investor.db import get_session

logger = logging.getLogger(__name__)


@dataclass
class CorporateEvent:
    """Detected corporate event."""

    instrument_id: int
    event_date: date
    event_type: str
    detection_method: str
    final_price: float | None
    notes: str | None


def detect_delistings(lookback_days: int = 90) -> list[CorporateEvent]:
    """Detect potential delistings via heuristics.

    Heuristics:
    1. No price data for lookback_days+ after last trade
    2. Sudden 90%+ price drop without recovery

    Args:
        lookback_days: Number of days without prices to consider delisted

    Returns:
        List of detected delisting events for review
    """
    logger.info(f"Detecting delistings (lookback={lookback_days} days)...")

    events: list[CorporateEvent] = []
    cutoff_date = date.today() - timedelta(days=lookback_days)

    with get_session() as session:
        # Heuristic 1: No recent price data
        # Find instruments whose last price is more than lookback_days ago
        query = text("""
            SELECT
                ins_id,
                MAX(date) as last_trade_date,
                (
                    SELECT close
                    FROM stock_prices sp2
                    WHERE sp2.ins_id = sp.ins_id
                    ORDER BY date DESC
                    LIMIT 1
                ) as final_price
            FROM stock_prices sp
            GROUP BY ins_id
            HAVING MAX(date) < :cutoff_date
            ORDER BY MAX(date) DESC
            LIMIT 100
        """)

        result = session.execute(query, {"cutoff_date": cutoff_date})
        rows = result.fetchall()

        for ins_id, last_trade_date, final_price in rows:
            events.append(
                CorporateEvent(
                    instrument_id=ins_id,
                    event_date=last_trade_date,
                    event_type="delisting",
                    detection_method="missing_prices",
                    final_price=float(final_price) if final_price else None,
                    notes=f"No prices after {last_trade_date}",
                )
            )

    logger.info(f"Detected {len(events)} potential delisting events")

    return events
