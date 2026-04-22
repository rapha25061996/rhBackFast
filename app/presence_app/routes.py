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
from app.presence_app.constants import (
    AbsenceType,
    DeclarationStatus,
    LateReasonType,
)
from app.presence_app.models import WorkSchedule
from app.presence_app.schemas import (
    AbsenceDeclarationCreate,
    AbsenceDeclarationResponse,
    AbsenceDeclarationReview,
    AbsenceDeclarationUpdate,
    DailyStat,
    GlobalStatsResponse,
    GlobalStatTotals,
    GlobalUserStat,
    LateDailyStat,
    LateDeclarationCreate,
    LateDeclarationResponse,
    LateDeclarationReview,
    LateDeclarationUpdate,
    LateRangeStatResponse,
    LateTodayStatResponse,
    LateUserStat,
    PaginatedAbsenceDeclaration,
    PaginatedLateDeclaration,
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
    AbsenceDeclarationService,
    DeclarationNotFoundError,
    DeclarationStateError,
    GlobalStatsService,
    LateDeclarationService,
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


# ---------------------------------------------------------------------------
# Absence declarations
# ---------------------------------------------------------------------------


def _can_manage_declaration(owner_id: int, user: User) -> bool:
    """Allow the declaration owner or a superuser to mutate it."""
    return bool(getattr(user, "is_superuser", False)) or user.id == owner_id


@router.post(
    "/absence-declarations",
    response_model=AbsenceDeclarationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_absence_declaration(
    payload: AbsenceDeclarationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("absence_declaration", "create")),
):
    target_user_id = payload.user_id if payload.user_id is not None else current_user.id
    if (
        payload.user_id is not None
        and payload.user_id != current_user.id
        and not getattr(current_user, "is_superuser", False)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seul un superuser peut déclarer une absence pour un autre utilisateur",
        )
    try:
        decl = await AbsenceDeclarationService.create(
            db,
            user_id=target_user_id,
            date_debut=payload.date_debut,
            date_fin=payload.date_fin,
            absence_type=payload.absence_type,
            reason=payload.reason,
            justificatif_url=payload.justificatif_url,
        )
    except UserNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return AbsenceDeclarationResponse.model_validate(decl)


@router.get(
    "/absence-declarations",
    response_model=PaginatedAbsenceDeclaration,
)
async def list_absence_declarations(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("absence_declaration", "read")),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    user_id: Optional[int] = Query(None),
    decl_status: Optional[DeclarationStatus] = Query(
        None, alias="status", description="Filtrer par statut"
    ),
    absence_type: Optional[AbsenceType] = Query(None),
    start: Optional[_date] = Query(
        None, description="Borne basse (chevauchement avec date_fin)"
    ),
    end: Optional[_date] = Query(
        None, description="Borne haute (chevauchement avec date_debut)"
    ),
    expand: Optional[str] = Query(
        None, description="Relations à inclure. Exemples: user, reviewed_by"
    ),
):
    items, total = await AbsenceDeclarationService.list(
        db,
        skip=skip,
        limit=limit,
        user_id=user_id,
        status=decl_status,
        absence_type=absence_type,
        start=start,
        end=end,
        expand_fields=parse_expand_param(expand),
    )
    return PaginatedAbsenceDeclaration(
        items=[AbsenceDeclarationResponse.model_validate(i) for i in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/absence-declarations/{declaration_id}",
    response_model=AbsenceDeclarationResponse,
)
async def get_absence_declaration(
    declaration_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("absence_declaration", "read")),
    expand: Optional[str] = Query(None),
):
    try:
        decl = await AbsenceDeclarationService.get(
            db, declaration_id, expand_fields=parse_expand_param(expand)
        )
    except DeclarationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return AbsenceDeclarationResponse.model_validate(decl)


@router.patch(
    "/absence-declarations/{declaration_id}",
    response_model=AbsenceDeclarationResponse,
)
async def update_absence_declaration(
    declaration_id: int,
    payload: AbsenceDeclarationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("absence_declaration", "update")),
):
    try:
        existing = await AbsenceDeclarationService.get(db, declaration_id)
    except DeclarationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if not _can_manage_declaration(existing.user_id, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous ne pouvez modifier que vos propres déclarations",
        )
    try:
        decl = await AbsenceDeclarationService.update(
            db,
            declaration_id,
            date_debut=payload.date_debut,
            date_fin=payload.date_fin,
            absence_type=payload.absence_type,
            reason=payload.reason,
            justificatif_url=payload.justificatif_url,
        )
    except DeclarationStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return AbsenceDeclarationResponse.model_validate(decl)


@router.post(
    "/absence-declarations/{declaration_id}/review",
    response_model=AbsenceDeclarationResponse,
)
async def review_absence_declaration(
    declaration_id: int,
    payload: AbsenceDeclarationReview,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("absence_declaration", "review")),
):
    try:
        decl = await AbsenceDeclarationService.review(
            db,
            declaration_id,
            decision=payload.decision,
            reviewer_id=current_user.id,
            review_comment=payload.review_comment,
        )
    except DeclarationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except DeclarationStateError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return AbsenceDeclarationResponse.model_validate(decl)


@router.delete(
    "/absence-declarations/{declaration_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_absence_declaration(
    declaration_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("absence_declaration", "delete")),
):
    try:
        existing = await AbsenceDeclarationService.get(db, declaration_id)
    except DeclarationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if not _can_manage_declaration(existing.user_id, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous ne pouvez supprimer que vos propres déclarations",
        )
    await AbsenceDeclarationService.delete(db, declaration_id)
    return None


# ---------------------------------------------------------------------------
# Late declarations
# ---------------------------------------------------------------------------


@router.post(
    "/late-declarations",
    response_model=LateDeclarationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_late_declaration(
    payload: LateDeclarationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("late_declaration", "create")),
):
    target_user_id = payload.user_id if payload.user_id is not None else current_user.id
    if (
        payload.user_id is not None
        and payload.user_id != current_user.id
        and not getattr(current_user, "is_superuser", False)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seul un superuser peut déclarer un retard pour un autre utilisateur",
        )
    try:
        decl = await LateDeclarationService.create(
            db,
            user_id=target_user_id,
            date_retard=payload.date_retard,
            reason_type=payload.reason_type,
            expected_arrival_time=payload.expected_arrival_time,
            reason=payload.reason,
        )
    except UserNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return LateDeclarationResponse.model_validate(decl)


@router.get(
    "/late-declarations",
    response_model=PaginatedLateDeclaration,
)
async def list_late_declarations(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("late_declaration", "read")),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    user_id: Optional[int] = Query(None),
    decl_status: Optional[DeclarationStatus] = Query(
        None, alias="status", description="Filtrer par statut"
    ),
    reason_type: Optional[LateReasonType] = Query(None),
    start: Optional[_date] = Query(None),
    end: Optional[_date] = Query(None),
    expand: Optional[str] = Query(None),
):
    items, total = await LateDeclarationService.list(
        db,
        skip=skip,
        limit=limit,
        user_id=user_id,
        status=decl_status,
        reason_type=reason_type,
        start=start,
        end=end,
        expand_fields=parse_expand_param(expand),
    )
    return PaginatedLateDeclaration(
        items=[LateDeclarationResponse.model_validate(i) for i in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/late-declarations/{declaration_id}",
    response_model=LateDeclarationResponse,
)
async def get_late_declaration(
    declaration_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("late_declaration", "read")),
    expand: Optional[str] = Query(None),
):
    try:
        decl = await LateDeclarationService.get(
            db, declaration_id, expand_fields=parse_expand_param(expand)
        )
    except DeclarationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return LateDeclarationResponse.model_validate(decl)


@router.patch(
    "/late-declarations/{declaration_id}",
    response_model=LateDeclarationResponse,
)
async def update_late_declaration(
    declaration_id: int,
    payload: LateDeclarationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("late_declaration", "update")),
):
    try:
        existing = await LateDeclarationService.get(db, declaration_id)
    except DeclarationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if not _can_manage_declaration(existing.user_id, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous ne pouvez modifier que vos propres déclarations",
        )
    try:
        decl = await LateDeclarationService.update(
            db,
            declaration_id,
            date_retard=payload.date_retard,
            expected_arrival_time=payload.expected_arrival_time,
            reason_type=payload.reason_type,
            reason=payload.reason,
        )
    except DeclarationStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return LateDeclarationResponse.model_validate(decl)


@router.post(
    "/late-declarations/{declaration_id}/review",
    response_model=LateDeclarationResponse,
)
async def review_late_declaration(
    declaration_id: int,
    payload: LateDeclarationReview,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("late_declaration", "review")),
):
    try:
        decl = await LateDeclarationService.review(
            db,
            declaration_id,
            decision=payload.decision,
            reviewer_id=current_user.id,
            review_comment=payload.review_comment,
        )
    except DeclarationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except DeclarationStateError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return LateDeclarationResponse.model_validate(decl)


@router.delete(
    "/late-declarations/{declaration_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_late_declaration(
    declaration_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("late_declaration", "delete")),
):
    try:
        existing = await LateDeclarationService.get(db, declaration_id)
    except DeclarationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if not _can_manage_declaration(existing.user_id, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous ne pouvez supprimer que vos propres déclarations",
        )
    await LateDeclarationService.delete(db, declaration_id)
    return None


# ---------------------------------------------------------------------------
# Global stats
# ---------------------------------------------------------------------------


_GLOBAL_PERIOD_CHOICES = {"daily", "weekly", "monthly", "yearly", "custom"}


def _compute_global_range(
    period: str,
    reference_date: Optional[_date],
    start: Optional[_date],
    end: Optional[_date],
) -> tuple[_date, _date]:
    from calendar import monthrange
    from datetime import timedelta

    if period not in _GLOBAL_PERIOD_CHOICES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"period doit être l'une de {sorted(_GLOBAL_PERIOD_CHOICES)}",
        )
    ref = reference_date or _today()
    if period == "custom":
        if start is None or end is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="period=custom exige les paramètres 'start' et 'end'",
            )
        _validate_range(start, end)
        return start, end
    if period == "daily":
        return ref, ref
    if period == "weekly":
        # Monday..Sunday containing `ref`
        week_start = ref - timedelta(days=ref.weekday())
        return week_start, week_start + timedelta(days=6)
    if period == "monthly":
        first = ref.replace(day=1)
        last_day = monthrange(ref.year, ref.month)[1]
        return first, ref.replace(day=last_day)
    # yearly
    return ref.replace(month=1, day=1), ref.replace(month=12, day=31)


@router.get("/stats/global", response_model=GlobalStatsResponse)
async def stats_global(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("presence", "view_stats")),
    period: str = Query(
        "monthly",
        description="Période: daily, weekly, monthly, yearly ou custom",
    ),
    reference_date: Optional[_date] = Query(
        None,
        description=(
            "Date de référence utilisée pour calculer la semaine/mois/année. "
            "Défaut: aujourd'hui. Ignoré si period=custom."
        ),
    ),
    start: Optional[_date] = Query(None, description="Requis si period=custom"),
    end: Optional[_date] = Query(None, description="Requis si period=custom"),
    user_id: Optional[int] = Query(
        None, description="Filtrer sur un utilisateur (sinon tous les actifs)"
    ),
    expand: Optional[str] = Query(
        None, description="Relations utilisateur. Exemples: employe, employe.poste"
    ),
):
    """Statistiques globales (présence, absence, retards) par utilisateur.

    Agrège sur la période demandée:
      - ``presence_count``: jours avec au moins un scan ENTRY.
      - ``absence_total_count``: jours de la période sans aucun scan.
      - ``absence_justified_count``: absences couvertes par une déclaration
        d'absence ``APPROVED``.
      - ``absence_unjustified_count``: complément.
      - ``late_total_count``: scans ENTRY marqués en retard.
      - ``late_declared_count``: retards couverts par une déclaration de
        retard ``APPROVED`` pour le même jour.
      - ``late_undeclared_count``: complément.
      - ``total_minutes_late``: somme des minutes de retard.

    Par défaut, toutes les personnes actives sont retournées. Utilisez
    ``user_id`` pour filtrer sur un utilisateur spécifique.
    """
    range_start, range_end = _compute_global_range(period, reference_date, start, end)
    ordered_user_ids, stats, users_by_id = await GlobalStatsService.compute(
        db,
        start=range_start,
        end=range_end,
        user_id=user_id,
        expand_fields=_parse_user_expand(expand),
    )

    totals = GlobalStatTotals()
    per_user: list[GlobalUserStat] = []
    for uid in ordered_user_ids:
        user = users_by_id.get(uid)
        if user is None:
            continue
        row = stats[uid]
        totals = GlobalStatTotals(
            presence_count=totals.presence_count + row["presence_count"],
            absence_total_count=totals.absence_total_count + row["absence_total_count"],
            absence_justified_count=totals.absence_justified_count
            + row["absence_justified_count"],
            absence_unjustified_count=totals.absence_unjustified_count
            + row["absence_unjustified_count"],
            late_total_count=totals.late_total_count + row["late_total_count"],
            late_declared_count=totals.late_declared_count + row["late_declared_count"],
            late_undeclared_count=totals.late_undeclared_count
            + row["late_undeclared_count"],
            total_minutes_late=totals.total_minutes_late + row["total_minutes_late"],
        )
        per_user.append(
            GlobalUserStat(
                user=UserSummary.model_validate(user),
                **row,
            )
        )

    return GlobalStatsResponse(
        period=period,
        start=range_start,
        end=range_end,
        filter_user_id=user_id,
        totals=totals,
        per_user=per_user,
    )
