"""Business logic for the presence/attendance module.

All HR calculations (ENTRY/EXIT decision, late detection, absence
computation, statistics) are centralized here so routes stay thin and
the rules are easy to audit.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date as _date
from datetime import datetime
from datetime import time as _time
from typing import Iterable, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.query_utils import apply_expansion
from app.presence_app.constants import (
    DEFAULT_END_TIME,
    DEFAULT_START_TIME,
    ScanMethod,
    ScanType,
)
from app.presence_app.models import Presence, WorkSchedule
from app.user_app.models import User


@dataclass(frozen=True)
class LateEntry:
    """Per-user, per-day late information exposed to the routes layer."""

    user: "User"
    date_scan: _date
    heure_scan: _time
    scheduled_start: _time
    minutes_late: int


def _minutes_between(earlier: _time, later: _time) -> int:
    """Return the integer minute delta between two ``time`` instances.

    Negative deltas are clamped to 0 because late presence can only happen
    *after* the scheduled start.
    """
    anchor = datetime(2000, 1, 1)
    delta = datetime.combine(anchor.date(), later) - datetime.combine(anchor.date(), earlier)
    return max(0, int(delta.total_seconds() // 60))


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
    async def get_start_time_map(
        db: AsyncSession,
    ) -> tuple[dict[int, _time], _time]:
        """Return ``(per_user_start_time, default_start_time)``.

        Fetches every work schedule row once and builds:
          - ``per_user``: ``{user_id: start_time}`` for overrides.
          - ``default``: the global start time (row with ``user_id IS NULL``)
            or the hard-coded :data:`DEFAULT_SCHEDULE_START` when none exists.

        Used by late-statistics computations to avoid N+1 lookups.
        """
        stmt = select(WorkSchedule.user_id, WorkSchedule.start_time)
        rows = (await db.execute(stmt)).all()
        per_user: dict[int, _time] = {}
        default: _time = DEFAULT_SCHEDULE_START
        for user_id, start_time in rows:
            if user_id is None:
                default = start_time
            else:
                per_user[int(user_id)] = start_time
        return per_user, default

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
        expand_fields: Optional[list[str]] = None,
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
        if expand_fields:
            stmt = apply_expansion(stmt, Presence, expand_fields)
        items = list((await db.execute(stmt)).scalars().all())
        return items, total

    @staticmethod
    async def _load_users(
        db: AsyncSession,
        user_ids: list[int],
        expand_fields: Optional[list[str]] = None,
    ) -> list[User]:
        """Load :class:`User` rows for the given ids, preserving id order.

        Supports optional eager loading through the shared ``expand`` helper
        (same syntax accepted by every other module: ``employe``,
        ``employe.poste``, etc.).
        """
        if not user_ids:
            return []
        stmt = select(User).where(User.id.in_(user_ids))
        if expand_fields:
            stmt = apply_expansion(stmt, User, expand_fields)
        rows = list((await db.execute(stmt)).scalars().all())
        by_id = {u.id: u for u in rows}
        return [by_id[uid] for uid in user_ids if uid in by_id]

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
    async def presence_today(
        cls,
        db: AsyncSession,
        day: _date,
        expand_fields: Optional[list[str]] = None,
    ) -> tuple[_date, list[User]]:
        user_ids = await cls._distinct_user_ids_for_day(db, day)
        users = await cls._load_users(db, user_ids, expand_fields=expand_fields)
        return day, users

    @classmethod
    async def late_today(
        cls,
        db: AsyncSession,
        day: _date,
        expand_fields: Optional[list[str]] = None,
    ) -> tuple[_date, list[LateEntry]]:
        """Return the late ENTRY scans for ``day`` with their minute delta.

        Each user may have at most one ENTRY scan per day, so the returned
        list contains one :class:`LateEntry` per user who was late.
        """
        stmt = (
            select(Presence.user_id, Presence.heure_scan, Presence.date_scan)
            .where(
                and_(
                    Presence.date_scan == day,
                    Presence.scan_type == ScanType.ENTRY.value,
                    Presence.is_late.is_(True),
                )
            )
            .order_by(Presence.user_id.asc())
        )
        rows = list((await db.execute(stmt)).all())
        user_ids = sorted({int(r.user_id) for r in rows})
        users = await cls._load_users(db, user_ids, expand_fields=expand_fields)
        users_by_id = {u.id: u for u in users}

        per_user_starts, default_start = await WorkScheduleService.get_start_time_map(db)

        entries: list[LateEntry] = []
        for row in rows:
            uid = int(row.user_id)
            user = users_by_id.get(uid)
            if user is None:
                continue
            scheduled_start = per_user_starts.get(uid, default_start)
            entries.append(
                LateEntry(
                    user=user,
                    date_scan=row.date_scan,
                    heure_scan=row.heure_scan,
                    scheduled_start=scheduled_start,
                    minutes_late=_minutes_between(scheduled_start, row.heure_scan),
                )
            )
        entries.sort(key=lambda e: (-e.minutes_late, e.user.id))
        return day, entries

    @classmethod
    async def absence_today(
        cls,
        db: AsyncSession,
        day: _date,
        expand_fields: Optional[list[str]] = None,
    ) -> tuple[_date, list[User]]:
        present_stmt = select(Presence.user_id).where(Presence.date_scan == day).distinct()
        present_ids = {int(r) for r in (await db.execute(present_stmt)).scalars().all()}
        active_stmt = select(User.id).where(User.is_active.is_(True))
        all_ids = {int(r) for r in (await db.execute(active_stmt)).scalars().all()}
        ordered_ids = sorted(all_ids - present_ids)
        users = await cls._load_users(db, ordered_ids, expand_fields=expand_fields)
        return day, users

    @staticmethod
    def _iter_days(start: _date, end: _date) -> Iterable[_date]:
        from datetime import timedelta
        current = start
        while current <= end:
            yield current
            current += timedelta(days=1)

    @classmethod
    async def _resolve_range(
        cls,
        db: AsyncSession,
        per_day_ids: dict[_date, set[int]],
        start: _date,
        end: _date,
        expand_fields: Optional[list[str]] = None,
    ) -> list[tuple[_date, list[User]]]:
        # Fetch every user that appears at least once in the range in a single
        # query, then redistribute back by day. Keeps the statistics endpoints
        # O(unique_users) instead of O(days × users).
        all_ids = sorted({uid for ids in per_day_ids.values() for uid in ids})
        users = await cls._load_users(db, all_ids, expand_fields=expand_fields)
        users_by_id = {u.id: u for u in users}
        return [
            (
                day,
                [users_by_id[uid] for uid in sorted(per_day_ids.get(day, set())) if uid in users_by_id],
            )
            for day in cls._iter_days(start, end)
        ]

    @classmethod
    async def presence_range(
        cls,
        db,
        start,
        end,
        expand_fields: Optional[list[str]] = None,
    ):
        stmt = (
            select(Presence.date_scan, Presence.user_id)
            .where(and_(Presence.date_scan >= start, Presence.date_scan <= end))
            .distinct()
        )
        rows = (await db.execute(stmt)).all()
        per_day: dict = {d: set() for d in cls._iter_days(start, end)}
        for day, uid in rows:
            per_day.setdefault(day, set()).add(int(uid))
        return await cls._resolve_range(db, per_day, start, end, expand_fields=expand_fields)

    @classmethod
    async def late_range(
        cls,
        db: AsyncSession,
        start: _date,
        end: _date,
        expand_fields: Optional[list[str]] = None,
    ) -> list[tuple[_date, list[LateEntry]]]:
        """Return, per day in the range, the late ENTRY scans with minute delta."""
        stmt = (
            select(Presence.user_id, Presence.date_scan, Presence.heure_scan)
            .where(
                and_(
                    Presence.date_scan >= start,
                    Presence.date_scan <= end,
                    Presence.scan_type == ScanType.ENTRY.value,
                    Presence.is_late.is_(True),
                )
            )
            .order_by(Presence.date_scan.asc(), Presence.user_id.asc())
        )
        rows = list((await db.execute(stmt)).all())
        user_ids = sorted({int(r.user_id) for r in rows})
        users = await cls._load_users(db, user_ids, expand_fields=expand_fields)
        users_by_id = {u.id: u for u in users}

        per_user_starts, default_start = await WorkScheduleService.get_start_time_map(db)

        entries_per_day: dict[_date, list[LateEntry]] = {
            d: [] for d in cls._iter_days(start, end)
        }
        for row in rows:
            uid = int(row.user_id)
            user = users_by_id.get(uid)
            if user is None:
                continue
            scheduled_start = per_user_starts.get(uid, default_start)
            entries_per_day.setdefault(row.date_scan, []).append(
                LateEntry(
                    user=user,
                    date_scan=row.date_scan,
                    heure_scan=row.heure_scan,
                    scheduled_start=scheduled_start,
                    minutes_late=_minutes_between(scheduled_start, row.heure_scan),
                )
            )

        result: list[tuple[_date, list[LateEntry]]] = []
        for day in cls._iter_days(start, end):
            day_entries = entries_per_day.get(day, [])
            day_entries.sort(key=lambda e: (-e.minutes_late, e.user.id))
            result.append((day, day_entries))
        return result

    @classmethod
    async def absence_range(
        cls,
        db,
        start,
        end,
        expand_fields: Optional[list[str]] = None,
    ):
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
        per_day: dict = {
            day: all_ids - present_per_day.get(day, set())
            for day in cls._iter_days(start, end)
        }
        return await cls._resolve_range(db, per_day, start, end, expand_fields=expand_fields)