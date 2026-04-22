"""Pydantic schemas for the presence/attendance module."""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.presence_app.constants import ScanMethod, ScanType


# ---------------------------------------------------------------------------
# Nested user summary (lightweight User representation used when expanding)
# ---------------------------------------------------------------------------


class UserSummary(BaseModel):
    """Minimal user payload returned whenever a presence endpoint exposes a
    related user. It is intentionally decoupled from :class:`UserResponse` in
    ``user_app.schemas`` to avoid circular imports and to give the caller only
    the fields they need. Additional relations can still be loaded via the
    ``expand`` query parameter on each endpoint.
    """

    id: int
    email: Optional[str] = None
    nom: Optional[str] = None
    prenom: Optional[str] = None
    phone: Optional[str] = None
    photo: Optional[str] = None
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None
    is_staff: Optional[bool] = None
    employe_id: Optional[int] = None

    # Free-form nested relations populated by SQLAlchemy when the caller uses
    # ``expand=user.employe`` (or similar). We expose them as generic ``Any``
    # to keep this schema light while still letting the serializer include
    # eagerly loaded relationships.
    employe: Optional[Any] = None
    user_groups: Optional[list[Any]] = None

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Presence
# ---------------------------------------------------------------------------


class PresenceResponse(BaseModel):
    id: int
    user_id: int
    date_scan: date
    heure_scan: time
    method: ScanMethod
    scan_type: ScanType
    is_late: bool
    created_at: datetime
    updated_at: datetime

    # Populated when the caller adds ``expand=user`` (or nested paths such as
    # ``expand=user.employe``). Always optional so non-expanded responses stay
    # small.
    user: Optional[UserSummary] = None

    model_config = ConfigDict(from_attributes=True)


class PaginatedPresence(BaseModel):
    items: list[PresenceResponse]
    total: int
    skip: int
    limit: int


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------


class ScanRequest(BaseModel):
    """Payload sent by the client when a user scans.

    The server decides automatically whether the scan is ENTRY or EXIT,
    computes late status and enforces the max-2-scans-per-day rule.
    """

    user_id: int = Field(..., gt=0)
    method: ScanMethod
    # Optional scan timestamp. If omitted, server time is used.
    scanned_at: Optional[datetime] = None


class ScanResponse(BaseModel):
    presence: PresenceResponse
    message: str


# ---------------------------------------------------------------------------
# WorkSchedule
# ---------------------------------------------------------------------------


class WorkScheduleBase(BaseModel):
    user_id: Optional[int] = Field(
        default=None,
        description="If null, this is the global default schedule.",
    )
    start_time: time
    end_time: time
    break_start: Optional[time] = None
    break_end: Optional[time] = None

    @model_validator(mode="after")
    def _validate_ranges(self) -> "WorkScheduleBase":
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be strictly after start_time")
        if (self.break_start is None) ^ (self.break_end is None):
            raise ValueError("break_start and break_end must both be set or both null")
        if self.break_start and self.break_end:
            if self.break_end <= self.break_start:
                raise ValueError("break_end must be strictly after break_start")
            if self.break_start < self.start_time or self.break_end > self.end_time:
                raise ValueError("break must be within the work day")
        return self


class WorkScheduleCreate(WorkScheduleBase):
    pass


class WorkScheduleUpdate(BaseModel):
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    break_start: Optional[time] = None
    break_end: Optional[time] = None


class WorkScheduleResponse(WorkScheduleBase):
    id: int
    created_at: datetime
    updated_at: datetime

    # Populated when the caller adds ``expand=user`` (or nested paths).
    user: Optional[UserSummary] = None

    model_config = ConfigDict(from_attributes=True)


class PaginatedWorkSchedule(BaseModel):
    items: list[WorkScheduleResponse]
    total: int
    skip: int
    limit: int


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


class DailyStat(BaseModel):
    date: date
    count: int
    # Full user objects matching the day. ``user_ids`` is kept for backwards
    # compatibility but is always derived from ``users``.
    users: list[UserSummary] = Field(default_factory=list)
    user_ids: list[int] = Field(default_factory=list)


class RangeStatResponse(BaseModel):
    start: date
    end: date
    total: int
    per_day: list[DailyStat]


class TodayStatResponse(BaseModel):
    date: date
    count: int
    users: list[UserSummary] = Field(default_factory=list)
    user_ids: list[int] = Field(default_factory=list)
