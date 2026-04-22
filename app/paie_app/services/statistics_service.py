"""Statistics and reporting service for payroll system"""
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc
from sqlalchemy.orm import selectinload

from app.paie_app.constants import AlertStatus
from app.paie_app.models import (
    PeriodePaie, EntreePaie, RetenueEmploye, Alert
)


class StatisticsService:
    """Service for generating payroll statistics and reports"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_period_summary(self, periode_id: int) -> Dict[str, Any]:
        """Get comprehensive summary for a specific payroll period"""
        result = await self.db.execute(
            select(PeriodePaie)
            .options(selectinload(PeriodePaie.entries))
            .where(PeriodePaie.id == periode_id)
        )
        periode = result.scalar_one_or_none()

        if not periode:
            raise ValueError(f"Period {periode_id} not found")

        # Calculate statistics from entries
        entries = periode.entries
        total_employees = len(entries)
        total_gross = sum(e.salaire_brut for e in entries)
        total_net = sum(e.salaire_net for e in entries)
        total_employer_contrib = sum(
            sum(e.cotisations_patronales.values())
            if isinstance(e.cotisations_patronales, dict)
            else Decimal(0)
            for e in entries
        )
        total_employee_contrib = sum(
            sum(e.cotisations_salariales.values())
            if isinstance(e.cotisations_salariales, dict)
            else Decimal(0)
            for e in entries
        )
        total_deductions = sum(
            sum(e.retenues_diverses.values())
            if isinstance(e.retenues_diverses, dict)
            else Decimal(0)
            for e in entries
        )

        return {
            "periode_id": periode.id,
            "annee": periode.annee,
            "mois": periode.mois,
            "statut": periode.statut,
            "date_debut": periode.date_debut,
            "date_fin": periode.date_fin,
            "nombre_employes": total_employees,
            "masse_salariale_brute": float(total_gross),
            "masse_salariale_nette": float(total_net),
            "total_cotisations_patronales": float(total_employer_contrib),
            "total_cotisations_salariales": float(total_employee_contrib),
            "total_retenues": float(total_deductions),
            "cout_total_employeur": float(
                total_gross + total_employer_contrib
            ),
            "moyenne_salaire_brut": float(
                total_gross / total_employees if total_employees > 0 else 0
            ),
            "moyenne_salaire_net": float(
                total_net / total_employees if total_employees > 0 else 0
            ),
        }

    async def get_annual_summary(self, annee: int) -> Dict[str, Any]:
        """Get annual payroll summary"""
        result = await self.db.execute(
            select(PeriodePaie)
            .where(PeriodePaie.annee == annee)
            .order_by(PeriodePaie.mois)
        )
        periodes = result.scalars().all()

        if not periodes:
            raise ValueError(f"No periods found for year {annee}")

        monthly_data = []
        total_gross = Decimal(0)
        total_net = Decimal(0)
        total_employer_contrib = Decimal(0)
        total_employee_contrib = Decimal(0)

        for periode in periodes:
            summary = await self.get_period_summary(periode.id)
            monthly_data.append({
                "mois": periode.mois,
                "masse_salariale_brute": summary["masse_salariale_brute"],
                "masse_salariale_nette": summary["masse_salariale_nette"],
                "nombre_employes": summary["nombre_employes"],
            })
            total_gross += Decimal(str(summary["masse_salariale_brute"]))
            total_net += Decimal(str(summary["masse_salariale_nette"]))
            total_employer_contrib += Decimal(
                str(summary["total_cotisations_patronales"])
            )
            total_employee_contrib += Decimal(
                str(summary["total_cotisations_salariales"])
            )

        return {
            "annee": annee,
            "nombre_periodes": len(periodes),
            "masse_salariale_brute_annuelle": float(total_gross),
            "masse_salariale_nette_annuelle": float(total_net),
            "total_cotisations_patronales_annuelles": float(
                total_employer_contrib
            ),
            "total_cotisations_salariales_annuelles": float(
                total_employee_contrib
            ),
            "cout_total_employeur_annuel": float(
                total_gross + total_employer_contrib
            ),
            "moyenne_mensuelle_brute": float(
                total_gross / len(periodes) if periodes else 0
            ),
            "moyenne_mensuelle_nette": float(
                total_net / len(periodes) if periodes else 0
            ),
            "donnees_mensuelles": monthly_data,
        }

    async def get_employee_payroll_history(
        self,
        employe_id: int,
        annee: Optional[int] = None,
        limit: int = 12
    ) -> Dict[str, Any]:
        """Get payroll history for a specific employee"""
        query = (
            select(EntreePaie)
            .join(PeriodePaie)
            .where(EntreePaie.employe_id == employe_id)
            .order_by(desc(PeriodePaie.annee), desc(PeriodePaie.mois))
            .limit(limit)
        )

        if annee:
            query = query.where(PeriodePaie.annee == annee)

        result = await self.db.execute(query)
        entries = result.scalars().all()

        if not entries:
            raise ValueError(
                f"No payroll history found for employee {employe_id}"
            )

        history = []
        total_gross = Decimal(0)
        total_net = Decimal(0)

        for entry in entries:
            # Get period info
            period_result = await self.db.execute(
                select(PeriodePaie).where(
                    PeriodePaie.id == entry.periode_paie_id
                )
            )
            periode = period_result.scalar_one()

            history.append({
                "periode_id": periode.id,
                "annee": periode.annee,
                "mois": periode.mois,
                "salaire_base": float(entry.salaire_base),
                "salaire_brut": float(entry.salaire_brut),
                "salaire_net": float(entry.salaire_net),
                "cotisations_salariales": entry.cotisations_salariales,
                "retenues_diverses": entry.retenues_diverses,
            })
            total_gross += entry.salaire_brut
            total_net += entry.salaire_net

        return {
            "employe_id": employe_id,
            "nombre_periodes": len(entries),
            "historique": history,
            "total_brut": float(total_gross),
            "total_net": float(total_net),
            "moyenne_brute": float(
                total_gross / len(entries) if entries else 0
            ),
            "moyenne_nette": float(
                total_net / len(entries) if entries else 0
            ),
        }

    async def get_deductions_summary(
        self,
        employe_id: Optional[int] = None,
        type_retenue: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get summary of employee deductions"""
        query = select(RetenueEmploye).where(
            RetenueEmploye.est_active == True  # noqa: E712
        )

        if employe_id:
            query = query.where(RetenueEmploye.employe_id == employe_id)
        if type_retenue:
            query = query.where(RetenueEmploye.type_retenue == type_retenue)

        result = await self.db.execute(query)
        retenues = result.scalars().all()

        total_monthly = Decimal(0)
        total_remaining = Decimal(0)
        total_deducted = Decimal(0)
        by_type: Dict[str, Dict[str, Any]] = {}

        for retenue in retenues:
            total_monthly += retenue.montant_mensuel
            total_deducted += retenue.montant_deja_deduit
            if retenue.montant_total:
                remaining = (
                    retenue.montant_total - retenue.montant_deja_deduit
                )
                total_remaining += remaining

            # Group by type
            if retenue.type_retenue not in by_type:
                by_type[retenue.type_retenue] = {
                    "count": 0,
                    "total_monthly": Decimal(0),
                    "total_deducted": Decimal(0),
                    "total_remaining": Decimal(0),
                }

            by_type[retenue.type_retenue]["count"] += 1
            by_type[retenue.type_retenue]["total_monthly"] += (
                retenue.montant_mensuel
            )
            by_type[retenue.type_retenue]["total_deducted"] += (
                retenue.montant_deja_deduit
            )
            if retenue.montant_total:
                by_type[retenue.type_retenue]["total_remaining"] += (
                    retenue.montant_total - retenue.montant_deja_deduit
                )

        # Convert Decimal to float for JSON serialization
        by_type_serializable = {
            k: {
                "count": v["count"],
                "total_monthly": float(v["total_monthly"]),
                "total_deducted": float(v["total_deducted"]),
                "total_remaining": float(v["total_remaining"]),
            }
            for k, v in by_type.items()
        }

        return {
            "nombre_retenues_actives": len(retenues),
            "total_mensuel": float(total_monthly),
            "total_deja_deduit": float(total_deducted),
            "total_restant": float(total_remaining),
            "par_type": by_type_serializable,
        }

    async def get_alerts_summary(
        self,
        periode_id: Optional[int] = None,
        severity: Optional[str] = None,
        status: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get summary of payroll alerts"""
        query = select(Alert)

        if periode_id:
            query = query.where(Alert.periode_paie_id == periode_id)
        if severity:
            query = query.where(Alert.severity == severity)
        if status:
            query = query.where(Alert.status == status)

        result = await self.db.execute(query)
        alerts = result.scalars().all()

        by_severity: Dict[str, int] = {}
        by_status: Dict[str, int] = {}
        by_type: Dict[str, int] = {}

        for alert in alerts:
            # Count by severity
            by_severity[alert.severity] = (
                by_severity.get(alert.severity, 0) + 1
            )
            # Count by status
            by_status[alert.status] = by_status.get(alert.status, 0) + 1
            # Count by type
            by_type[alert.alert_type] = by_type.get(alert.alert_type, 0) + 1

        return {
            "total_alertes": len(alerts),
            "par_severite": by_severity,
            "par_statut": by_status,
            "par_type": by_type,
        }

    async def get_comparative_analysis(
        self,
        annee: int,
        mois: int,
        compare_to_previous: bool = True
    ) -> Dict[str, Any]:
        """Compare current period with previous or same month last year"""
        # Get current period
        current_result = await self.db.execute(
            select(PeriodePaie).where(
                and_(
                    PeriodePaie.annee == annee,
                    PeriodePaie.mois == mois
                )
            )
        )
        current_periode = current_result.scalar_one_or_none()

        if not current_periode:
            raise ValueError(f"Period {annee}/{mois} not found")

        current_summary = await self.get_period_summary(current_periode.id)

        # Determine comparison period
        if compare_to_previous:
            # Previous month
            compare_mois = mois - 1 if mois > 1 else 12
            compare_annee = annee if mois > 1 else annee - 1
        else:
            # Same month last year
            compare_mois = mois
            compare_annee = annee - 1

        # Get comparison period
        compare_result = await self.db.execute(
            select(PeriodePaie).where(
                and_(
                    PeriodePaie.annee == compare_annee,
                    PeriodePaie.mois == compare_mois
                )
            )
        )
        compare_periode = compare_result.scalar_one_or_none()

        if not compare_periode:
            return {
                "periode_actuelle": current_summary,
                "periode_comparaison": None,
                "comparaison_disponible": False,
                "message": (
                    f"No data for comparison period "
                    f"{compare_annee}/{compare_mois}"
                ),
            }

        compare_summary = await self.get_period_summary(compare_periode.id)

        # Calculate differences
        def calc_diff(current: float, previous: float) -> Dict[str, Any]:
            if previous == 0:
                return {
                    "valeur": 0,
                    "pourcentage": 0,
                }
            diff = current - previous
            pct = (diff / previous) * 100
            return {
                "valeur": round(diff, 2),
                "pourcentage": round(pct, 2),
            }

        return {
            "periode_actuelle": {
                "annee": annee,
                "mois": mois,
                "donnees": current_summary,
            },
            "periode_comparaison": {
                "annee": compare_annee,
                "mois": compare_mois,
                "donnees": compare_summary,
            },
            "comparaison_disponible": True,
            "differences": {
                "nombre_employes": calc_diff(
                    current_summary["nombre_employes"],
                    compare_summary["nombre_employes"]
                ),
                "masse_salariale_brute": calc_diff(
                    current_summary["masse_salariale_brute"],
                    compare_summary["masse_salariale_brute"]
                ),
                "masse_salariale_nette": calc_diff(
                    current_summary["masse_salariale_nette"],
                    compare_summary["masse_salariale_nette"]
                ),
                "cotisations_patronales": calc_diff(
                    current_summary["total_cotisations_patronales"],
                    compare_summary["total_cotisations_patronales"]
                ),
                "cotisations_salariales": calc_diff(
                    current_summary["total_cotisations_salariales"],
                    compare_summary["total_cotisations_salariales"]
                ),
            },
        }

    async def get_top_earners(
        self,
        periode_id: Optional[int] = None,
        annee: Optional[int] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get top earners for a period or year"""
        if periode_id:
            # Top earners for specific period
            result = await self.db.execute(
                select(EntreePaie)
                .where(EntreePaie.periode_paie_id == periode_id)
                .order_by(desc(EntreePaie.salaire_brut))
                .limit(limit)
            )
            entries = result.scalars().all()

            top_earners = []
            for entry in entries:
                top_earners.append({
                    "employe_id": entry.employe_id,
                    "salaire_brut": float(entry.salaire_brut),
                    "salaire_net": float(entry.salaire_net),
                    "periode_id": entry.periode_paie_id,
                })
            return top_earners

        elif annee:
            # Top earners for entire year (by total)
            result = await self.db.execute(
                select(
                    EntreePaie.employe_id,
                    func.sum(EntreePaie.salaire_brut).label("total_brut"),
                    func.sum(EntreePaie.salaire_net).label("total_net"),
                    func.count(EntreePaie.id).label("nombre_periodes")
                )
                .join(PeriodePaie)
                .where(PeriodePaie.annee == annee)
                .group_by(EntreePaie.employe_id)
                .order_by(desc("total_brut"))
                .limit(limit)
            )
            rows = result.all()

            top_earners = []
            for row in rows:
                top_earners.append({
                    "employe_id": row.employe_id,
                    "total_brut": float(row.total_brut),
                    "total_net": float(row.total_net),
                    "nombre_periodes": row.nombre_periodes,
                    "moyenne_brute": float(
                        row.total_brut / row.nombre_periodes
                    ),
                    "moyenne_nette": float(
                        row.total_net / row.nombre_periodes
                    ),
                })
            return top_earners

        else:
            raise ValueError(
                "Either periode_id or annee must be provided"
            )

    async def get_dashboard_summary(
        self,
        annee: Optional[int] = None,
        mois: Optional[int] = None
    ) -> Dict[str, Any]:
        """Get comprehensive dashboard summary"""
        if not annee:
            annee = datetime.now().year
        if not mois:
            mois = datetime.now().month

        # Get current period
        current_result = await self.db.execute(
            select(PeriodePaie).where(
                and_(
                    PeriodePaie.annee == annee,
                    PeriodePaie.mois == mois
                )
            )
        )
        current_periode = current_result.scalar_one_or_none()

        dashboard = {
            "annee": annee,
            "mois": mois,
            "periode_actuelle": None,
            "alertes": await self.get_alerts_summary(status=AlertStatus.ACTIVE.value),
            "retenues_actives": await self.get_deductions_summary(),
        }

        if current_periode:
            dashboard["periode_actuelle"] = await self.get_period_summary(
                current_periode.id
            )
            dashboard["top_earners"] = await self.get_top_earners(
                periode_id=current_periode.id,
                limit=5
            )

        # Get annual summary
        try:
            dashboard["resume_annuel"] = await self.get_annual_summary(annee)
        except ValueError:
            dashboard["resume_annuel"] = None

        return dashboard
