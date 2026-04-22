"""
Period processing service.
"""
from decimal import Decimal
from typing import Dict, List
from datetime import date, datetime
from calendar import monthrange
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.paie_app.constants import PeriodeStatutTexte
from app.paie_app.models import PeriodePaie, EntreePaie
from app.paie_app.services.salary_calculator import SalaryCalculatorService
from app.user_app.models import Employe, Contrat


class PeriodProcessorService:
    """Service for processing payroll periods"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.salary_calculator = SalaryCalculatorService(db)

    async def create_period(
        self, annee: int, mois: int, user_id: int
    ) -> PeriodePaie:
        """Create a new payroll period with automatic date calculation"""
        # Check if period already exists
        result = await self.db.execute(
            select(PeriodePaie).where(
                PeriodePaie.annee == annee,
                PeriodePaie.mois == mois
            )
        )
        existing_period = result.scalar_one_or_none()

        if existing_period:
            raise ValueError(
                f"A period already exists for {mois}/{annee}"
            )

        # Calculate dates automatically
        date_debut = date(annee, mois, 1)
        _, last_day = monthrange(annee, mois)
        date_fin = date(annee, mois, last_day)

        # Create period
        periode = PeriodePaie(
            annee=annee,
            mois=mois,
            date_debut=date_debut,
            date_fin=date_fin,
            statut=PeriodeStatutTexte.DRAFT.value,
            traite_par_id=user_id
        )
        self.db.add(periode)
        await self.db.commit()
        await self.db.refresh(periode)

        return periode

    async def process_period(self, periode_id: int) -> Dict:
        """Process a payroll period by calculating salaries"""
        # Get period
        result = await self.db.execute(
            select(PeriodePaie).where(PeriodePaie.id == periode_id)
        )
        periode = result.scalar_one_or_none()
        if not periode:
            raise ValueError(f"Period {periode_id} not found")

        if periode.statut != PeriodeStatutTexte.DRAFT.value:
            raise ValueError(
                f"Period {periode_id} cannot be processed"
            )

        # Get active employees with contracts
        result = await self.db.execute(
            select(Employe).where(Employe.statut_emploi == 'ACTIVE')
        )
        employes = result.scalars().all()

        employes_actifs = []
        for emp in employes:
            result = await self.db.execute(
                select(Contrat).where(
                    Contrat.employe_id == emp.id,
                    Contrat.is_active.is_(True)
                )
            )
            contrat_actif = result.scalar_one_or_none()
            if contrat_actif:
                employes_actifs.append(emp)

        # Processing results
        results = {
            'periode_id': periode_id,
            'employes_traites': 0,
            'employes_erreurs': 0,
            'total_salaire_brut': Decimal('0'),
            'total_salaire_net': Decimal('0'),
            'erreurs': []
        }

        # Process each employee
        for emp in employes_actifs:
            try:
                salary_data = await (
                    self.salary_calculator.calculate_salary(
                        emp.id, periode_id
                    )
                )

                # Create or update payroll entry
                result = await self.db.execute(
                    select(EntreePaie).where(
                        EntreePaie.employe_id == emp.id,
                        EntreePaie.periode_paie_id == periode_id
                    )
                )
                entree = result.scalar_one_or_none()

                if entree:
                    # Track modification
                    from app.paie_app.services.modification_history_service import (
                        ModificationHistoryService
                    )
                    from app.user_app.models import User

                    old_values = ModificationHistoryService.extract_model_values(entree)

                    entree.salaire_base = salary_data['salaire_base']
                    entree.salaire_brut = salary_data['salaire_brut']
                    entree.salaire_net = salary_data['salaire_net']
                    entree.calculated_at = datetime.utcnow()
                    entree.calculated_by_id = periode.traite_par_id

                    # Get user for tracking
                    if periode.traite_par_id:
                        user_result = await self.db.execute(
                            select(User).where(User.id == periode.traite_par_id)
                        )
                        user = user_result.scalar_one_or_none()
                        if user:
                            new_values = ModificationHistoryService.extract_model_values(entree)
                            await ModificationHistoryService.track_entree_modification(
                                db=self.db,
                                entree=entree,
                                user=user,
                                action="RECALCULATE",
                                old_values=old_values,
                                new_values=new_values,
                                reason=f"Period {periode_id} processing"
                            )
                else:
                    entree = EntreePaie(
                        employe_id=emp.id,
                        periode_paie_id=periode_id,
                        salaire_base=salary_data['salaire_base'],
                        salaire_brut=salary_data['salaire_brut'],
                        salaire_net=salary_data['salaire_net'],
                        calculated_at=datetime.utcnow(),
                        calculated_by_id=periode.traite_par_id
                    )
                    self.db.add(entree)

                    # Track creation
                    from app.paie_app.services.modification_history_service import (
                        ModificationHistoryService
                    )
                    from app.user_app.models import User

                    if periode.traite_par_id:
                        user_result = await self.db.execute(
                            select(User).where(User.id == periode.traite_par_id)
                        )
                        user = user_result.scalar_one_or_none()
                        if user:
                            await self.db.flush()  # Ensure entree has an ID
                            new_values = ModificationHistoryService.extract_model_values(entree)
                            await ModificationHistoryService.track_entree_modification(
                                db=self.db,
                                entree=entree,
                                user=user,
                                action="CREATE",
                                new_values=new_values,
                                reason=f"Period {periode_id} processing"
                            )

                results['employes_traites'] += 1
                results['total_salaire_brut'] += salary_data['salaire_brut']
                results['total_salaire_net'] += salary_data['salaire_net']

            except Exception as e:
                results['employes_erreurs'] += 1
                results['erreurs'].append({
                    'employe_id': emp.id,
                    'erreur': str(e)
                })

        # Update period
        periode.masse_salariale_brute = results['total_salaire_brut']
        periode.total_net_a_payer = results['total_salaire_net']
        periode.nombre_employes = results['employes_traites']
        periode.statut = (
            PeriodeStatutTexte.COMPLETED.value
            if results['employes_erreurs'] == 0
            else PeriodeStatutTexte.PROCESSING.value
        )

        await self.db.commit()
        await self.db.refresh(periode)

        return results

    async def validate_period(self, periode_id: int) -> List[str]:
        """Validate a payroll period and return list of errors"""
        errors = []

        # Get period
        result = await self.db.execute(
            select(PeriodePaie).where(PeriodePaie.id == periode_id)
        )
        periode = result.scalar_one_or_none()

        if not periode:
            errors.append(f"Period {periode_id} not found")
            return errors

        if periode.statut == PeriodeStatutTexte.DRAFT.value:
            errors.append("Period has not been processed yet")
            return errors

        # Check payroll entries
        result = await self.db.execute(
            select(EntreePaie).where(
                EntreePaie.periode_paie_id == periode_id
            )
        )
        entrees = result.scalars().all()

        if not entrees:
            errors.append("No payroll entries found")

        return errors

    async def finalize_period(self, periode_id: int) -> bool:
        """Finalize a payroll period after validation"""
        # Get period
        result = await self.db.execute(
            select(PeriodePaie).where(PeriodePaie.id == periode_id)
        )
        periode = result.scalar_one_or_none()

        if not periode:
            raise ValueError(f"Period {periode_id} not found")

        # Validate
        errors = await self.validate_period(periode_id)
        if errors:
            error_msg = f"Cannot finalize: {', '.join(errors)}"
            raise ValueError(error_msg)

        periode.statut = PeriodeStatutTexte.FINALIZED.value
        await self.db.commit()
        await self.db.refresh(periode)

        return True

    async def approve_period(
        self, periode_id: int, user_id: int
    ) -> bool:
        """Approve a finalized payroll period"""
        # Get period
        result = await self.db.execute(
            select(PeriodePaie).where(PeriodePaie.id == periode_id)
        )
        periode = result.scalar_one_or_none()

        if not periode:
            raise ValueError(f"Period {periode_id} not found")

        if periode.statut != PeriodeStatutTexte.FINALIZED.value:
            raise ValueError(
                "Period must be finalized before approval"
            )

        periode.statut = PeriodeStatutTexte.APPROVED.value
        periode.approuve_par_id = user_id
        periode.date_approbation = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(periode)

        return True
