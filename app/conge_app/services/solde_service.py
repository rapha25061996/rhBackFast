"""Service de gestion des soldes de congé."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conge_app.models import SoldeConge


class SoldeService:
    """CRUD + débit/crédit du solde de congé d'un employé."""

    @staticmethod
    async def get_solde(
        db: AsyncSession, employe_id: int, type_conge_id: int, annee: int
    ) -> SoldeConge | None:
        stmt = select(SoldeConge).where(
            SoldeConge.employe_id == employe_id,
            SoldeConge.type_conge_id == type_conge_id,
            SoldeConge.annee == annee,
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def ensure_solde(
        db: AsyncSession,
        employe_id: int,
        type_conge_id: int,
        annee: int,
        alloue_par_defaut: float = 0.0,
    ) -> SoldeConge:
        """Retourne le solde existant ou en crée un nouveau à zéro."""
        solde = await SoldeService.get_solde(db, employe_id, type_conge_id, annee)
        if solde is not None:
            return solde
        solde = SoldeConge(
            employe_id=employe_id,
            type_conge_id=type_conge_id,
            annee=annee,
            alloue=alloue_par_defaut,
            utilise=0.0,
            restant=alloue_par_defaut,
            reporte=0.0,
        )
        db.add(solde)
        await db.flush()
        return solde

    @staticmethod
    def can_debit(solde: SoldeConge, nb_jours: float) -> bool:
        return solde.restant + 1e-9 >= nb_jours

    @staticmethod
    async def debit(
        db: AsyncSession,
        employe_id: int,
        type_conge_id: int,
        annee: int,
        nb_jours: float,
    ) -> SoldeConge:
        """Débite le solde (augmente `utilise`, diminue `restant`).

        Lève ``ValueError`` si le solde n'existe pas ou est insuffisant.
        """
        solde = await SoldeService.get_solde(db, employe_id, type_conge_id, annee)
        if solde is None:
            raise ValueError(
                f"Aucun solde pour employe={employe_id}, type={type_conge_id}, annee={annee}"
            )
        if not SoldeService.can_debit(solde, nb_jours):
            raise ValueError("Solde insuffisant")
        solde.utilise = (solde.utilise or 0.0) + nb_jours
        solde.restant = (solde.alloue or 0.0) + (solde.reporte or 0.0) - solde.utilise
        await db.flush()
        return solde

    @staticmethod
    async def upsert(
        db: AsyncSession,
        employe_id: int,
        type_conge_id: int,
        annee: int,
        alloue: float,
        reporte: float = 0.0,
        date_expiration=None,
    ) -> SoldeConge:
        solde = await SoldeService.get_solde(db, employe_id, type_conge_id, annee)
        if solde is None:
            solde = SoldeConge(
                employe_id=employe_id,
                type_conge_id=type_conge_id,
                annee=annee,
                alloue=alloue,
                utilise=0.0,
                reporte=reporte,
                restant=alloue + reporte,
                date_expiration=date_expiration,
            )
            db.add(solde)
        else:
            solde.alloue = alloue
            solde.reporte = reporte
            solde.restant = alloue + reporte - (solde.utilise or 0.0)
            solde.date_expiration = date_expiration
        await db.flush()
        return solde
