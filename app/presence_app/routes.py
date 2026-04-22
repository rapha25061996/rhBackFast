"""FastAPI routes for the presence/attendance module."""
from __future__ import annotations

from datetime import date as _date
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import require_permission
from app.core.query_utils import apply_expansion, parse_expand_param
from app.presence_app.models import WorkSchedule
from app.presence_app.schemas import (
    DailyStat,
    LateDailyStat,
    LateRangeStatResponse,
    LateTodayStatResponse,
    LateUserStat,
    PaginatedPresence,
    PaginatedWorkSchedule,
    PresenceResponse,
    RangeStatResponse,
    ScanRequest,
    ScanResponse,
    TodayStatResponse,
    UserSummary,
    WorkScheduleCreate,
    WorkScheduleResponse,
    WorkScheduleUpdate,
)
from app.presence_app.services import (
    LateEntry,
    MaxScansReachedError,
    PresenceService,
    UserNotFoundError,
)
from app.user_app.models import User

router = APIRouter(prefix="/api/presence", tags=["Presence Management"])


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _today() -> _date:
    return datetime.utcnow().date()


def _validate_range(start: _date, end: _date) -> None:
    if end < start:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="'end' doit être postérieur ou égal à 'start'",
        )


def _users_to_summary(users: list[User]) -> list[UserSummary]:
    return [UserSummary.model_validate(u) for u in users]


def _parse_user_expand(expand: Optional[str]) -> list[str]:
    """Parse ``expand`` for stats endpoints (returned users).

    Stats endpoints expose users as the main payload so each path is applied
    directly on :class:`User`. Example: ``expand=employe,employe.poste``.
    """
    return parse_expand_param(expand)


def _build_today_response(
    day: _date, users: list[User]
) -> TodayStatResponse:
    summaries = _users_to_summary(users)
    return TodayStatResponse(
        date=day,
        count=len(summaries),
        users=summaries,
        user_ids=[u.id for u in summaries],
    )


def _build_range_response(
    start: _date, end: _date, data: list[tuple[_date, list[User]]]
) -> RangeStatResponse:
    per_day: list[DailyStat] = []
    for day, users in data:
        summaries = _users_to_summary(users)
        per_day.append(
            DailyStat(
                date=day,
                count=len(summaries),
                users=summaries,
                user_ids=[u.id for u in summaries],
            )
        )
    total = sum(s.count for s in per_day)
    return RangeStatResponse(start=start, end=end, total=total, per_day=per_day)


def _late_entry_to_stat(entry: LateEntry) -> LateUserStat:
    return LateUserStat(
        user=UserSummary.model_validate(entry.user),
        minutes_late=entry.minutes_late,
        heure_scan=entry.heure_scan,
        scheduled_start=entry.scheduled_start,
        date_scan=entry.date_scan,
    )


def _build_late_today_response(
    day: _date, entries: list[LateEntry]
) -> LateTodayStatResponse:
    stats = [_late_entry_to_stat(e) for e in entries]
    total_minutes = sum(s.minutes_late for s in stats)
    avg_minutes = (total_minutes / len(stats)) if stats else 0.0
    return LateTodayStatResponse(
        date=day,
        count=len(stats),
        users=stats,
        user_ids=[s.user.id for s in stats],
        total_minutes_late=total_minutes,
        average_minutes_late=round(avg_minutes, 2),
    )


def _build_late_range_response(
    start: _date, end: _date, data: list[tuple[_date, list[LateEntry]]]
) -> LateRangeStatResponse:
    per_day: list[LateDailyStat] = []
    grand_total_minutes = 0
    grand_total_count = 0
    for day, entries in data:
        stats = [_late_entry_to_stat(e) for e in entries]
        day_total_minutes = sum(s.minutes_late for s in stats)
        day_avg_minutes = (day_total_minutes / len(stats)) if stats else 0.0
        grand_total_minutes += day_total_minutes
        grand_total_count += len(stats)
        per_day.append(
            LateDailyStat(
                date=day,
                count=len(stats),
                users=stats,
                user_ids=[s.user.id for s in stats],
                total_minutes_late=day_total_minutes,
                average_minutes_late=round(day_avg_minutes, 2),
            )
        )
    return LateRangeStatResponse(
        start=start,
        end=end,
        total=grand_total_count,
        total_minutes_late=grand_total_minutes,
        per_day=per_day,
    )


# ---------------------------------------------------------------------------
# Scans
# ---------------------------------------------------------------------------


@router.post("/scan", response_model=ScanResponse, status_code=status.HTTP_201_CREATED)
async def scan(
    payload: ScanRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("presence", "create")),
):
    try:
        presence = await PresenceService.register_scan(
            db,
            user_id=payload.user_id,
            method=payload.method,
            scanned_at=payload.scanned_at,
        )
    except UserNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except MaxScansReachedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    return ScanResponse(
        presence=PresenceResponse.model_validate(presence),
        message=f"{presence.scan_type} enregistré pour user {presence.user_id}",
    )


# ---------------------------------------------------------------------------
# Presences (list)
# ---------------------------------------------------------------------------


@router.get("/presences", response_model=PaginatedPresence)
async def list_presences(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("presence", "read")),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    user_id: Optional[int] = Query(None, description="Filtrer par utilisateur"),
    on_date: Optional[_date] = Query(
        None, description="Filtrer sur une date précise (YYYY-MM-DD)"
    ),
    expand: Optional[str] = Query(
        None,
        description="Relations à inclure. Exemples: user, user.employe, user.employe.poste",
    ),
):
    items, total = await PresenceService.list_presences(
        db,
        skip=skip,
        limit=limit,
        user_id=user_id,
        on_date=on_date,
        expand_fields=parse_expand_param(expand),
    )
    return PaginatedPresence(
        items=[PresenceResponse.model_validate(i) for i in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/presences/user/{user_id}", response_model=PaginatedPresence)
async def list_presences_by_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("presence", "read")),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    expand: Optional[str] = Query(None),
):
    items, total = await PresenceService.list_presences(
        db,
        skip=skip,
        limit=limit,
        user_id=user_id,
        expand_fields=parse_expand_param(expand),
    )
    return PaginatedPresence(
        items=[PresenceResponse.model_validate(i) for i in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/presences/date/{on_date}", response_model=PaginatedPresence)
async def list_presences_by_date(
    on_date: _date,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("presence", "read")),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    expand: Optional[str] = Query(None),
):
    items, total = await PresenceService.list_presences(
        db,
        skip=skip,
        limit=limit,
        on_date=on_date,
        expand_fields=parse_expand_param(expand),
    )
    return PaginatedPresence(
        items=[PresenceResponse.model_validate(i) for i in items],
        total=total,
        skip=skip,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# Statistics — today
# ---------------------------------------------------------------------------


@router.get("/stats/presence/today", response_model=TodayStatResponse)
async def stats_presence_today(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("presence", "view_stats")),
    expand: Optional[str] = Query(
        None,
        description=(
            "Relations à inclure sur les utilisateurs retournés. "
            "Exemples: employe, employe.poste, user_groups"
        ),
    ),
):
    day, users = await PresenceService.presence_today(
        db, _today(), expand_fields=_parse_user_expand(expand)
    )
    return _build_today_response(day, users)


@router.get("/stats/late/today", response_model=LateTodayStatResponse)
async def stats_late_today(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("presence", "view_stats")),
    expand: Optional[str] = Query(
        None,
        description=(
            "Relations à inclure sur les utilisateurs retournés. "
            "Exemples: employe, employe.poste, user_groups"
        ),
    ),
):
    """Liste les retards du jour avec les minutes de retard par utilisateur.

    Chaque entrée contient l'utilisateur complet (``user``), l'heure de
    scan, l'heure de début planifiée (``scheduled_start``) et le delta
    ``minutes_late`` calculé à partir du ``WorkSchedule`` effectif de
    l'utilisateur (override personnel, sinon défaut global).
    """
    day, entries = await PresenceService.late_today(
        db, _today(), expand_fields=_parse_user_expand(expand)
    )
    return _build_late_today_response(day, entries)


@router.get("/stats/absence/today", response_model=TodayStatResponse)
async def stats_absence_today(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("presence", "view_stats")),
    expand: Optional[str] = Query(None),
):
    day, users = await PresenceService.absence_today(
        db, _today(), expand_fields=_parse_user_expand(expand)
    )
    return _build_today_response(day, users)


# ---------------------------------------------------------------------------
# Statistics — range
# ---------------------------------------------------------------------------


@router.get("/stats/presence/range", response_model=RangeStatResponse)
async def stats_presence_range(
    start: _date = Query(..., description="Date de début (YYYY-MM-DD)"),
    end: _date = Query(..., description="Date de fin (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("presence", "view_stats")),
    expand: Optional[str] = Query(None),
):
    _validate_range(start, end)
    data = await PresenceService.presence_range(
        db, start, end, expand_fields=_parse_user_expand(expand)
    )
    return _build_range_response(start, end, data)


@router.get("/stats/late/range", response_model=LateRangeStatResponse)
async def stats_late_range(
    start: _date = Query(..., description="Date de début (YYYY-MM-DD)"),
    end: _date = Query(..., description="Date de fin (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("presence", "view_stats")),
    expand: Optional[str] = Query(None),
):
    """Liste jour par jour les retards avec les minutes de retard par utilisateur.

    Chaque ``per_day[*].users[*]`` expose ``minutes_late``,
    ``scheduled_start`` et ``heure_scan``. ``total_minutes_late`` et
    ``average_minutes_late`` sont fournis par jour et pour l'ensemble de la
    période.
    """
    _validate_range(start, end)
    data = await PresenceService.late_range(
        db, start, end, expand_fields=_parse_user_expand(expand)
    )
    return _build_late_range_response(start, end, data)


@router.get("/stats/absence/range", response_model=RangeStatResponse)
async def stats_absence_range(
    start: _date = Query(..., description="Date de début (YYYY-MM-DD)"),
    end: _date = Query(..., description="Date de fin (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("presence", "view_stats")),
    expand: Optional[str] = Query(None),
):
    _validate_range(start, end)
    data = await PresenceService.absence_range(
        db, start, end, expand_fields=_parse_user_expand(expand)
    )
    return _build_range_response(start, end, data)


# ---------------------------------------------------------------------------
# Work schedules
# ---------------------------------------------------------------------------


@router.get("/work-schedules", response_model=PaginatedWorkSchedule)
async def list_work_schedules(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("work_schedule", "read")),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    user_id: Optional[int] = Query(
        None,
        description="Filtrer par utilisateur. Ignoré si include_default=true.",
    ),
    include_default: bool = Query(
        False,
        description=(
            "Inclure le planning global (user_id IS NULL). "
            "Si true et user_id est fourni, la réponse contient les deux."
        ),
    ),
    search: Optional[str] = Query(None, description="Recherche sur le user lié"),
    expand: Optional[str] = Query(
        None, description="Relations à inclure. Exemples: user, user.employe"
    ),
):
    stmt = select(WorkSchedule)
    count_stmt = select(func.count()).select_from(WorkSchedule)

    clauses = []
    if user_id is not None and include_default:
        clauses.append(or_(WorkSchedule.user_id == user_id, WorkSchedule.user_id.is_(None)))
    elif user_id is not None:
        clauses.append(WorkSchedule.user_id == user_id)

    if search:
        like = f"%{search}%"
        stmt = stmt.join(User, WorkSchedule.user_id == User.id).where(
            or_(
                User.email.ilike(like),
                User.nom.ilike(like),
                User.prenom.ilike(like),
            )
        )
        count_stmt = count_stmt.join(User, WorkSchedule.user_id == User.id).where(
            or_(
                User.email.ilike(like),
                User.nom.ilike(like),
                User.prenom.ilike(like),
            )
        )

    for clause in clauses:
        stmt = stmt.where(clause)
        count_stmt = count_stmt.where(clause)

    total = (await db.execute(count_stmt)).scalar() or 0

    expand_fields = parse_expand_param(expand)
    if expand_fields:
        stmt = apply_expansion(stmt, WorkSchedule, expand_fields)

    stmt = stmt.order_by(WorkSchedule.user_id.is_(None).desc(), WorkSchedule.id.asc())
    stmt = stmt.offset(skip).limit(limit)

    rows = (await db.execute(stmt)).scalars().all()
    return PaginatedWorkSchedule(
        items=[WorkScheduleResponse.model_validate(r) for r in rows],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/work-schedules/{schedule_id}", response_model=WorkScheduleResponse)
async def get_work_schedule(
    schedule_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("work_schedule", "read")),
    expand: Optional[str] = Query(None),
):
    stmt = select(WorkSchedule).where(WorkSchedule.id == schedule_id)
    expand_fields = parse_expand_param(expand)
    if expand_fields:
        stmt = apply_expansion(stmt, WorkSchedule, expand_fields)
    schedule = (await db.execute(stmt)).scalar_one_or_none()
    if schedule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"WorkSchedule {schedule_id} introuvable",
        )
    return WorkScheduleResponse.model_validate(schedule)


@router.post(
    "/work-schedules",
    response_model=WorkScheduleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_work_schedule(
    payload: WorkScheduleCreate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("work_schedule", "create")),
):
    if payload.user_id is None:
        stmt = select(WorkSchedule).where(WorkSchedule.user_id.is_(None))
    else:
        stmt = select(WorkSchedule).where(WorkSchedule.user_id == payload.user_id)
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Un planning existe déjà pour cet utilisateur (ou le défaut global)",
        )
    schedule = WorkSchedule(**payload.model_dump())
    db.add(schedule)
    await db.flush()
    await db.refresh(schedule)
    return WorkScheduleResponse.model_validate(schedule)


@router.patch("/work-schedules/{schedule_id}", response_model=WorkScheduleResponse)
async def update_work_schedule(
    schedule_id: int,
    payload: WorkScheduleUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("work_schedule", "update")),
):
    schedule = await db.get(WorkSchedule, schedule_id)
    if schedule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"WorkSchedule {schedule_id} introuvable",
        )
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(schedule, field, value)
    if schedule.end_time <= schedule.start_time:
        raise HTTPException(
            status_code=400, detail="end_time doit être strictement après start_time"
        )
    if (schedule.break_start is None) ^ (schedule.break_end is None):
        raise HTTPException(
            status_code=400,
            detail="break_start et break_end doivent être tous deux définis ou tous deux nuls",
        )
    await db.flush()
    await db.refresh(schedule)
    return WorkScheduleResponse.model_validate(schedule)


@router.delete("/work-schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_work_schedule(
    schedule_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("work_schedule", "delete")),
):
    schedule = await db.get(WorkSchedule, schedule_id)
    if schedule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"WorkSchedule {schedule_id} introuvable",
        )
    await db.delete(schedule)
    await db.flush()
    return None
