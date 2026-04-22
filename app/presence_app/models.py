"""SQLAlchemy models for the presence/attendance module.

These tables are additive and do not modify any existing table. The
``users`` table (``user_management_user``) is referenced only through
``user_id`` foreign keys.
"""
from __future__ import annotations

from datetime import date as _date
from datetime import datetime
from datetime import time as _time
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class _TimestampMixin:
    """Standard ``created_at`` / ``updated_at`` columns."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class Presence(_TimestampMixin, Base):
    """A single ENTRY or EXIT scan for a user on a given day."""

    __tablename__ = "pr_presence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user_management_user.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    date_scan: Mapped[_date] = mapped_column(Date, index=True, nullable=False)
    heure_scan: Mapped[_time] = mapped_column(Time, nullable=False)
    method: Mapped[str] = mapped_column(String(32), nullable=False)
    scan_type: Mapped[str] = mapped_column(String(16), nullable=False)
    is_late: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "user_id", "date_scan", "scan_type", name="uq_presence_user_day_type"
        ),
        Index("ix_pr_presence_user_date", "user_id", "date_scan"),
    )


class WorkSchedule(_TimestampMixin, Base):
    """Work schedule defining start/end hours.

    When ``user_id`` is ``NULL`` the row is treated as the global default
    schedule applied to every user without a personal schedule. When
    ``user_id`` is set the row overrides the default for that user.
    """

    __tablename__ = "pr_work_schedule"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("user_management_user.id", ondelete="CASCADE"),
        index=True,
        unique=True,
        nullable=True,
    )
    start_time: Mapped[_time] = mapped_column(Time, nullable=False)
    end_time: Mapped[_time] = mapped_column(Time, nullable=False)
    break_start: Mapped[Optional[_time]] = mapped_column(Time, nullable=True)
    break_end: Mapped[Optional[_time]] = mapped_column(Time, nullable=True)