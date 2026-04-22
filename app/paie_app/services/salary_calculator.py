"""
Salary calculation service.
"""
from decimal import Decimal
from typing import Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.paie_app.models import PeriodePaie, RetenueEmploye
from app.paie_app.constants import (
    calculate_ire,
    calculate_family_allowance,
    calculate_inss_employer,
    calculate_inss_employee,
)
from app.user_app.models import Employe, Contrat


class SalaryCalculatorService:
    """Service for calculating employee salaries"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def calculate_salary(
        self,
        employe_id: int,
        periode_id: int
    ) -> Dict:
        """Calculate complete salary for an employee"""
        # Get employee
        result = await self.db.execute(
            select(Employe).where(Employe.id == employe_id)
        )
        employe_obj = result.scalar_one_or_none()
        if not employe_obj:
            raise ValueError(f"Employee {employe_id} not found")

        # Get period
        result = await self.db.execute(
            select(PeriodePaie).where(PeriodePaie.id == periode_id)
        )
        periode_obj = result.scalar_one_or_none()
        if not periode_obj:
            raise ValueError(f"Period {periode_id} not found")

        # Get active contract
        result = await self.db.execute(
            select(Contrat).where(
                Contrat.employe_id == employe_id,
                Contrat.is_active.is_(True)
            )
        )
        contrat_obj = result.scalar_one_or_none()
        if not contrat_obj:
            raise ValueError(
                f"No active contract found for employee {employe_id}"
            )

        # Calculate all components
        salary_components = await self._calculate_all_components(
            contrat_obj, periode_obj, employe_obj
        )

        return salary_components

    async def calculate_gross_salary(
        self,
        contrat_obj: Contrat
    ) -> Dict[str, Decimal]:
        """Calculate gross salary based on contract"""
        salaire_base = contrat_obj.salaire_base

        # Calculate allowances as percentage of base salary
        indemnite_logement = salaire_base * (
            Decimal(str(contrat_obj.indemnite_logement)) / 100
        )
        indemnite_deplacement = salaire_base * (
            Decimal(str(contrat_obj.indemnite_deplacement)) / 100
        )
        indemnite_fonction = salaire_base * (
            Decimal(str(contrat_obj.prime_fonction)) / 100
        )

        # Get family allowance
        allocation_familiale = calculate_family_allowance(
            contrat_obj.employe.nombre_enfants
        )

        autres_avantages = contrat_obj.autre_avantage

        salaire_brut = (
            salaire_base +
            indemnite_logement +
            indemnite_deplacement +
            indemnite_fonction +
            allocation_familiale +
            autres_avantages
        )

        return {
            "salaire_base": salaire_base,
            "indemnite_logement": indemnite_logement,
            "indemnite_deplacement": indemnite_deplacement,
            "indemnite_fonction": indemnite_fonction,
            "allocation_familiale": allocation_familiale,
            "autres_avantages": autres_avantages,
            "salaire_brut": salaire_brut
        }

    async def calculate_social_contributions(
        self,
        gross_salary: Decimal,
        contrat_obj: Contrat
    ) -> Dict:
        """Calculate employer and employee social contributions"""
        # Employer contributions
        inss_employer = calculate_inss_employer(gross_salary)

        mfp_patron = gross_salary * (
            Decimal(str(contrat_obj.assurance_patronale)) / 100
        )
        fpc_patron = gross_salary * (
            Decimal(str(contrat_obj.fpc_patronale)) / 100
        )

        cotisations_patronales = {
            "inss_pension": inss_employer["pension"],
            "inss_risque": inss_employer["risk"],
            "mfp": mfp_patron,
            "fpc": fpc_patron,
            "total": inss_employer["total"] + mfp_patron + fpc_patron
        }

        # Employee contributions
        inss_employe = calculate_inss_employee(gross_salary)

        mfp_employe = gross_salary * (
            Decimal(str(contrat_obj.assurance_salariale)) / 100
        )
        fpc_employe = gross_salary * (
            Decimal(str(contrat_obj.fpc_salariale)) / 100
        )

        cotisations_salariales = {
            "inss": inss_employe,
            "mfp": mfp_employe,
            "fpc": fpc_employe,
            "total": inss_employe + mfp_employe + fpc_employe
        }

        return {
            "patronales": cotisations_patronales,
            "salariales": cotisations_salariales
        }

    async def calculate_deductions(
        self,
        employe_id: int,
        periode_obj: PeriodePaie
    ) -> Dict:
        """Calculate employee deductions for the period"""
        # Get active deductions for the period
        result = await self.db.execute(
            select(RetenueEmploye).where(
                RetenueEmploye.employe_id == employe_id,
                RetenueEmploye.est_active.is_(True),
                RetenueEmploye.date_debut <= periode_obj.date_fin,
                (RetenueEmploye.date_fin.is_(None)) |
                (RetenueEmploye.date_fin >= periode_obj.date_debut)
            )
        )
        retenues = result.scalars().all()

        total_retenues = Decimal("0")
        retenues_detail = {}

        for retenue in retenues:
            montant = retenue.montant_mensuel

            # Check if deduction has a total limit
            if retenue.montant_total:
                restant = retenue.montant_total - retenue.montant_deja_deduit
                if restant <= 0:
                    continue
                montant = min(montant, restant)

            retenues_detail[retenue.type_retenue] = {
                "id": retenue.id,
                "description": retenue.description,
                "montant": montant
            }
            total_retenues += montant

        return {
            "detail": retenues_detail,
            "total": total_retenues
        }

    async def calculate_net_salary(self, components: Dict) -> Decimal:
        """Calculate final net salary"""
        salaire_brut = components["salaire_brut"]
        cotisations_salariales = components["cotisations"]["salariales"]["total"]
        ire = components["ire"]
        retenues = components["retenues"]["total"]

        salaire_net = (
            salaire_brut -
            cotisations_salariales -
            ire -
            retenues
        )

        return salaire_net

    async def _calculate_all_components(
        self,
        contrat_obj: Contrat,
        periode_obj: PeriodePaie,
        employe_obj: Employe
    ) -> Dict:
        """Calculate all salary components"""
        # Gross salary components
        gross_components = await self.calculate_gross_salary(contrat_obj)
        salaire_brut = gross_components["salaire_brut"]

        # Social contributions
        cotisations = await self.calculate_social_contributions(
            salaire_brut, contrat_obj
        )

        # Taxable base
        base_imposable = (
            salaire_brut -
            gross_components["indemnite_logement"] -
            gross_components["indemnite_deplacement"] -
            gross_components["indemnite_fonction"] -
            cotisations["salariales"]["total"]
        )

        # Calculate IRE
        ire = calculate_ire(base_imposable)

        # Get deductions
        retenues = await self.calculate_deductions(
            employe_obj.id, periode_obj
        )

        # Calculate net salary
        salaire_net = await self.calculate_net_salary({
            "salaire_brut": salaire_brut,
            "cotisations": cotisations,
            "ire": ire,
            "retenues": retenues
        })

        # Total employer charge
        total_charge_salariale = (
            salaire_brut + cotisations["patronales"]["total"]
        )

        return {
            "employe_id": employe_obj.id,
            "periode_id": periode_obj.id,
            "contrat_reference": {
                "id": contrat_obj.id,
                "salaire_base": float(contrat_obj.salaire_base),
            },
            "salaire_base": gross_components["salaire_base"],
            "indemnite_logement": gross_components["indemnite_logement"],
            "indemnite_deplacement": gross_components["indemnite_deplacement"],
            "indemnite_fonction": gross_components["indemnite_fonction"],
            "allocation_familiale": gross_components["allocation_familiale"],
            "autres_avantages": gross_components["autres_avantages"],
            "salaire_brut": salaire_brut,
            "cotisations_patronales": cotisations["patronales"],
            "cotisations_salariales": cotisations["salariales"],
            "base_imposable": base_imposable,
            "ire": ire,
            "retenues_diverses": retenues["detail"],
            "total_charge_salariale": total_charge_salariale,
            "salaire_net": salaire_net
        }
