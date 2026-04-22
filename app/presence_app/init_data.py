"""Idempotent seed for the presence lookup tables.

Seeds :class:`~app.presence_app.models.PrAbsenceType` and
:class:`~app.presence_app.models.PrLateReasonType` with the canonical
values declared in :mod:`app.presence_app.constants`. Existing rows are
kept as-is (no label override) so that humans can freely rename them.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.presence_app.constants import AbsenceType, LateReasonType
from app.presence_app.models import PrAbsenceType, PrLateReasonType


ABSENCE_TYPE_LABELS: dict[str, str] = {
    AbsenceType.MALADIE.value: "Maladie",
    AbsenceType.URGENCE_FAMILIALE.value: "Urgence familiale",
    AbsenceType.DEUIL.value: "Deuil",
    AbsenceType.ENFANT_MALADE.value: "Enfant malade",
    AbsenceType.RDV_MEDICAL.value: "Rendez-vous médical",
    AbsenceType.AUTRE.value: "Autre",
}


LATE_REASON_LABELS: dict[str, str] = {
    LateReasonType.TRANSPORT.value: "Transport",
    LateReasonType.FAMILIAL.value: "Familial",
    LateReasonType.MEDICAL.value: "Médical",
    LateReasonType.AUTRE.value: "Autre",
}


async def seed_presence_lookups(session: AsyncSession) -> None:
    """Ensure every canonical absence/late-reason type exists in DB."""
    existing_abs = {
        row.code
        for row in (await session.execute(select(PrAbsenceType))).scalars().all()
    }
    new_abs = [
        PrAbsenceType(code=code, label=label, is_active=True)
        for code, label in ABSENCE_TYPE_LABELS.items()
        if code not in existing_abs
    ]
    if new_abs:
        session.add_all(new_abs)

    existing_late = {
        row.code
        for row in (await session.execute(select(PrLateReasonType))).scalars().all()
    }
    new_late = [
        PrLateReasonType(code=code, label=label, is_active=True)
        for code, label in LATE_REASON_LABELS.items()
        if code not in existing_late
    ]
    if new_late:
        session.add_all(new_late)

    if new_abs or new_late:
        await session.commit()
