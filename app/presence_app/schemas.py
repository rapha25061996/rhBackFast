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


# ---------------------------------------------------------------------------
# Late statistics (includes the minutes-late delta per user per day)
# ---------------------------------------------------------------------------


class LateUserStat(BaseModel):
    """Per-user late information for a given day.

    ``minutes_late`` is the difference, in minutes, between the ENTRY scan
    time and the user's effective schedule start time (per-user override or
    global default). It is always ``>= 0`` because only late entries are
    returned here.
    """

    user: UserSummary
    minutes_late: int = Field(..., ge=0)
    heure_scan: time
    scheduled_start: time
    date_scan: date


class LateTodayStatResponse(BaseModel):
    date: date
    count: int
    users: list[LateUserStat] = Field(default_factory=list)
    user_ids: list[int] = Field(default_factory=list)
    # Aggregated summary to help dashboards without re-iterating `users`.
    total_minutes_late: int = Field(default=0, ge=0)
    average_minutes_late: float = Field(default=0.0, ge=0)


class LateDailyStat(BaseModel):
    date: date
    count: int
    users: list[LateUserStat] = Field(default_factory=list)
    user_ids: list[int] = Field(default_factory=list)
    total_minutes_late: int = Field(default=0, ge=0)
    average_minutes_late: float = Field(default=0.0, ge=0)


class LateRangeStatResponse(BaseModel):
    start: date
    end: date
    total: int
    total_minutes_late: int = Field(default=0, ge=0)
    per_day: list[LateDailyStat]


# ---------------------------------------------------------------------------
# Reference data: absence types & late reason types
# ---------------------------------------------------------------------------


class PrAbsenceTypeBase(BaseModel):
    code: str = Field(..., min_length=1, max_length=32)
    label: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    is_active: bool = True


class PrAbsenceTypeCreate(PrAbsenceTypeBase):
    pass


class PrAbsenceTypeUpdate(BaseModel):
    code: Optional[str] = Field(default=None, min_length=1, max_length=32)
    label: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class PrAbsenceTypeResponse(PrAbsenceTypeBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaginatedPrAbsenceType(BaseModel):
    items: list[PrAbsenceTypeResponse]
    total: int
    skip: int
    limit: int


class PrLateReasonTypeBase(BaseModel):
    code: str = Field(..., min_length=1, max_length=32)
    label: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    is_active: bool = True


class PrLateReasonTypeCreate(PrLateReasonTypeBase):
    pass


class PrLateReasonTypeUpdate(BaseModel):
    code: Optional[str] = Field(default=None, min_length=1, max_length=32)
    label: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class PrLateReasonTypeResponse(PrLateReasonTypeBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaginatedPrLateReasonType(BaseModel):
    items: list[PrLateReasonTypeResponse]
    total: int
    skip: int
    limit: int


# ---------------------------------------------------------------------------
# Absence declarations
# ---------------------------------------------------------------------------


class AbsenceDeclarationBase(BaseModel):
    date_debut: date
    date_fin: Optional[date] = Field(
        default=None,
        description=(
            "Dernier jour de l'absence (optionnel). Si omis, la déclaration "
            "ne couvre que ``date_debut``."
        ),
    )
    absence_type_id: int = Field(..., gt=0)
    reason: Optional[str] = None

    @model_validator(mode="after")
    def _validate_dates(self) -> "AbsenceDeclarationBase":
        if self.date_fin is not None and self.date_fin < self.date_debut:
            raise ValueError("date_fin must be greater than or equal to date_debut")
        return self


class AbsenceDeclarationUpdate(BaseModel):
    date_debut: Optional[date] = None
    date_fin: Optional[date] = None
    absence_type_id: Optional[int] = Field(default=None, gt=0)
    reason: Optional[str] = None
    clear_date_fin: bool = Field(
        default=False,
        description="Si true, date_fin est explicitement effacé (même jour que date_debut).",
    )
    clear_justificatif: bool = Field(
        default=False,
        description="Si true, le justificatif existant est supprimé.",
    )


class AbsenceDeclarationResponse(BaseModel):
    id: int
    user_id: int
    absence_type_id: int
    date_debut: date
    date_fin: Optional[date] = None
    reason: Optional[str] = None
    justificatif_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    user: Optional[UserSummary] = None
    absence_type: Optional[PrAbsenceTypeResponse] = None

    model_config = ConfigDict(from_attributes=True)


class PaginatedAbsenceDeclaration(BaseModel):
    items: list[AbsenceDeclarationResponse]
    total: int
    skip: int
    limit: int


# ---------------------------------------------------------------------------
# Late declarations
# ---------------------------------------------------------------------------


class LateDeclarationBase(BaseModel):
    date_retard: date
    expected_arrival_time: Optional[time] = None
    reason_type_id: int = Field(..., gt=0)
    reason: Optional[str] = None


class LateDeclarationCreate(LateDeclarationBase):
    user_id: Optional[int] = Field(
        default=None,
        description=(
            "ID de l'utilisateur concerné. Si omis, la déclaration est créée "
            "pour l'utilisateur authentifié."
        ),
    )


class LateDeclarationUpdate(BaseModel):
    date_retard: Optional[date] = None
    expected_arrival_time: Optional[time] = None
    reason_type_id: Optional[int] = Field(default=None, gt=0)
    reason: Optional[str] = None


class LateDeclarationResponse(BaseModel):
    id: int
    user_id: int
    reason_type_id: int
    date_retard: date
    expected_arrival_time: Optional[time] = None
    reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    user: Optional[UserSummary] = None
    reason_type: Optional[PrLateReasonTypeResponse] = None

    model_config = ConfigDict(from_attributes=True)


class PaginatedLateDeclaration(BaseModel):
    items: list[LateDeclarationResponse]
    total: int
    skip: int
    limit: int


# ---------------------------------------------------------------------------
# Global stats
# ---------------------------------------------------------------------------


class GlobalStatTotals(BaseModel):
    presence_count: int = 0
    absence_total_count: int = 0
    absence_justified_count: int = 0
    absence_unjustified_count: int = 0
    late_total_count: int = 0
    late_declared_count: int = 0
    late_undeclared_count: int = 0
    total_minutes_late: int = 0


class GlobalUserStat(GlobalStatTotals):
    user: UserSummary


class GlobalStatsResponse(BaseModel):
    period: str
    start: date
    end: date
    filter_user_id: Optional[int] = None
    totals: GlobalStatTotals
    per_user: list[GlobalUserStat]


class GlobalUserDayStat(GlobalStatTotals):
    """Per-user counters for a single day inside the detailed stats."""

    user: UserSummary


class GlobalDayStat(GlobalStatTotals):
    """Totals + per-user breakdown for a single day."""

    date: date
    per_user: list[GlobalUserDayStat] = []


class GlobalStatsDetailResponse(BaseModel):
    """Day-by-day detail for :class:`GlobalStatsResponse`."""

    period: str
    start: date
    end: date
    filter_user_id: Optional[int] = None
    include_users: bool = True
    totals: GlobalStatTotals
    per_day: list[GlobalDayStat]
