"""SQLAlchemy models for universe, dividends, and corporate events."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Double,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from factor_investor.ingest.models import Base


class Dividend(Base):
    """Dividend events with ex-dates.

    Each row represents a dividend payment for an instrument on a specific ex-date.
    Ex-dates can be actual (from Börsdata calendar API) or estimated from reports.
    """

    __tablename__ = "dividends"
    __table_args__ = (
        UniqueConstraint("instrument_id", "ex_date", name="uq_dividends_ins_ex"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instruments.ins_id"), nullable=False, index=True
    )
    ex_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    payment_date: Mapped[date | None] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(24, 6), nullable=False)  # Per share
    currency: Mapped[str | None] = mapped_column(String(10))
    is_estimated_ex_date: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    source: Mapped[str | None] = mapped_column(String(50))  # calendar_api, report_estimated, manual
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default="NOW()")

    # Note: Unique constraint (instrument_id, ex_date) is defined in migration


class TotalReturn(Base):
    """Total return series with reinvested dividends.

    Each row contains the daily total return index (base 100 on first date) for an instrument,
    calculated as cumulative price returns + reinvested dividends on ex-dates.
    """

    __tablename__ = "total_returns"
    __table_args__ = (
        UniqueConstraint("instrument_id", "date", name="uq_total_returns_ins_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instruments.ins_id"), nullable=False, index=True
    )
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    close_price: Mapped[Decimal] = mapped_column(
        Numeric(24, 6), nullable=False
    )  # In local currency
    # Cumulative, base 100. Double precision, not Numeric(24, 6): a fixed
    # number of decimals rounds the index of stocks that fell >99.9999% to zero
    # (DATA_AUDIT "Benchmark vs OMX Stockholm GI").
    total_return_index: Mapped[float] = mapped_column(Double, nullable=False)
    total_return_index_sek: Mapped[float | None] = mapped_column(Double)  # Converted to SEK
    dividend_on_date: Mapped[Decimal | None] = mapped_column(
        Numeric(24, 6)
    )  # Dividend paid today (if any)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default="NOW()")

    # Note: Unique constraint (instrument_id, date) is defined in migration


class UniverseConstituent(Base):
    """Universe membership per date.

    Each row represents an instrument's eligibility status for the investable universe
    on a specific date (typically month-end). Stores intermediate metrics for transparency
    and auditability.
    """

    __tablename__ = "universe_constituents"
    __table_args__ = (
        UniqueConstraint("instrument_id", "date", name="uq_universe_ins_date"),
        Index("ix_universe_date_eligible", "date", "is_eligible"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instruments.ins_id"), nullable=False, index=True
    )
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # Eligibility metrics (stored for transparency)
    market_cap_local: Mapped[Decimal | None] = mapped_column(
        Numeric(24, 2)
    )  # In instrument currency
    median_turnover_60d: Mapped[Decimal | None] = mapped_column(
        Numeric(24, 2)
    )  # 60-day median daily turnover
    price: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    years_of_history: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))

    # Inclusion status
    is_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    exclusion_reason: Mapped[str | None] = mapped_column(String(200))
    liquidity_bucket: Mapped[int | None] = mapped_column(Integer)  # 1-5 (1=most liquid)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default="NOW()")

    # Note: Unique constraint (instrument_id, date) is defined in migration
    # Note: Composite index (date, is_eligible) is defined in migration


class CorporateEvent(Base):
    """Corporate events (delistings, mergers, bankruptcies).

    Tracks major corporate events, primarily delistings detected via heuristics
    since Börsdata doesn't provide delisted companies.
    """

    __tablename__ = "corporate_events"
    __table_args__ = (
        UniqueConstraint("instrument_id", "event_date", "event_type", name="uq_events_ins_date_type"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instruments.ins_id"), nullable=False, index=True
    )
    event_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # delisting, listing, merger, bankruptcy
    detection_method: Mapped[str | None] = mapped_column(
        String(100)
    )  # missing_prices, market_change, manual
    final_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))  # Last traded price
    recovery_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))  # 0.0-1.0 for bankruptcy
    notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default="NOW()")

    # Note: Unique constraint (instrument_id, event_date, event_type) is defined in migration
