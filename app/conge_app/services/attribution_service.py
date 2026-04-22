"""Service d'attribution des étapes de workflow à des valideurs."""
from __future__ import annotations

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conge_app.constants import CodeProcessus, StatutAttribution
from app.conge_app.models import DemandeAttribution, EtapeProcessus
from app.user_app.models import Employe


class AttributionService:
    """Détermine les valideurs d'une étape et crée les lignes d'attribution associées."""

    @staticmethod
    async def find_valideurs(
        db: AsyncSession, etape: EtapeProcessus, responsable_id: int | None
    ) -> list[int]:
        """Retourne la liste des ``employe_id`` candidats pour valider l'étape.

        - Si l'étape est ``is_responsable`` → le responsable (ou []).
        - Sinon si l'étape référence un poste → tous les employés de ce poste.
        - Sinon → aucun candidat.
        """
        if etape.is_responsable:
            return [responsable_id] if responsable_id is not None else []

        if etape.poste_id is None:
            return []

        stmt = select(Employe.id).where(Employe.poste_id == etape.poste_id)
        result = await db.execute(stmt)
        return [row[0] for row in result.all()]

    @staticmethod
    async def create_attributions(
        db: AsyncSession,
        demande_id: int,
        etape: EtapeProcessus,
        valideurs: list[int],
        demande_type: str = CodeProcessus.CONGE.value,
    ) -> list[DemandeAttribution]:
        """Crée les lignes d'attribution pour une étape et une demande.

        - 0 candidat → aucune ligne créée (l'étape reste bloquée tant qu'un admin
          ne corrige pas la configuration).
        - 1 candidat → attribution directement en ``prise_en_charge``.
        - N candidats → N lignes en ``en_attente`` (l'un d'eux devra prendre en charge).
        """
        if not valideurs:
            return []

        statut_default = (
            StatutAttribution.PRISE_EN_CHARGE.value
            if len(valideurs) == 1
            else StatutAttribution.EN_ATTENTE.value
        )

        created: list[DemandeAttribution] = []
        for valideur_id in valideurs:
            attribution = DemandeAttribution(
                demande_type=demande_type,
                demande_id=demande_id,
                etape_id=etape.id,
                valideur_attribue_id=valideur_id,
                statut=statut_default,
            )
            db.add(attribution)
            created.append(attribution)
        await db.flush()
        return created

    @staticmethod
    async def get_attribution_for_user(
        db: AsyncSession,
        demande_id: int,
        etape_id: int,
        employe_id: int,
        demande_type: str = CodeProcessus.CONGE.value,
    ) -> DemandeAttribution | None:
        stmt = select(DemandeAttribution).where(
            and_(
                DemandeAttribution.demande_type == demande_type,
                DemandeAttribution.demande_id == demande_id,
                DemandeAttribution.etape_id == etape_id,
                DemandeAttribution.valideur_attribue_id == employe_id,
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_attributions_for_step(
        db: AsyncSession,
        demande_id: int,
        etape_id: int,
        demande_type: str = CodeProcessus.CONGE.value,
    ) -> list[DemandeAttribution]:
        stmt = select(DemandeAttribution).where(
            DemandeAttribution.demande_type == demande_type,
            DemandeAttribution.demande_id == demande_id,
            DemandeAttribution.etape_id == etape_id,
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def take_ownership(
        db: AsyncSession,
        demande_id: int,
        etape_id: int,
        employe_id: int,
        demande_type: str = CodeProcessus.CONGE.value,
    ) -> DemandeAttribution:
        """Prendre en charge l'étape quand plusieurs valideurs se la partagent.

        - La ligne de l'utilisateur passe ``en_attente`` → ``prise_en_charge``.
        - Toutes les autres lignes ``en_attente`` pour la même (demande, étape) passent
          à ``traitee`` afin de signaler qu'elles ne sont plus actionnables.
        """
        attributions = await AttributionService.list_attributions_for_step(
            db, demande_id, etape_id, demande_type=demande_type
        )
        if not attributions:
            raise ValueError("Aucune attribution pour cette étape")

        target: DemandeAttribution | None = None
        for attribution in attributions:
            if attribution.valideur_attribue_id == employe_id:
                target = attribution
                break
        if target is None:
            raise PermissionError("Vous n'êtes pas attribué à cette étape")

        if target.statut == StatutAttribution.TRAITEE.value:
            raise ValueError("Cette attribution a déjà été traitée")

        target.statut = StatutAttribution.PRISE_EN_CHARGE.value
        for attribution in attributions:
            if attribution.id == target.id:
                continue
            if attribution.statut == StatutAttribution.EN_ATTENTE.value:
                attribution.statut = StatutAttribution.TRAITEE.value
        await db.flush()
        return target

    @staticmethod
    async def mark_traitee(
        db: AsyncSession,
        demande_id: int,
        etape_id: int,
        employe_id: int,
        demande_type: str = CodeProcessus.CONGE.value,
    ) -> None:
        """Marque la ligne ``prise_en_charge`` du valideur comme ``traitee``."""
        attributions = await AttributionService.list_attributions_for_step(
            db, demande_id, etape_id, demande_type=demande_type
        )
        for attribution in attributions:
            if (
                attribution.valideur_attribue_id == employe_id
                and attribution.statut == StatutAttribution.PRISE_EN_CHARGE.value
            ):
                attribution.statut = StatutAttribution.TRAITEE.value
        await db.flush()
