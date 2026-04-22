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


class PrAbsenceType(_TimestampMixin, Base):
    """Lookup table for absence declaration categories.

    Seeded at startup with the values defined in
    :class:`app.presence_app.constants.AbsenceType`. Rows can be added,
    renamed or deactivated without touching the schema.
    """

    __tablename__ = "pr_absence_type"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class PrLateReasonType(_TimestampMixin, Base):
    """Lookup table for late-declaration reason categories.

    Seeded at startup with the values defined in
    :class:`app.presence_app.constants.LateReasonType`.
    """

    __tablename__ = "pr_late_reason_type"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class AbsenceDeclaration(_TimestampMixin, Base):
    """Absence declaration filed by an employee.

    A declaration covers every calendar day in ``[date_debut, date_fin]``.
    ``date_fin`` is optional: when omitted the declaration only covers
    ``date_debut``. No approval workflow is involved — any recorded
    declaration justifies the covered days in the global statistics.
    """

    __tablename__ = "pr_absence_declaration"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user_management_user.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    absence_type_id: Mapped[int] = mapped_column(
        ForeignKey("pr_absence_type.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    date_debut: Mapped[_date] = mapped_column(Date, index=True, nullable=False)
    date_fin: Mapped[Optional[_date]] = mapped_column(Date, index=True, nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    justificatif_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    user: Mapped["User"] = relationship(
        "User", foreign_keys=[user_id], lazy="select"
    )
    absence_type: Mapped["PrAbsenceType"] = relationship(
        "PrAbsenceType", foreign_keys=[absence_type_id], lazy="select"
    )

    __table_args__ = (
        CheckConstraint(
            "date_fin IS NULL OR date_fin >= date_debut",
            name="ck_absence_decl_dates_ordre",
        ),
        Index("ix_pr_absence_decl_user_range", "user_id", "date_debut", "date_fin"),
    )


class LateDeclaration(_TimestampMixin, Base):
    """Late-arrival declaration filed by an employee for a given day.

    There is intentionally no status / reviewer: a declaration is a pure
    user-authored record and is taken into account as-is by the global
    statistics.
    """

    __tablename__ = "pr_late_declaration"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user_management_user.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    reason_type_id: Mapped[int] = mapped_column(
        ForeignKey("pr_late_reason_type.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    date_retard: Mapped[_date] = mapped_column(Date, index=True, nullable=False)
    expected_arrival_time: Mapped[Optional[_time]] = mapped_column(
        Time, nullable=True
    )
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship(
        "User", foreign_keys=[user_id], lazy="select"
    )
    reason_type: Mapped["PrLateReasonType"] = relationship(
        "PrLateReasonType", foreign_keys=[reason_type_id], lazy="select"
    )

    __table_args__ = (
        Index("ix_pr_late_decl_user_date", "user_id", "date_retard"),
    )