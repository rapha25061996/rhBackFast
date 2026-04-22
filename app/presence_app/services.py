"""Business logic for the presence/attendance module.

All HR calculations (ENTRY/EXIT decision, late detection, absence
computation, statistics) are centralized here so routes stay thin and
the rules are easy to audit.
"""
from __future__ import annotations

from datetime import date as _date
from datetime import datetime
from datetime import time as _time
from typing import Iterable, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.presence_app.constants import (
    DEFAULT_END_TIME,
    DEFAULT_START_TIME,
    ScanMethod,
    ScanType,
)
from app.presence_app.models import Presence, WorkSchedule
from app.user_app.models import User


class PresenceError(Exception):
    """Base class for presence service errors."""


class MaxScansReachedError(PresenceError):
    """Raised when a user tries to scan more than twice in the same day."""


class UserNotFoundError(PresenceError):
    """Raised when the target user does not exist."""


def _parse_time(value: str) -> _time:
    return datetime.strptime(value, "%H:%M:%S").time()


DEFAULT_SCHEDULE_START = _parse_time(DEFAULT_START_TIME)
DEFAULT_SCHEDULE_END = _parse_time(DEFAULT_END_TIME)


class WorkScheduleService:
    """Read helpers for :class:`WorkSchedule`."""

    @staticmethod
    async def get_effective_schedule(
        db: AsyncSession, user_id: int
    ) -> tuple[_time, _time, Optional[_time], Optional[_time]]:
        stmt = select(WorkSchedule).where(WorkSchedule.user_id == user_id)
        user_schedule = (await db.execute(stmt)).scalar_one_or_none()
        if user_schedule is not None:
            return (
                user_schedule.start_time,
                user_schedule.end_time,
                user_schedule.break_start,
                user_schedule.break_end,
            )

        default_stmt = select(WorkSchedule).where(WorkSchedule.user_id.is_(None))
        default_schedule = (await db.execute(default_stmt)).scalar_one_or_none()
        if default_schedule is not None:
            return (
                default_schedule.start_time,
                default_schedule.end_time,
                default_schedule.break_start,
                default_schedule.break_end,
            )

        return DEFAULT_SCHEDULE_START, DEFAULT_SCHEDULE_END, None, None


class PresenceService:
    """Presence and statistics business logic."""

    @classmethod
    async def register_scan(
        cls,
        db: AsyncSession,
        user_id: int,
        method: ScanMethod,
        scanned_at: Optional[datetime] = None,
    ) -> Presence:
        user = await db.get(User, user_id)
        if user is None:
            raise UserNotFoundError(f"User {user_id} introuvable")

        now = scanned_at or datetime.utcnow()
        scan_date = now.date()
        scan_time = now.time().replace(microsecond=0)

        stmt = (
            select(Presence)
            .where(
                and_(
                    Presence.user_id == user_id,
                    Presence.date_scan == scan_date,
                )
            )
            .order_by(Presence.heure_scan.asc())
        )
        existing = list((await db.execute(stmt)).scalars().all())

        if len(existing) >= 2:
            raise MaxScansReachedError(
                f"User {user_id} a déjà atteint le maximum de 2 scans pour {scan_date}"
            )

        has_entry = any(p.scan_type == ScanType.ENTRY.value for p in existing)
        has_exit = any(p.scan_type == ScanType.EXIT.value for p in existing)

        start_time, end_time, _bs, _be = await WorkScheduleService.get_effective_schedule(
            db, user_id
        )

        if has_entry and not has_exit:
            scan_type = ScanType.EXIT
            is_late = False
        elif not has_entry:
            if scan_time >= end_time:
                scan_type = ScanType.EXIT
                is_late = False
            else:
                scan_type = ScanType.ENTRY
                is_late = scan_time > start_time
        else:
            raise MaxScansReachedError(
                f"User {user_id} a déjà enregistré un EXIT sans ENTRY pour {scan_date}"
            )

        presence = Presence(
            user_id=user_id,
            date_scan=scan_date,
            heure_scan=scan_time,
            method=method.value,
            scan_type=scan_type.value,
            is_late=is_late,
        )
        db.add(presence)
        await db.flush()
        await db.refresh(presence)
        return presence

    @staticmethod
    async def list_presences(
        db: AsyncSession,
        skip: int = 0,
        limit: int = 100,
        user_id: Optional[int] = None,
        on_date: Optional[_date] = None,
    ) -> tuple[list[Presence], int]:
        base = select(Presence)
        count_stmt = select(func.count()).select_from(Presence)
        if user_id is not None:
            base = base.where(Presence.user_id == user_id)
            count_stmt = count_stmt.where(Presence.user_id == user_id)
        if on_date is not None:
            base = base.where(Presence.date_scan == on_date)
            count_stmt = count_stmt.where(Presence.date_scan == on_date)

        total = (await db.execute(count_stmt)).scalar() or 0
        stmt = (
            base.order_by(Presence.date_scan.desc(), Presence.heure_scan.desc())
            .offset(skip)
            .limit(limit)
        )
        items = list((await db.execute(stmt)).scalars().all())
        return items, total

    @staticmethod
    async def _distinct_user_ids_for_day(
        db: AsyncSession, day: _date, *, only_late: bool = False
    ) -> list[int]:
        stmt = select(Presence.user_id).where(Presence.date_scan == day).distinct()
        if only_late:
            stmt = stmt.where(
                and_(
                    Presence.scan_type == ScanType.ENTRY.value,
                    Presence.is_late.is_(True),
                )
            )
        rows = (await db.execute(stmt)).scalars().all()
        return sorted(int(r) for r in rows)

    @classmethod
    async def presence_today(cls, db: AsyncSession, day: _date) -> tuple[_date, list[int]]:
        user_ids = await cls._distinct_user_ids_for_day(db, day)
        return day, user_ids

    @classmethod
    async def late_today(cls, db: AsyncSession, day: _date) -> tuple[_date, list[int]]:
        user_ids = await cls._distinct_user_ids_for_day(db, day, only_late=True)
        return day, user_ids

    @classmethod
    async def absence_today(cls, db: AsyncSession, day: _date) -> tuple[_date, list[int]]:
        present_stmt = select(Presence.user_id).where(Presence.date_scan == day).distinct()
        present_ids = {int(r) for r in (await db.execute(present_stmt)).scalars().all()}
        active_stmt = select(User.id).where(User.is_active.is_(True))
        all_ids = {int(r) for r in (await db.execute(active_stmt)).scalars().all()}
        return day, sorted(all_ids - present_ids)

    @staticmethod
    def _iter_days(start: _date, end: _date) -> Iterable[_date]:
        from datetime import timedelta
        current = start
        while current <= end:
            yield current
            current += timedelta(days=1)

    @classmethod
    async def presence_range(cls, db, start, end):
        stmt = (
            select(Presence.date_scan, Presence.user_id)
            .where(and_(Presence.date_scan >= start, Presence.date_scan <= end))
            .distinct()
        )
        rows = (await db.execute(stmt)).all()
        per_day: dict = {d: set() for d in cls._iter_days(start, end)}
        for day, uid in rows:
            per_day.setdefault(day, set()).add(int(uid))
        return [(day, sorted(per_day[day])) for day in cls._iter_days(start, end)]

    @classmethod
    async def late_range(cls, db, start, end):
        stmt = (
            select(Presence.date_scan, Presence.user_id)
            .where(
                and_(
                    Presence.date_scan >= start,
                    Presence.date_scan <= end,
                    Presence.scan_type == ScanType.ENTRY.value,
                    Presence.is_late.is_(True),
                )
            )
            .distinct()
        )
        rows = (await db.execute(stmt)).all()
        per_day: dict = {d: set() for d in cls._iter_days(start, end)}
        for day, uid in rows:
            per_day.setdefault(day, set()).add(int(uid))
        return [(day, sorted(per_day[day])) for day in cls._iter_days(start, end)]

    @classmethod
    async def absence_range(cls, db, start, end):
        active_stmt = select(User.id).where(User.is_active.is_(True))
        all_ids = {int(r) for r in (await db.execute(active_stmt)).scalars().all()}
        presence_stmt = (
            select(Presence.date_scan, Presence.user_id)
            .where(and_(Presence.date_scan >= start, Presence.date_scan <= end))
            .distinct()
        )
        rows = (await db.execute(presence_stmt)).all()
        present_per_day: dict = {d: set() for d in cls._iter_days(start, end)}
        for day, uid in rows:
            present_per_day.setdefault(day, set()).add(int(uid))
        return [
            (day, sorted(all_ids - present_per_day[day]))
            for day in cls._iter_days(start, end)
        ]