"""SQLAlchemy models for point-in-time fundamentals storage."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from factor_investor.ingest.models import Base


class FundamentalPIT(Base):
    """Point-in-time fundamental metric values.

    Each row represents a single metric value for an instrument's reporting period,
    along with the date when that value became known to the market (publication date + buffer).

    This enables lookahead-free historical queries: get all metrics as of date D using
    only values with known_from <= D.

    The schema supports multiple versions of the same (instrument, metric, period) with
    different known_from dates to handle restatements (though Börsdata doesn't provide these).
    """

    __tablename__ = "fundamentals_pit"
    __table_args__ = (
        UniqueConstraint(
            "instrument_id", "metric", "period_end", "period_type", "known_from",
            name="uq_fundamentals_pit",
        ),
        Index(
            "ix_fundamentals_pit_as_of",
            "instrument_id", "metric", "known_from", text("period_end DESC"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instruments.ins_id"), nullable=False, index=True
    )
    metric: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    period_end: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    period_type: Mapped[str] = mapped_column(String(10), nullable=False)  # 'year', 'quarter', 'r12'
    value: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    known_from: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("NOW()")
    )

