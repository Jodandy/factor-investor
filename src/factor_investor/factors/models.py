"""SQLAlchemy models for factor base metrics."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from factor_investor.ingest.models import Base


class FundamentalMetric(Base):
    """Fundamental base metrics (P/E, P/B, ROIC, etc.).

    Each row represents a fundamental metric value for an instrument on a specific date
    (typically month-end rebalancing dates). Includes both valuation metrics calculated
    from price + PIT fundamentals, and references to PIT-calculated metrics like ROIC.
    """

    __tablename__ = "fundamental_metrics"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instruments.ins_id"), nullable=False
    )
    metric: Mapped[str] = mapped_column(String(100), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    value: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    known_from: Mapped[date] = mapped_column(
        Date, nullable=False
    )  # Latest PIT report date used
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default="NOW()")

    __table_args__ = (
        UniqueConstraint("instrument_id", "metric", "date", name="uq_fundamental_metrics"),
        Index("ix_fundamental_metrics_ins_id", "instrument_id"),
        Index("ix_fundamental_metrics_metric", "metric"),
        Index("ix_fundamental_metrics_date", "date"),
    )


class PriceMetric(Base):
    """Price-derived base metrics (returns, volatility, momentum, etc.).

    Each row represents a price metric value for an instrument on a specific date
    (typically month-end rebalancing dates). Calculated from historical price data only,
    no PIT fundamentals needed.
    """

    __tablename__ = "price_metrics"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instruments.ins_id"), nullable=False
    )
    metric: Mapped[str] = mapped_column(String(100), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    value: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default="NOW()")

    __table_args__ = (
        UniqueConstraint("instrument_id", "metric", "date", name="uq_price_metrics"),
        Index("ix_price_metrics_ins_id", "instrument_id"),
        Index("ix_price_metrics_metric", "metric"),
        Index("ix_price_metrics_date", "date"),
    )
