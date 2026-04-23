"""Pydantic schemas for the presence/attendance module."""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

try:  # pragma: no cover - import guard
    from sqlalchemy import inspect as _sa_inspect
except Exception:  # pragma: no cover - SQLAlchemy must be installed at runtime
    _sa_inspect = None  # type: ignore[assignment]

from app.presence_app.constants import ScanMethod, ScanType


# ---------------------------------------------------------------------------
# Base schema that avoids triggering synchronous lazy-loads on SQLAlchemy
# relationships when ``model_validate`` is called from an async context.
#
# Endpoints of this module run under :class:`sqlalchemy.ext.asyncio.AsyncSession`.
# When a schema declares a relationship field (e.g. ``UserSummary.user_groups``
# or ``PresenceResponse.user``), ``from_attributes=True`` makes Pydantic read the
# attribute with ``getattr``. If that relationship was not eagerly loaded, the
# access triggers a blocking lazy-load inside the running event loop and
# SQLAlchemy raises ``MissingGreenlet``:
#
#   sqlalchemy.exc.MissingGreenlet: greenlet_spawn has not been called;
#   can't call await_only() here. Was IO attempted in an unexpected place?
#
# The validator below inspects the ORM state and simply skips unloaded
# attributes so Pydantic never reads them, leaving their schema default
# (usually ``None`` or ``[]``). Callers that need the nested data keep using
# the ``expand`` query parameter, which pre-loads the relationship through
# ``apply_expansion`` / ``selectinload`` before the schema runs.
# ---------------------------------------------------------------------------


class _ORMModel(BaseModel):
    """Base class for schemas fed from SQLAlchemy ORM instances.

    Strips relationship attributes that have not been eagerly loaded to avoid
    triggering an implicit async lazy-load during Pydantic validation.
    """

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def _skip_unloaded_orm_attrs(cls, data: Any) -> Any:
        if _sa_inspect is None:
            return data
        try:
            state = _sa_inspect(data, raiseerr=False)
        except Exception:
            return data
        if state is None or not hasattr(state, "unloaded"):
            # Not a SQLAlchemy ORM instance (e.g. plain dict or Pydantic model).
            return data

        unloaded = set(state.unloaded)
        if not unloaded:
            return data

        # Build an explicit dict from the declared fields, skipping relationships
        # that have not been loaded yet. Columns are always loaded by the
        # initial SELECT and therefore stay accessible.
        result: dict[str, Any] = {}
        for field_name in cls.model_fields:
            if field_name in unloaded:
                continue
            if hasattr(data, field_name):
                try:
                    result[field_name] = getattr(data, field_name)
                except Exception:
                    # Defensive: never let serialization fail because of an
                    # unexpected attribute access error.
                    continue
        return result


# ---------------------------------------------------------------------------
# Nested user summary (lightweight User representation used when expanding)
# ---------------------------------------------------------------------------


class UserSummary(_ORMModel):
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


# ---------------------------------------------------------------------------
# Presence
# ---------------------------------------------------------------------------


class PresenceResponse(_ORMModel):
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


class WorkScheduleResponse(WorkScheduleBase, _ORMModel):
    id: int
    created_at: datetime
    updated_at: datetime

    # Populated when the caller adds ``expand=user`` (or nested paths).
    user: Optional[UserSummary] = None


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


class PrAbsenceTypeResponse(PrAbsenceTypeBase, _ORMModel):
    id: int
    created_at: datetime
    updated_at: datetime


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


class PrLateReasonTypeResponse(PrLateReasonTypeBase, _ORMModel):
    id: int
    created_at: datetime
    updated_at: datetime


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


class AbsenceDeclarationResponse(_ORMModel):
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


class LateDeclarationResponse(_ORMModel):
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


class UserDayDetail(BaseModel):
    """Compact per-day status for a user over the stats range."""

    absent: str = Field(..., description='"oui" ou "non"')
    absence_justifiee: str = Field(
        ..., description='"oui" ou "non" (vaut "non" quand absent="non")'
    )
    retard: str = Field(
        ...,
        description=(
            '"non", "oui" (retard déclaré) ou "oui (N min)" '
            "(retard non déclaré, N = minutes)"
        ),
    )


class GlobalUserStat(GlobalStatTotals):
    user: UserSummary
    details: Optional[dict[date, UserDayDetail]] = Field(
        default=None,
        description=(
            "Statut jour par jour sur la période. Présent uniquement "
            "quand include_daily_details=true."
        ),
    )


class GlobalStatsResponse(BaseModel):
    period: str
    start: date
    end: date
    filter_user_id: Optional[int] = None
    include_daily_details: bool = False
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
