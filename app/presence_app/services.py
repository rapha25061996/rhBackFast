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
from app.presence_app.models import (
    AbsenceDeclaration,
    LateDeclaration,
    Presence,
    PrAbsenceType,
    PrLateReasonType,
    WorkSchedule,
)
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


class DeclarationNotFoundError(PresenceError):
    """Raised when a declaration cannot be loaded."""


class DeclarationStateError(PresenceError):
    """Raised when a declaration cannot transition to the requested state."""


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

class PrAbsenceTypeService:
    """CRUD helpers for :class:`PrAbsenceType`."""

    @staticmethod
    async def create(
        db: AsyncSession,
        *,
        code: str,
        label: str,
        description: Optional[str] = None,
        is_active: bool = True,
    ) -> PrAbsenceType:
        row = PrAbsenceType(
            code=code,
            label=label,
            description=description,
            is_active=is_active,
        )
        db.add(row)
        await db.flush()
        await db.refresh(row)
        return row

    @staticmethod
    async def get(db: AsyncSession, type_id: int) -> PrAbsenceType:
        row = await db.get(PrAbsenceType, type_id)
        if row is None:
            raise DeclarationNotFoundError(
                f"PrAbsenceType {type_id} introuvable"
            )
        return row

    @staticmethod
    async def get_by_code(db: AsyncSession, code: str) -> Optional[PrAbsenceType]:
        stmt = select(PrAbsenceType).where(PrAbsenceType.code == code)
        return (await db.execute(stmt)).scalar_one_or_none()

    @staticmethod
    async def list(
        db: AsyncSession,
        *,
        skip: int = 0,
        limit: int = 100,
        is_active: Optional[bool] = None,
    ) -> tuple[list[PrAbsenceType], int]:
        base = select(PrAbsenceType)
        count_stmt = select(func.count()).select_from(PrAbsenceType)
        if is_active is not None:
            base = base.where(PrAbsenceType.is_active.is_(is_active))
            count_stmt = count_stmt.where(PrAbsenceType.is_active.is_(is_active))
        total = (await db.execute(count_stmt)).scalar() or 0
        stmt = base.order_by(PrAbsenceType.code.asc()).offset(skip).limit(limit)
        items = list((await db.execute(stmt)).scalars().all())
        return items, total

    @staticmethod
    async def update(
        db: AsyncSession,
        type_id: int,
        *,
        code: Optional[str] = None,
        label: Optional[str] = None,
        description: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> PrAbsenceType:
        row = await PrAbsenceTypeService.get(db, type_id)
        if code is not None:
            row.code = code
        if label is not None:
            row.label = label
        if description is not None:
            row.description = description
        if is_active is not None:
            row.is_active = is_active
        await db.flush()
        await db.refresh(row)
        return row

    @staticmethod
    async def delete(db: AsyncSession, type_id: int) -> None:
        row = await PrAbsenceTypeService.get(db, type_id)
        await db.delete(row)
        await db.flush()


class PrLateReasonTypeService:
    """CRUD helpers for :class:`PrLateReasonType`."""

    @staticmethod
    async def create(
        db: AsyncSession,
        *,
        code: str,
        label: str,
        description: Optional[str] = None,
        is_active: bool = True,
    ) -> PrLateReasonType:
        row = PrLateReasonType(
            code=code,
            label=label,
            description=description,
            is_active=is_active,
        )
        db.add(row)
        await db.flush()
        await db.refresh(row)
        return row

    @staticmethod
    async def get(db: AsyncSession, type_id: int) -> PrLateReasonType:
        row = await db.get(PrLateReasonType, type_id)
        if row is None:
            raise DeclarationNotFoundError(
                f"PrLateReasonType {type_id} introuvable"
            )
        return row

    @staticmethod
    async def get_by_code(db: AsyncSession, code: str) -> Optional[PrLateReasonType]:
        stmt = select(PrLateReasonType).where(PrLateReasonType.code == code)
        return (await db.execute(stmt)).scalar_one_or_none()

    @staticmethod
    async def list(
        db: AsyncSession,
        *,
        skip: int = 0,
        limit: int = 100,
        is_active: Optional[bool] = None,
    ) -> tuple[list[PrLateReasonType], int]:
        base = select(PrLateReasonType)
        count_stmt = select(func.count()).select_from(PrLateReasonType)
        if is_active is not None:
            base = base.where(PrLateReasonType.is_active.is_(is_active))
            count_stmt = count_stmt.where(PrLateReasonType.is_active.is_(is_active))
        total = (await db.execute(count_stmt)).scalar() or 0
        stmt = base.order_by(PrLateReasonType.code.asc()).offset(skip).limit(limit)
        items = list((await db.execute(stmt)).scalars().all())
        return items, total

    @staticmethod
    async def update(
        db: AsyncSession,
        type_id: int,
        *,
        code: Optional[str] = None,
        label: Optional[str] = None,
        description: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> PrLateReasonType:
        row = await PrLateReasonTypeService.get(db, type_id)
        if code is not None:
            row.code = code
        if label is not None:
            row.label = label
        if description is not None:
            row.description = description
        if is_active is not None:
            row.is_active = is_active
        await db.flush()
        await db.refresh(row)
        return row

    @staticmethod
    async def delete(db: AsyncSession, type_id: int) -> None:
        row = await PrLateReasonTypeService.get(db, type_id)
        await db.delete(row)
        await db.flush()


class AbsenceDeclarationService:
    """CRUD helpers for :class:`AbsenceDeclaration`."""

    @staticmethod
    async def create(
        db: AsyncSession,
        *,
        user_id: int,
        absence_type_id: int,
        date_debut: _date,
        date_fin: Optional[_date] = None,
        reason: Optional[str] = None,
        justificatif_url: Optional[str] = None,
    ) -> AbsenceDeclaration:
        user = await db.get(User, user_id)
        if user is None:
            raise UserNotFoundError(f"User {user_id} introuvable")
        type_row = await db.get(PrAbsenceType, absence_type_id)
        if type_row is None:
            raise DeclarationNotFoundError(
                f"PrAbsenceType {absence_type_id} introuvable"
            )
        if date_fin is not None and date_fin < date_debut:
            raise DeclarationStateError("date_fin doit être >= date_debut")
        decl = AbsenceDeclaration(
            user_id=user_id,
            absence_type_id=absence_type_id,
            date_debut=date_debut,
            date_fin=date_fin,
            reason=reason,
            justificatif_url=justificatif_url,
        )
        db.add(decl)
        await db.flush()
        await db.refresh(decl)
        return decl

    @staticmethod
    async def get(
        db: AsyncSession,
        declaration_id: int,
        *,
        expand_fields: Optional[list[str]] = None,
    ) -> AbsenceDeclaration:
        stmt = select(AbsenceDeclaration).where(AbsenceDeclaration.id == declaration_id)
        if expand_fields:
            stmt = apply_expansion(stmt, AbsenceDeclaration, expand_fields)
        row = (await db.execute(stmt)).scalar_one_or_none()
        if row is None:
            raise DeclarationNotFoundError(
                f"AbsenceDeclaration {declaration_id} introuvable"
            )
        return row

    @staticmethod
    async def list(
        db: AsyncSession,
        *,
        skip: int = 0,
        limit: int = 100,
        user_id: Optional[int] = None,
        absence_type_id: Optional[int] = None,
        start: Optional[_date] = None,
        end: Optional[_date] = None,
        expand_fields: Optional[list[str]] = None,
    ) -> tuple[list[AbsenceDeclaration], int]:
        base = select(AbsenceDeclaration)
        count_stmt = select(func.count()).select_from(AbsenceDeclaration)
        clauses = []
        if user_id is not None:
            clauses.append(AbsenceDeclaration.user_id == user_id)
        if absence_type_id is not None:
            clauses.append(AbsenceDeclaration.absence_type_id == absence_type_id)
        if start is not None:
            # Declaration covers [date_debut, COALESCE(date_fin, date_debut)]
            clauses.append(
                func.coalesce(AbsenceDeclaration.date_fin, AbsenceDeclaration.date_debut)
                >= start
            )
        if end is not None:
            clauses.append(AbsenceDeclaration.date_debut <= end)
        if clauses:
            base = base.where(and_(*clauses))
            count_stmt = count_stmt.where(and_(*clauses))
        total = (await db.execute(count_stmt)).scalar() or 0
        stmt = (
            base.order_by(
                AbsenceDeclaration.date_debut.desc(),
                AbsenceDeclaration.id.desc(),
            )
            .offset(skip)
            .limit(limit)
        )
        if expand_fields:
            stmt = apply_expansion(stmt, AbsenceDeclaration, expand_fields)
        items = list((await db.execute(stmt)).scalars().all())
        return items, total

    @staticmethod
    async def update(
        db: AsyncSession,
        declaration_id: int,
        *,
        date_debut: Optional[_date] = None,
        date_fin: Optional[_date] = None,
        absence_type_id: Optional[int] = None,
        reason: Optional[str] = None,
        justificatif_url: Optional[str] = None,
        clear_date_fin: bool = False,
        clear_justificatif: bool = False,
    ) -> AbsenceDeclaration:
        decl = await AbsenceDeclarationService.get(db, declaration_id)
        if date_debut is not None:
            decl.date_debut = date_debut
        if clear_date_fin:
            decl.date_fin = None
        elif date_fin is not None:
            decl.date_fin = date_fin
        if decl.date_fin is not None and decl.date_fin < decl.date_debut:
            raise DeclarationStateError("date_fin doit être >= date_debut")
        if absence_type_id is not None:
            type_row = await db.get(PrAbsenceType, absence_type_id)
            if type_row is None:
                raise DeclarationNotFoundError(
                    f"PrAbsenceType {absence_type_id} introuvable"
                )
            decl.absence_type_id = absence_type_id
        if reason is not None:
            decl.reason = reason
        if clear_justificatif:
            decl.justificatif_url = None
        elif justificatif_url is not None:
            decl.justificatif_url = justificatif_url
        await db.flush()
        await db.refresh(decl)
        return decl

    @staticmethod
    async def delete(db: AsyncSession, declaration_id: int) -> None:
        decl = await AbsenceDeclarationService.get(db, declaration_id)
        await db.delete(decl)
        await db.flush()


class LateDeclarationService:
    """CRUD helpers for :class:`LateDeclaration`."""

    @staticmethod
    async def create(
        db: AsyncSession,
        *,
        user_id: int,
        reason_type_id: int,
        date_retard: _date,
        expected_arrival_time: Optional[_time] = None,
        reason: Optional[str] = None,
    ) -> LateDeclaration:
        user = await db.get(User, user_id)
        if user is None:
            raise UserNotFoundError(f"User {user_id} introuvable")
        type_row = await db.get(PrLateReasonType, reason_type_id)
        if type_row is None:
            raise DeclarationNotFoundError(
                f"PrLateReasonType {reason_type_id} introuvable"
            )
        decl = LateDeclaration(
            user_id=user_id,
            reason_type_id=reason_type_id,
            date_retard=date_retard,
            expected_arrival_time=expected_arrival_time,
            reason=reason,
        )
        db.add(decl)
        await db.flush()
        await db.refresh(decl)
        return decl

    @staticmethod
    async def get(
        db: AsyncSession,
        declaration_id: int,
        *,
        expand_fields: Optional[list[str]] = None,
    ) -> LateDeclaration:
        stmt = select(LateDeclaration).where(LateDeclaration.id == declaration_id)
        if expand_fields:
            stmt = apply_expansion(stmt, LateDeclaration, expand_fields)
        row = (await db.execute(stmt)).scalar_one_or_none()
        if row is None:
            raise DeclarationNotFoundError(
                f"LateDeclaration {declaration_id} introuvable"
            )
        return row

    @staticmethod
    async def list(
        db: AsyncSession,
        *,
        skip: int = 0,
        limit: int = 100,
        user_id: Optional[int] = None,
        reason_type_id: Optional[int] = None,
        start: Optional[_date] = None,
        end: Optional[_date] = None,
        expand_fields: Optional[list[str]] = None,
    ) -> tuple[list[LateDeclaration], int]:
        base = select(LateDeclaration)
        count_stmt = select(func.count()).select_from(LateDeclaration)
        clauses = []
        if user_id is not None:
            clauses.append(LateDeclaration.user_id == user_id)
        if reason_type_id is not None:
            clauses.append(LateDeclaration.reason_type_id == reason_type_id)
        if start is not None:
            clauses.append(LateDeclaration.date_retard >= start)
        if end is not None:
            clauses.append(LateDeclaration.date_retard <= end)
        if clauses:
            base = base.where(and_(*clauses))
            count_stmt = count_stmt.where(and_(*clauses))
        total = (await db.execute(count_stmt)).scalar() or 0
        stmt = (
            base.order_by(
                LateDeclaration.date_retard.desc(),
                LateDeclaration.id.desc(),
            )
            .offset(skip)
            .limit(limit)
        )
        if expand_fields:
            stmt = apply_expansion(stmt, LateDeclaration, expand_fields)
        items = list((await db.execute(stmt)).scalars().all())
        return items, total

    @staticmethod
    async def update(
        db: AsyncSession,
        declaration_id: int,
        *,
        date_retard: Optional[_date] = None,
        expected_arrival_time: Optional[_time] = None,
        reason_type_id: Optional[int] = None,
        reason: Optional[str] = None,
    ) -> LateDeclaration:
        decl = await LateDeclarationService.get(db, declaration_id)
        if date_retard is not None:
            decl.date_retard = date_retard
        if expected_arrival_time is not None:
            decl.expected_arrival_time = expected_arrival_time
        if reason_type_id is not None:
            type_row = await db.get(PrLateReasonType, reason_type_id)
            if type_row is None:
                raise DeclarationNotFoundError(
                    f"PrLateReasonType {reason_type_id} introuvable"
                )
            decl.reason_type_id = reason_type_id
        if reason is not None:
            decl.reason = reason
        await db.flush()
        await db.refresh(decl)
        return decl

    @staticmethod
    async def delete(db: AsyncSession, declaration_id: int) -> None:
        decl = await LateDeclarationService.get(db, declaration_id)
        await db.delete(decl)
        await db.flush()


# ---------------------------------------------------------------------------
# Global statistics
# ---------------------------------------------------------------------------


class GlobalStatsService:
    """Aggregate per-user statistics for a date range.

    Combines raw presence/late scans with user-filed absence and late
    declarations to compute:

      - presence_count             — days with at least one ENTRY scan
      - absence_total_count        — days without any scan in the range
      - absence_justified_count    — subset covered by an absence declaration
      - absence_unjustified_count  — absence_total_count - absence_justified
      - late_total_count           — late ENTRY scans in the range
      - late_declared_count        — late scans matched by a late declaration
      - late_undeclared_count      — late_total_count - late_declared_count
      - total_minutes_late         — sum of minute deltas for late scans

    Declarations have no approval workflow: any stored declaration
    contributes to the justified / declared counters as long as the
    corresponding day falls in the requested range.
    """

    @staticmethod
    async def _active_user_ids(
        db: AsyncSession, *, user_id: Optional[int] = None
    ) -> list[int]:
        stmt = select(User.id).where(User.is_active.is_(True))
        if user_id is not None:
            stmt = stmt.where(User.id == user_id)
        rows = (await db.execute(stmt)).scalars().all()
        return sorted(int(r) for r in rows)

    @classmethod
    async def _load_raw(
        cls,
        db: AsyncSession,
        *,
        start: _date,
        end: _date,
        user_id: Optional[int] = None,
    ) -> tuple[
        list[int],
        dict[int, set[_date]],
        dict[int, dict[_date, int]],
        dict[int, set[_date]],
        dict[int, set[_date]],
        list[_date],
    ]:
        """Load all raw data needed for both compute() and compute_detailed().

        Returns:
            ``(ordered_user_ids, presence_days, late_minutes_by_day,
               justified_days, declared_late_days, all_days)``.

            ``late_minutes_by_day[uid][date]`` holds the aggregated minutes
            late for that user/day (sum across multiple ENTRY scans, though
            in practice there is at most one).
        """
        from datetime import timedelta

        ordered_user_ids = await cls._active_user_ids(db, user_id=user_id)
        if not ordered_user_ids:
            return [], {}, {}, {}, {}, []
        user_id_set = set(ordered_user_ids)

        scan_stmt = select(
            Presence.user_id,
            Presence.date_scan,
            Presence.heure_scan,
            Presence.is_late,
        ).where(
            and_(
                Presence.date_scan >= start,
                Presence.date_scan <= end,
                Presence.scan_type == ScanType.ENTRY.value,
            )
        )
        if user_id is not None:
            scan_stmt = scan_stmt.where(Presence.user_id == user_id)
        scan_rows = list((await db.execute(scan_stmt)).all())

        per_user_starts, default_start = await WorkScheduleService.get_start_time_map(db)

        presence_days: dict[int, set[_date]] = {
            uid: set() for uid in ordered_user_ids
        }
        late_minutes_by_day: dict[int, dict[_date, int]] = {
            uid: {} for uid in ordered_user_ids
        }
        for row in scan_rows:
            uid = int(row.user_id)
            if uid not in user_id_set:
                continue
            presence_days[uid].add(row.date_scan)
            if bool(row.is_late):
                scheduled_start = per_user_starts.get(uid, default_start)
                minutes = _minutes_between(scheduled_start, row.heure_scan)
                late_minutes_by_day[uid][row.date_scan] = (
                    late_minutes_by_day[uid].get(row.date_scan, 0) + minutes
                )

        abs_stmt = select(AbsenceDeclaration).where(
            and_(
                AbsenceDeclaration.date_debut <= end,
                func.coalesce(
                    AbsenceDeclaration.date_fin, AbsenceDeclaration.date_debut
                )
                >= start,
            )
        )
        if user_id is not None:
            abs_stmt = abs_stmt.where(AbsenceDeclaration.user_id == user_id)
        abs_rows = list((await db.execute(abs_stmt)).scalars().all())

        justified_days: dict[int, set[_date]] = {
            uid: set() for uid in ordered_user_ids
        }
        for decl in abs_rows:
            uid = int(decl.user_id)
            if uid not in user_id_set:
                continue
            effective_end = (
                decl.date_fin if decl.date_fin is not None else decl.date_debut
            )
            d = max(decl.date_debut, start)
            last = min(effective_end, end)
            while d <= last:
                justified_days[uid].add(d)
                d += timedelta(days=1)

        late_decl_stmt = select(
            LateDeclaration.user_id, LateDeclaration.date_retard
        ).where(
            and_(
                LateDeclaration.date_retard >= start,
                LateDeclaration.date_retard <= end,
            )
        )
        if user_id is not None:
            late_decl_stmt = late_decl_stmt.where(
                LateDeclaration.user_id == user_id
            )
        late_decl_rows = list((await db.execute(late_decl_stmt)).all())

        declared_late_days: dict[int, set[_date]] = {
            uid: set() for uid in ordered_user_ids
        }
        for row in late_decl_rows:
            uid = int(row.user_id)
            if uid not in user_id_set:
                continue
            declared_late_days[uid].add(row.date_retard)

        all_days: list[_date] = []
        cursor = start
        while cursor <= end:
            all_days.append(cursor)
            cursor += timedelta(days=1)

        return (
            ordered_user_ids,
            presence_days,
            late_minutes_by_day,
            justified_days,
            declared_late_days,
            all_days,
        )

    @staticmethod
    def _empty_counters() -> dict[str, int]:
        return {
            "presence_count": 0,
            "absence_total_count": 0,
            "absence_justified_count": 0,
            "absence_unjustified_count": 0,
            "late_total_count": 0,
            "late_declared_count": 0,
            "late_undeclared_count": 0,
            "total_minutes_late": 0,
        }

    @staticmethod
    async def _load_users(
        db: AsyncSession,
        user_ids: list[int],
        *,
        expand_fields: Optional[list[str]] = None,
    ) -> dict[int, "User"]:
        if not user_ids:
            return {}
        users_stmt = select(User).where(User.id.in_(user_ids))
        if expand_fields:
            users_stmt = apply_expansion(users_stmt, User, expand_fields)
        users = list((await db.execute(users_stmt)).scalars().all())
        return {u.id: u for u in users}

    @classmethod
    async def compute(
        cls,
        db: AsyncSession,
        *,
        start: _date,
        end: _date,
        user_id: Optional[int] = None,
        expand_fields: Optional[list[str]] = None,
    ) -> tuple[list[int], dict[int, dict[str, int]], dict[int, "User"]]:
        """Return ``(ordered_user_ids, stats_by_user, users_by_id)``."""
        (
            ordered_user_ids,
            presence_days,
            late_minutes_by_day,
            justified_days,
            declared_late_days,
            all_days,
        ) = await cls._load_raw(db, start=start, end=end, user_id=user_id)
        if not ordered_user_ids:
            return [], {}, {}

        total_days = len(all_days)
        all_days_set = set(all_days)
        stats: dict[int, dict[str, int]] = {
            uid: cls._empty_counters() for uid in ordered_user_ids
        }
        for uid in ordered_user_ids:
            present = presence_days[uid]
            justified = justified_days[uid]
            declared_late = declared_late_days[uid]
            minutes_by_day = late_minutes_by_day[uid]

            absences = total_days - len(present)
            absent_days_set = all_days_set - present
            justified_absent = len(justified & absent_days_set)
            late_total = len(minutes_by_day)
            declared_late_matches = sum(
                1 for d in minutes_by_day if d in declared_late
            )
            total_minutes = sum(minutes_by_day.values())

            stats[uid]["presence_count"] = len(present)
            stats[uid]["absence_total_count"] = absences
            stats[uid]["absence_justified_count"] = justified_absent
            stats[uid]["absence_unjustified_count"] = absences - justified_absent
            stats[uid]["late_total_count"] = late_total
            stats[uid]["late_declared_count"] = declared_late_matches
            stats[uid]["late_undeclared_count"] = late_total - declared_late_matches
            stats[uid]["total_minutes_late"] = total_minutes

        users_by_id = await cls._load_users(
            db, ordered_user_ids, expand_fields=expand_fields
        )
        return ordered_user_ids, stats, users_by_id

    @classmethod
    async def compute_detailed(
        cls,
        db: AsyncSession,
        *,
        start: _date,
        end: _date,
        user_id: Optional[int] = None,
        include_users: bool = True,
        expand_fields: Optional[list[str]] = None,
    ) -> tuple[
        list[_date],
        dict[_date, dict[str, int]],
        dict[_date, dict[int, dict[str, int]]],
        list[int],
        dict[int, "User"],
    ]:
        """Day-by-day breakdown of the same counters exposed by :meth:`compute`.

        Returns ``(all_days, totals_by_day, per_user_by_day,
        users_in_response, users_by_id)``.

        ``per_user_by_day[date]`` only contains entries for users with at
        least one non-zero counter that day (keeps the yearly payload
        manageable). ``users_in_response`` is the ordered set of users
        actually referenced across all days.
        """
        (
            ordered_user_ids,
            presence_days,
            late_minutes_by_day,
            justified_days,
            declared_late_days,
            all_days,
        ) = await cls._load_raw(db, start=start, end=end, user_id=user_id)

        totals_by_day: dict[_date, dict[str, int]] = {
            d: cls._empty_counters() for d in all_days
        }
        per_user_by_day: dict[_date, dict[int, dict[str, int]]] = {
            d: {} for d in all_days
        }
        referenced_users: set[int] = set()

        for uid in ordered_user_ids:
            present = presence_days[uid]
            justified = justified_days[uid]
            declared_late = declared_late_days[uid]
            minutes_by_day = late_minutes_by_day[uid]

            for d in all_days:
                is_present = d in present
                is_absent = not is_present
                is_justified = is_absent and d in justified
                minutes = minutes_by_day.get(d, 0)
                is_late_scan = d in minutes_by_day
                is_declared_late = is_late_scan and d in declared_late

                day_counters = {
                    "presence_count": 1 if is_present else 0,
                    "absence_total_count": 1 if is_absent else 0,
                    "absence_justified_count": 1 if is_justified else 0,
                    "absence_unjustified_count": 1
                    if (is_absent and not is_justified)
                    else 0,
                    "late_total_count": 1 if is_late_scan else 0,
                    "late_declared_count": 1 if is_declared_late else 0,
                    "late_undeclared_count": 1
                    if (is_late_scan and not is_declared_late)
                    else 0,
                    "total_minutes_late": minutes,
                }

                totals = totals_by_day[d]
                for key, val in day_counters.items():
                    totals[key] += val

                if include_users and any(v > 0 for v in day_counters.values()):
                    per_user_by_day[d][uid] = day_counters
                    referenced_users.add(uid)

        if include_users:
            users_in_response = [
                uid for uid in ordered_user_ids if uid in referenced_users
            ]
            users_by_id = await cls._load_users(
                db, users_in_response, expand_fields=expand_fields
            )
        else:
            users_in_response = []
            users_by_id = {}

        return all_days, totals_by_day, per_user_by_day, users_in_response, users_by_id
