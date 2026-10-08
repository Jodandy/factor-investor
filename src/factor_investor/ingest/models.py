"""SQLAlchemy models for raw data storage from Börsdata."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


# --- Metadata tables ---


class Country(Base):
    """Country reference table."""

    __tablename__ = "countries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    instruments: Mapped[list["Instrument"]] = relationship(back_populates="country")


class Market(Base):
    """Market/exchange reference table."""

    __tablename__ = "markets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    country_id: Mapped[int] = mapped_column(Integer, ForeignKey("countries.id"), nullable=False)
    exchange_name: Mapped[str | None] = mapped_column(String(100))
    is_index: Mapped[bool] = mapped_column(Boolean, default=False)

    country: Mapped["Country"] = relationship()
    instruments: Mapped[list["Instrument"]] = relationship(back_populates="market")


class Sector(Base):
    """Sector reference table."""

    __tablename__ = "sectors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    branches: Mapped[list["Branch"]] = relationship(back_populates="sector")
    instruments: Mapped[list["Instrument"]] = relationship(back_populates="sector")


class Branch(Base):
    """Branch/industry reference table."""

    __tablename__ = "branches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sector_id: Mapped[int] = mapped_column(Integer, ForeignKey("sectors.id"), nullable=False)

    sector: Mapped["Sector"] = relationship(back_populates="branches")
    instruments: Mapped[list["Instrument"]] = relationship(back_populates="branch")


# --- Core data tables ---


class Instrument(Base):
    """Instrument (stock, index, etc.) master table."""

    __tablename__ = "instruments"

    ins_id: Mapped[int] = mapped_column(Integer, primary_key=True)  # Börsdata's ID
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    ticker: Mapped[str | None] = mapped_column(String(50))
    isin: Mapped[str | None] = mapped_column(String(20))
    yahoo: Mapped[str | None] = mapped_column(String(50))
    url_name: Mapped[str | None] = mapped_column(String(200))

    instrument_type: Mapped[int] = mapped_column(Integer, default=0)  # 0=stock, etc.
    country_id: Mapped[int] = mapped_column(Integer, ForeignKey("countries.id"), nullable=False)
    market_id: Mapped[int] = mapped_column(Integer, ForeignKey("markets.id"), nullable=False)
    sector_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("sectors.id"))
    branch_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("branches.id"))

    listing_date: Mapped[date | None] = mapped_column(Date)
    stock_price_currency: Mapped[str | None] = mapped_column(String(10))
    report_currency: Mapped[str | None] = mapped_column(String(10))

    # Sync metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    country: Mapped["Country"] = relationship(back_populates="instruments")
    market: Mapped["Market"] = relationship(back_populates="instruments")
    sector: Mapped["Sector | None"] = relationship(back_populates="instruments")
    branch: Mapped["Branch | None"] = relationship(back_populates="instruments")
    prices: Mapped[list["StockPrice"]] = relationship(back_populates="instrument")
    reports_year: Mapped[list["ReportYear"]] = relationship(back_populates="instrument")
    reports_quarter: Mapped[list["ReportQuarter"]] = relationship(back_populates="instrument")
    reports_r12: Mapped[list["ReportR12"]] = relationship(back_populates="instrument")
    splits: Mapped[list["StockSplit"]] = relationship(back_populates="instrument")

    __table_args__ = (
        Index("ix_instruments_country", "country_id"),
        Index("ix_instruments_market", "market_id"),
        Index("ix_instruments_ticker", "ticker"),
        Index("ix_instruments_isin", "isin"),
    )


class StockPrice(Base):
    """Daily stock prices (OHLCV)."""

    __tablename__ = "stock_prices"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ins_id: Mapped[int] = mapped_column(Integer, ForeignKey("instruments.ins_id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)

    open: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    high: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    low: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    close: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    volume: Mapped[int | None] = mapped_column(BigInteger)

    instrument: Mapped["Instrument"] = relationship(back_populates="prices")

    __table_args__ = (
        UniqueConstraint("ins_id", "date", name="uq_stock_prices_ins_date"),
        Index("ix_stock_prices_ins_date", "ins_id", "date"),
        Index("ix_stock_prices_date", "date"),
    )


class StockSplit(Base):
    """Stock split events."""

    __tablename__ = "stock_splits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ins_id: Mapped[int] = mapped_column(Integer, ForeignKey("instruments.ins_id"), nullable=False)
    split_date: Mapped[date] = mapped_column(Date, nullable=False)
    split_type: Mapped[str] = mapped_column(String(10))  # S=split, RS=reverse split
    ratio: Mapped[str] = mapped_column(String(20))  # e.g., "2:1", "1:10"

    instrument: Mapped["Instrument"] = relationship(back_populates="splits")

    __table_args__ = (
        UniqueConstraint("ins_id", "split_date", name="uq_stock_splits_ins_date"),
        Index("ix_stock_splits_date", "split_date"),
    )


# --- Report tables ---
# Using separate tables for year/quarter/r12 for clarity and performance


class ReportYear(Base):
    """Annual financial reports."""

    __tablename__ = "reports_year"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ins_id: Mapped[int] = mapped_column(Integer, ForeignKey("instruments.ins_id"), nullable=False)

    year: Mapped[int] = mapped_column(Integer, nullable=False)
    period: Mapped[int | None] = mapped_column(Integer)  # Börsdata period indicator
    report_start_date: Mapped[date | None] = mapped_column(Date)
    report_end_date: Mapped[date | None] = mapped_column(Date)
    report_date: Mapped[date | None] = mapped_column(Date)  # Publication date - critical for PIT!
    broken_fiscal_year: Mapped[bool | None] = mapped_column(Boolean, default=False)
    currency: Mapped[str | None] = mapped_column(String(10))
    currency_ratio: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))

    # Income statement
    revenues: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    net_sales: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    gross_income: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    operating_income: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    profit_before_tax: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    profit_to_equity_holders: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    earnings_per_share: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))

    # Balance sheet
    intangible_assets: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    tangible_assets: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    financial_assets: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    non_current_assets: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    cash_and_equivalents: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    current_assets: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    total_assets: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    total_equity: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    non_current_liabilities: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    current_liabilities: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    total_liabilities_and_equity: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    net_debt: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))

    # Cash flow
    cash_flow_from_operating_activities: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    cash_flow_from_investing_activities: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    cash_flow_from_financing_activities: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    cash_flow_for_the_year: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    free_cash_flow: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))

    # Share data
    number_of_shares: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))  # In millions
    dividend: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))

    # Price data at report time
    stock_price_average: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    stock_price_high: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    stock_price_low: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))

    instrument: Mapped["Instrument"] = relationship(back_populates="reports_year")

    __table_args__ = (
        UniqueConstraint("ins_id", "year", "period", name="uq_reports_year_ins_year"),
        Index("ix_reports_year_ins_id", "ins_id"),
        Index("ix_reports_year_report_date", "report_date"),
    )


class ReportQuarter(Base):
    """Quarterly financial reports."""

    __tablename__ = "reports_quarter"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ins_id: Mapped[int] = mapped_column(Integer, ForeignKey("instruments.ins_id"), nullable=False)

    year: Mapped[int] = mapped_column(Integer, nullable=False)
    period: Mapped[int] = mapped_column(Integer, nullable=False)  # Quarter 1-4
    report_start_date: Mapped[date | None] = mapped_column(Date)
    report_end_date: Mapped[date | None] = mapped_column(Date)
    report_date: Mapped[date | None] = mapped_column(Date)  # Publication date
    currency: Mapped[str | None] = mapped_column(String(10))
    currency_ratio: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))

    # Income statement (same fields as year)
    revenues: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    net_sales: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    gross_income: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    operating_income: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    profit_before_tax: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    profit_to_equity_holders: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    earnings_per_share: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))

    # Balance sheet
    intangible_assets: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    tangible_assets: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    financial_assets: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    non_current_assets: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    cash_and_equivalents: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    current_assets: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    total_assets: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    total_equity: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    non_current_liabilities: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    current_liabilities: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    total_liabilities_and_equity: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    net_debt: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))

    # Cash flow
    cash_flow_from_operating_activities: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    cash_flow_from_investing_activities: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    cash_flow_from_financing_activities: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    cash_flow_for_the_year: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    free_cash_flow: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))

    # Share data
    number_of_shares: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    dividend: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))

    instrument: Mapped["Instrument"] = relationship(back_populates="reports_quarter")

    __table_args__ = (
        UniqueConstraint("ins_id", "year", "period", name="uq_reports_quarter_ins_year_period"),
        Index("ix_reports_quarter_ins_id", "ins_id"),
        Index("ix_reports_quarter_report_date", "report_date"),
    )


class ReportR12(Base):
    """Rolling 12-month (R12) financial reports."""

    __tablename__ = "reports_r12"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ins_id: Mapped[int] = mapped_column(Integer, ForeignKey("instruments.ins_id"), nullable=False)

    year: Mapped[int] = mapped_column(Integer, nullable=False)
    period: Mapped[int] = mapped_column(Integer, nullable=False)
    report_start_date: Mapped[date | None] = mapped_column(Date)
    report_end_date: Mapped[date | None] = mapped_column(Date)
    report_date: Mapped[date | None] = mapped_column(Date)
    currency: Mapped[str | None] = mapped_column(String(10))
    currency_ratio: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))

    # Same financial fields as quarterly (R12 is cumulative)
    revenues: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    net_sales: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    gross_income: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    operating_income: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    profit_before_tax: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    profit_to_equity_holders: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    earnings_per_share: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))

    intangible_assets: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    tangible_assets: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    financial_assets: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    non_current_assets: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    cash_and_equivalents: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    current_assets: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    total_assets: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    total_equity: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    non_current_liabilities: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    current_liabilities: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    total_liabilities_and_equity: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    net_debt: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))

    cash_flow_from_operating_activities: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    cash_flow_from_investing_activities: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    cash_flow_from_financing_activities: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    cash_flow_for_the_year: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))
    free_cash_flow: Mapped[Decimal | None] = mapped_column(Numeric(24, 2))

    number_of_shares: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    dividend: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))

    instrument: Mapped["Instrument"] = relationship(back_populates="reports_r12")

    __table_args__ = (
        UniqueConstraint("ins_id", "year", "period", name="uq_reports_r12_ins_year_period"),
        Index("ix_reports_r12_ins_id", "ins_id"),
        Index("ix_reports_r12_report_date", "report_date"),
    )


# --- Sync tracking ---


class SyncLog(Base):
    """Track sync operations for idempotency and incremental updates."""

    __tablename__ = "sync_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sync_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # instruments, prices, reports
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default="running")  # running, completed, failed
    records_processed: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (Index("ix_sync_log_type_started", "sync_type", "started_at"),)


class InstrumentSyncStatus(Base):
    """Track sync status per instrument for resumable syncs."""

    __tablename__ = "instrument_sync_status"

    ins_id: Mapped[int] = mapped_column(Integer, ForeignKey("instruments.ins_id"), primary_key=True)
    sync_type: Mapped[str] = mapped_column(String(20), primary_key=True)  # reports, prices
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, completed, failed
    error_message: Mapped[str | None] = mapped_column(Text)
    records_synced: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (Index("ix_instrument_sync_status_type_status", "sync_type", "status"),)
