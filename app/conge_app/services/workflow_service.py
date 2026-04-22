"""Service d'orchestration du workflow de demandes."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conge_app.constants import CodeProcessus, CodeStatut, StatutAttribution
from app.conge_app.models import (
    ActionEtapeProcessus,
    DemandeConge,
    EtapeProcessus,
    HistoriqueDemande,
    StatutProcessus,
)
from app.conge_app.services.attribution_service import AttributionService
from app.conge_app.services.solde_service import SoldeService


class WorkflowConfigError(RuntimeError):
    """Erreur de configuration du workflow (étape/statut manquant)."""


class WorkflowPermissionError(PermissionError):
    """L'utilisateur n'a pas le droit d'exécuter l'action."""


class WorkflowStateError(ValueError):
    """État invalide (étape inconnue, action non applicable, etc.)."""


class WorkflowService:
    """Orchestration d'un workflow dynamique piloté par la DB."""

    DEMANDE_TYPE = CodeProcessus.CONGE.value

    # ------------------------------------------------------------------
    # Accès aux entités de configuration
    # ------------------------------------------------------------------

    @staticmethod
    async def get_statut_by_code(db: AsyncSession, code_statut: str) -> StatutProcessus:
        stmt = select(StatutProcessus).where(StatutProcessus.code_statut == code_statut)
        result = await db.execute(stmt)
        statut = result.scalar_one_or_none()
        if statut is None:
            raise WorkflowConfigError(f"Statut '{code_statut}' non configuré")
        return statut

    @staticmethod
    async def get_first_etape(db: AsyncSession, code_processus: str) -> EtapeProcessus:
        stmt = (
            select(EtapeProcessus)
            .where(EtapeProcessus.code_processus == code_processus)
            .order_by(EtapeProcessus.ordre.asc())
            .limit(1)
        )
        result = await db.execute(stmt)
        etape = result.scalar_one_or_none()
        if etape is None:
            raise WorkflowConfigError(
                f"Aucune étape configurée pour le processus '{code_processus}'"
            )
        return etape

    @staticmethod
    async def list_actions_for_etape(
        db: AsyncSession, etape_id: int
    ) -> list[ActionEtapeProcessus]:
        stmt = select(ActionEtapeProcessus).where(ActionEtapeProcessus.etape_id == etape_id)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Permissions
    # ------------------------------------------------------------------

    @classmethod
    async def is_user_valideur(
        cls,
        db: AsyncSession,
        demande: DemandeConge,
        employe_id: int,
    ) -> bool:
        """True si l'utilisateur peut agir sur l'étape courante de la demande."""
        attribution = await AttributionService.get_attribution_for_user(
            db,
            demande_id=demande.id,
            etape_id=demande.etape_courante_id,
            employe_id=employe_id,
            demande_type=cls.DEMANDE_TYPE,
        )
        if attribution is None:
            return False
        return attribution.statut == StatutAttribution.PRISE_EN_CHARGE.value

    # ------------------------------------------------------------------
    # Application d'une action
    # ------------------------------------------------------------------

    @classmethod
    async def apply_action(
        cls,
        db: AsyncSession,
        demande: DemandeConge,
        action_id: int,
        valideur_employe_id: int,
        commentaire: str | None = None,
    ) -> DemandeConge:
        """Exécute une action sur l'étape courante de la demande.

        - Vérifie que l'utilisateur est bien le valideur attribué (``prise_en_charge``).
        - Met à jour ``statut_global`` et ``etape_courante`` selon la config.
        - Enregistre l'historique et marque l'attribution comme ``traitee``.
        - Si fin du workflow → positionne ``date_decision_finale`` et débite le solde
          en cas de statut terminal ``VALIDE``.
        """
        stmt = select(ActionEtapeProcessus).where(ActionEtapeProcessus.id == action_id)
        result = await db.execute(stmt)
        action = result.scalar_one_or_none()
        if action is None:
            raise WorkflowStateError(f"Action {action_id} introuvable")

        if action.etape_id != demande.etape_courante_id:
            raise WorkflowStateError(
                "L'action ne s'applique pas à l'étape courante de la demande"
            )

        if not await cls.is_user_valideur(db, demande, valideur_employe_id):
            raise WorkflowPermissionError(
                "Vous n'êtes pas le valideur attribué à cette étape"
            )

        etape_actuelle_id = demande.etape_courante_id
        nouveau_statut_id = action.statut_cible_id

        # Mise à jour statut global
        demande.statut_global_id = nouveau_statut_id

        # Transition d'étape
        if action.etape_suivante_id is not None:
            demande.etape_courante_id = action.etape_suivante_id
            workflow_termine = False
        else:
            workflow_termine = True

        # Historique (avant marquage traitee de l'attribution)
        historique = HistoriqueDemande(
            demande_type=cls.DEMANDE_TYPE,
            demande_id=demande.id,
            etape_id=etape_actuelle_id,
            action_id=action.id,
            nouveau_statut_id=nouveau_statut_id,
            valideur_id=valideur_employe_id,
            commentaire=commentaire,
        )
        db.add(historique)

        # Marquer l'attribution comme traitée
        await AttributionService.mark_traitee(
            db,
            demande_id=demande.id,
            etape_id=etape_actuelle_id,
            employe_id=valideur_employe_id,
            demande_type=cls.DEMANDE_TYPE,
        )

        if workflow_termine:
            demande.date_decision_finale = datetime.utcnow()
            # Débit solde si statut final = VALIDE
            statut_final = await db.get(StatutProcessus, nouveau_statut_id)
            if (
                statut_final is not None
                and statut_final.code_statut == CodeStatut.VALIDE.value
            ):
                await SoldeService.debit(
                    db,
                    employe_id=demande.employe_id,
                    type_conge_id=demande.type_conge_id,
                    annee=demande.date_debut.year,
                    nb_jours=demande.nb_jours_ouvres,
                )
        else:
            # Création des attributions pour la nouvelle étape
            etape_suivante = await db.get(EtapeProcessus, demande.etape_courante_id)
            if etape_suivante is None:
                raise WorkflowConfigError(
                    f"Étape suivante {demande.etape_courante_id} introuvable"
                )
            valideurs = await AttributionService.find_valideurs(
                db, etape_suivante, demande.responsable_id
            )
            await AttributionService.create_attributions(
                db,
                demande_id=demande.id,
                etape=etape_suivante,
                valideurs=valideurs,
                demande_type=cls.DEMANDE_TYPE,
            )

        await db.flush()
        return demande
