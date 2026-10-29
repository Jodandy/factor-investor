"""Trial registry table: one row per research backtest (CLAUDE.md invariant 5)."""

from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, Float, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from factor_investor.ingest.models import Base


class Trial(Base):
    """A research backtest: what was run, on which data and code, and the result.

    A row is written with status "running" before the backtest starts, so a
    run that crashes is still counted. Daily returns are stored in
    `returns_path` (Parquet) for PBO and CPCV.
    """

    __tablename__ = "trials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20))  # running, completed, failed
    error: Mapped[str | None] = mapped_column(Text)

    hypothesis_id: Mapped[str] = mapped_column(String(20))
    experiment: Mapped[str] = mapped_column(String(200))
    stage: Mapped[str] = mapped_column(String(50))

    strategy_id: Mapped[str] = mapped_column(String(200))
    strategy_source_hash: Mapped[str] = mapped_column(String(64))
    params: Mapped[dict[str, Any]] = mapped_column(JSONB)
    config_hash: Mapped[str] = mapped_column(String(64))
    area: Mapped[str] = mapped_column(String(10))
    from_date: Mapped[date] = mapped_column(Date)
    to_date: Mapped[date] = mapped_column(Date)
    cost_bps: Mapped[int] = mapped_column(Integer)
    gross: Mapped[bool] = mapped_column(Boolean)
    scenario: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # data scenario, e.g. bankruptcy

    price_filter: Mapped[str] = mapped_column(String(50))
    data_fingerprint: Mapped[dict[str, Any]] = mapped_column(JSONB)
    code_commit: Mapped[str] = mapped_column(String(40))
    code_dirty: Mapped[bool] = mapped_column(Boolean)

    final_value: Mapped[float | None] = mapped_column(Float)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    returns_path: Mapped[str | None] = mapped_column(String(500))

    __table_args__ = (
        Index("ix_trials_experiment", "experiment"),
        Index("ix_trials_hypothesis", "hypothesis_id"),
        Index("ix_trials_strategy", "strategy_id"),
        Index("ix_trials_config_hash", "config_hash"),
    )
