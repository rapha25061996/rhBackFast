"""
Employee deduction management service.
"""
from decimal import Decimal
from typing import Dict, List
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from app.paie_app.models import RetenueEmploye, PeriodePaie


class DeductionManagerService:
    """Service for managing employee deductions"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_deduction(
        self, data: Dict, user=None
    ) -> RetenueEmploye:
        """Create a new deduction for an employee"""
        required_fields = [
            'employe_id', 'type_retenue', 'description',
            'montant_mensuel', 'date_debut'
        ]
        for field in required_fields:
            if field not in data:
                raise ValueError(f"Required field missing: {field}")

        retenue = RetenueEmploye(
            employe_id=data['employe_id'],
            type_retenue=data['type_retenue'],
            description=data['description'],
            montant_mensuel=Decimal(str(data['montant_mensuel'])),
            montant_total=(
                Decimal(str(data['montant_total']))
                if data.get('montant_total') else None
            ),
            date_debut=data['date_debut'],
            date_fin=data.get('date_fin'),
            est_active=data.get('est_active', True),
            est_recurrente=data.get('est_recurrente', True),
            cree_par_id=data.get('cree_par'),
            banque_beneficiaire=data.get('banque_beneficiaire', ''),
            compte_beneficiaire=data.get('compte_beneficiaire', '')
        )
        self.db.add(retenue)
        await self.db.commit()
        await self.db.refresh(retenue)

        # Track creation
        if user:
            from app.paie_app.services.modification_history_service import (
                ModificationHistoryService
            )
            new_values = ModificationHistoryService.extract_model_values(
                retenue
            )
            await ModificationHistoryService.track_retenue_modification(
                db=self.db,
                retenue=retenue,
                user=user,
                action="CREATE",
                new_values=new_values,
                reason="Deduction created"
            )

        return retenue

    async def get_active_deductions(
        self, employe_id: int, periode: PeriodePaie
    ) -> List[RetenueEmploye]:
        """Get active deductions for an employee at a given period"""
        reference_date = date(periode.annee, periode.mois, 1)

        result = await self.db.execute(
            select(RetenueEmploye).where(
                RetenueEmploye.employe_id == employe_id,
                RetenueEmploye.est_active.is_(True),
                RetenueEmploye.date_debut <= reference_date,
                or_(
                    RetenueEmploye.date_fin.is_(None),
                    RetenueEmploye.date_fin >= reference_date
                )
            )
        )
        retenues = result.scalars().all()

        active_retenues = []
        for retenue in retenues:
            if retenue.montant_total:
                restant = (
                    retenue.montant_total - retenue.montant_deja_deduit
                )
                if restant > 0:
                    active_retenues.append(retenue)
            else:
                active_retenues.append(retenue)

        return active_retenues

    async def apply_deduction(
        self, retenue: RetenueEmploye, periode: PeriodePaie
    ) -> Decimal:
        """Apply a deduction for a given period"""
        montant_a_deduire = retenue.montant_mensuel

        if retenue.montant_total:
            restant = retenue.montant_total - retenue.montant_deja_deduit
            if restant <= 0:
                return Decimal('0')
            montant_a_deduire = min(montant_a_deduire, restant)

        if montant_a_deduire <= 0:
            return Decimal('0')

        return montant_a_deduire

    async def update_deduction_balance(
        self, retenue_id: int, montant_deduit: Decimal, user=None
    ) -> None:
        """Update deduction balance after deduction"""
        result = await self.db.execute(
            select(RetenueEmploye).where(RetenueEmploye.id == retenue_id)
        )
        retenue = result.scalar_one_or_none()

        if not retenue:
            raise ValueError(f"Deduction {retenue_id} not found")

        # Track modification
        old_values = None
        if user:
            from app.paie_app.services.modification_history_service import (
                ModificationHistoryService
            )
            old_values = ModificationHistoryService.extract_model_values(
                retenue
            )

        retenue.montant_deja_deduit += montant_deduit

        if (retenue.montant_total and
                retenue.montant_deja_deduit >= retenue.montant_total):
            retenue.est_active = False

        await self.db.commit()
        await self.db.refresh(retenue)

        # Track modification
        if user:
            from app.paie_app.services.modification_history_service import (
                ModificationHistoryService
            )
            new_values = ModificationHistoryService.extract_model_values(
                retenue
            )
            await ModificationHistoryService.track_retenue_modification(
                db=self.db,
                retenue=retenue,
                user=user,
                action="APPLY",
                old_values=old_values,
                new_values=new_values,
                reason=f"Applied deduction: {montant_deduit}"
            )


