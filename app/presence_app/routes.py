"""FastAPI routes for the presence/attendance module."""
from __future__ import annotations

from datetime import date as _date
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.presence_app.models import WorkSchedule
from app.presence_app.schemas import (
    DailyStat,
    PaginatedPresence,
    PresenceResponse,
    RangeStatResponse,
    ScanRequest,
    ScanResponse,
    TodayStatResponse,
    WorkScheduleCreate,
    WorkScheduleResponse,
    WorkScheduleUpdate,
)
from app.presence_app.services import (
    MaxScansReachedError,
    PresenceService,
    UserNotFoundError,
)

router = APIRouter(prefix="/api/presence", tags=["Presence Management"])


@router.post("/scan", response_model=ScanResponse, status_code=status.HTTP_201_CREATED)
async def scan(payload: ScanRequest, db: AsyncSession = Depends(get_db)):
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


@router.get("/presences", response_model=PaginatedPresence)
async def list_presences(
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    items, total = await PresenceService.list_presences(db, skip=skip, limit=limit)
    return PaginatedPresence(
        items=[PresenceResponse.model_validate(i) for i in items],
        total=total, skip=skip, limit=limit,
    )


@router.get("/presences/user/{user_id}", response_model=PaginatedPresence)
async def list_presences_by_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    items, total = await PresenceService.list_presences(db, skip=skip, limit=limit, user_id=user_id)
    return PaginatedPresence(
        items=[PresenceResponse.model_validate(i) for i in items],
        total=total, skip=skip, limit=limit,
    )


@router.get("/presences/date/{on_date}", response_model=PaginatedPresence)
async def list_presences_by_date(
    on_date: _date,
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    items, total = await PresenceService.list_presences(db, skip=skip, limit=limit, on_date=on_date)
    return PaginatedPresence(
        items=[PresenceResponse.model_validate(i) for i in items],
        total=total, skip=skip, limit=limit,
    )


def _today() -> _date:
    return datetime.utcnow().date()


@router.get("/stats/presence/today", response_model=TodayStatResponse)
async def stats_presence_today(db: AsyncSession = Depends(get_db)):
    day, user_ids = await PresenceService.presence_today(db, _today())
    return TodayStatResponse(date=day, count=len(user_ids), user_ids=user_ids)


@router.get("/stats/late/today", response_model=TodayStatResponse)
async def stats_late_today(db: AsyncSession = Depends(get_db)):
    day, user_ids = await PresenceService.late_today(db, _today())
    return TodayStatResponse(date=day, count=len(user_ids), user_ids=user_ids)


@router.get("/stats/absence/today", response_model=TodayStatResponse)
async def stats_absence_today(db: AsyncSession = Depends(get_db)):
    day, user_ids = await PresenceService.absence_today(db, _today())
    return TodayStatResponse(date=day, count=len(user_ids), user_ids=user_ids)


def _validate_range(start: _date, end: _date) -> None:
    if end < start:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="'end' doit être postérieur ou égal à 'start'",
        )


def _build_range_response(start, end, data):
    per_day = [DailyStat(date=d, count=len(ids), user_ids=ids) for d, ids in data]
    total = sum(s.count for s in per_day)
    return RangeStatResponse(start=start, end=end, total=total, per_day=per_day)


@router.get("/stats/presence/range", response_model=RangeStatResponse)
async def stats_presence_range(
    start: _date = Query(..., description="Date de début (YYYY-MM-DD)"),
    end: _date = Query(..., description="Date de fin (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
):
    _validate_range(start, end)
    data = await PresenceService.presence_range(db, start, end)
    return _build_range_response(start, end, data)


@router.get("/stats/late/range", response_model=RangeStatResponse)
async def stats_late_range(
    start: _date = Query(..., description="Date de début (YYYY-MM-DD)"),
    end: _date = Query(..., description="Date de fin (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
):
    _validate_range(start, end)
    data = await PresenceService.late_range(db, start, end)
    return _build_range_response(start, end, data)


@router.get("/stats/absence/range", response_model=RangeStatResponse)
async def stats_absence_range(
    start: _date = Query(..., description="Date de début (YYYY-MM-DD)"),
    end: _date = Query(..., description="Date de fin (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
):
    _validate_range(start, end)
    data = await PresenceService.absence_range(db, start, end)
    return _build_range_response(start, end, data)


@router.get("/work-schedules", response_model=list[WorkScheduleResponse])
async def list_work_schedules(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(WorkSchedule))).scalars().all()
    return [WorkScheduleResponse.model_validate(r) for r in rows]


@router.post("/work-schedules", response_model=WorkScheduleResponse, status_code=status.HTTP_201_CREATED)
async def create_work_schedule(payload: WorkScheduleCreate, db: AsyncSession = Depends(get_db)):
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
async def update_work_schedule(schedule_id: int, payload: WorkScheduleUpdate, db: AsyncSession = Depends(get_db)):
    schedule = await db.get(WorkSchedule, schedule_id)
    if schedule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"WorkSchedule {schedule_id} introuvable")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(schedule, field, value)
    if schedule.end_time <= schedule.start_time:
        raise HTTPException(status_code=400, detail="end_time doit être strictement après start_time")
    if (schedule.break_start is None) ^ (schedule.break_end is None):
        raise HTTPException(status_code=400, detail="break_start et break_end doivent être tous deux définis ou tous deux nuls")
    await db.flush()
    await db.refresh(schedule)
    return WorkScheduleResponse.model_validate(schedule)


@router.delete("/work-schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_work_schedule(schedule_id: int, db: AsyncSession = Depends(get_db)):
    schedule = await db.get(WorkSchedule, schedule_id)
    if schedule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"WorkSchedule {schedule_id} introuvable")
    await db.delete(schedule)
    await db.flush()
    return None