"""SQLAlchemy models for the presence/attendance module.

These tables are additive and do not modify any existing table. The
``users`` table (``user_management_user``) is referenced only through
``user_id`` foreign keys.
"""
from __future__ import annotations

from datetime import date as _date
from datetime import datetime
from datetime import time as _time
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.user_app.models import User


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

    user: Mapped["User"] = relationship("User", lazy="select")

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

    user: Mapped[Optional["User"]] = relationship("User", lazy="select")


class AbsenceDeclaration(_TimestampMixin, Base):
    """Absence declaration filed by an employee.

    An approved declaration justifies the absence of the user for every
    calendar day in the ``[date_debut, date_fin]`` range. The declaration
    is intentionally decoupled from :class:`Presence`: if a user scans
    during the declared range the declaration remains valid and is simply
    no longer used to justify that particular day.
    """

    __tablename__ = "pr_absence_declaration"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user_management_user.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    date_debut: Mapped[_date] = mapped_column(Date, index=True, nullable=False)
    date_fin: Mapped[_date] = mapped_column(Date, index=True, nullable=False)
    absence_type: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), default="PENDING", nullable=False, index=True
    )
    justificatif_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    reviewed_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("user_management_user.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    review_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship(
        "User", foreign_keys=[user_id], lazy="select"
    )
    reviewed_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[reviewed_by_id], lazy="select"
    )

    __table_args__ = (
        CheckConstraint("date_fin >= date_debut", name="ck_absence_decl_dates_ordre"),
        Index("ix_pr_absence_decl_user_range", "user_id", "date_debut", "date_fin"),
    )


class LateDeclaration(_TimestampMixin, Base):
    """Late-arrival declaration filed by an employee for a given day."""

    __tablename__ = "pr_late_declaration"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user_management_user.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    date_retard: Mapped[_date] = mapped_column(Date, index=True, nullable=False)
    expected_arrival_time: Mapped[Optional[_time]] = mapped_column(
        Time, nullable=True
    )
    reason_type: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), default="PENDING", nullable=False, index=True
    )

    reviewed_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("user_management_user.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    review_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship(
        "User", foreign_keys=[user_id], lazy="select"
    )
    reviewed_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[reviewed_by_id], lazy="select"
    )

    __table_args__ = (
        Index("ix_pr_late_decl_user_date", "user_id", "date_retard"),
    )