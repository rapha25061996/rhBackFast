"""Service d'orchestration du workflow pour les périodes de paie.

Réutilise intégralement les tables génériques du module ``conge_app``
(``StatutProcessus``, ``EtapeProcessus``, ``ActionEtapeProcessus``,
``DemandeAttribution``, ``HistoriqueDemande``) mais avec
``demande_type = 'PERIODE_PAIE'`` et ``code_processus = 'PAIE'``.

Le design est intentionnellement parallèle à ``conge_app.services.workflow_service``
pour garantir une cohérence maximale, sans toucher au code conge (aucune
régression possible sur les demandes de congé).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conge_app.models import (
    ActionEtapeProcessus,
    EtapeProcessus,
    HistoriqueDemande,
    StatutProcessus,
)
from app.conge_app.services.attribution_service import AttributionService
from app.paie_app.models import PeriodePaie
from app.paie_app.constants import (
    STATUT_TEXTUEL_PAR_CODE,
    CodeProcessusPaie,
    CodeStatutPaie,
    DemandeTypePaie,
    StatutAttribution,
)


class PaieWorkflowConfigError(RuntimeError):
    """Erreur de configuration du workflow paie (étape/statut manquant)."""


class PaieWorkflowPermissionError(PermissionError):
    """L'utilisateur n'a pas le droit d'exécuter l'action."""


class PaieWorkflowStateError(ValueError):
    """État invalide (étape inconnue, action non applicable, etc.)."""


class PaieWorkflowService:
    """Orchestration du workflow paie piloté par la DB."""

    DEMANDE_TYPE = DemandeTypePaie.PERIODE_PAIE.value
    CODE_PROCESSUS = CodeProcessusPaie.PAIE.value

    # ------------------------------------------------------------------
    # Accès aux entités de configuration
    # ------------------------------------------------------------------

    @staticmethod
    async def get_statut_by_code(db: AsyncSession, code_statut: str) -> StatutProcessus:
        stmt = select(StatutProcessus).where(StatutProcessus.code_statut == code_statut)
        statut = (await db.execute(stmt)).scalar_one_or_none()
        if statut is None:
            raise PaieWorkflowConfigError(f"Statut '{code_statut}' non configuré")
        return statut

    @classmethod
    async def get_first_etape(cls, db: AsyncSession) -> EtapeProcessus:
        stmt = (
            select(EtapeProcessus)
            .where(EtapeProcessus.code_processus == cls.CODE_PROCESSUS)
            .order_by(EtapeProcessus.ordre.asc())
            .limit(1)
        )
        etape = (await db.execute(stmt)).scalar_one_or_none()
        if etape is None:
            raise PaieWorkflowConfigError(
                f"Aucune étape configurée pour le processus '{cls.CODE_PROCESSUS}'"
            )
        return etape

    @staticmethod
    async def list_actions_for_etape(
        db: AsyncSession, etape_id: int
    ) -> list[ActionEtapeProcessus]:
        stmt = select(ActionEtapeProcessus).where(ActionEtapeProcessus.etape_id == etape_id)
        return list((await db.execute(stmt)).scalars().all())

    # ------------------------------------------------------------------
    # Soumission initiale
    # ------------------------------------------------------------------

    @classmethod
    async def submit_periode(
        cls,
        db: AsyncSession,
        periode: PeriodePaie,
        responsable_id: Optional[int] = None,
    ) -> PeriodePaie:
        """Positionne la période à l'étape initiale du workflow PAIE.

        - ``etape_courante_id`` ← première étape ordonnée du processus ``PAIE``
        - ``statut_global_id`` ← ``EN_ATTENTE``
        - ``responsable_id`` optionnel (utilisé si une étape ``is_responsable=True``
          est présente dans le workflow)
        - ``date_soumission`` renseignée, ``statut`` texte synchronisé
        - Création des lignes ``DemandeAttribution`` pour la première étape
        """
        if periode.etape_courante_id is not None:
            raise PaieWorkflowStateError(
                f"Période {periode.id} déjà dans le workflow"
            )

        etape = await cls.get_first_etape(db)
        statut_en_attente = await cls.get_statut_by_code(
            db, CodeStatutPaie.EN_ATTENTE.value
        )

        periode.etape_courante_id = etape.id
        periode.statut_global_id = statut_en_attente.id
        periode.responsable_id = responsable_id
        periode.date_soumission = datetime.utcnow()
        periode.date_decision_finale = None
        periode.statut = STATUT_TEXTUEL_PAR_CODE.get(
            CodeStatutPaie.EN_ATTENTE.value, periode.statut
        )

        valideurs = await AttributionService.find_valideurs(db, etape, responsable_id)
        await AttributionService.create_attributions(
            db,
            demande_id=periode.id,
            etape=etape,
            valideurs=valideurs,
            demande_type=cls.DEMANDE_TYPE,
        )
        await db.flush()
        return periode

    # ------------------------------------------------------------------
    # Permissions
    # ------------------------------------------------------------------

    @classmethod
    async def is_user_valideur(
        cls,
        db: AsyncSession,
        periode: PeriodePaie,
        employe_id: int,
    ) -> bool:
        """``True`` si l'utilisateur est l'attributaire courant de la période."""
        if periode.etape_courante_id is None:
            return False
        attribution = await AttributionService.get_attribution_for_user(
            db,
            demande_id=periode.id,
            etape_id=periode.etape_courante_id,
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
        periode: PeriodePaie,
        action_id: int,
        valideur_employe_id: int,
        commentaire: Optional[str] = None,
    ) -> PeriodePaie:
        """Exécute une action sur l'étape courante de la période.

        - Vérifie que l'utilisateur est le valideur attribué (``prise_en_charge``).
        - Met à jour ``statut_global_id`` et ``etape_courante_id`` selon la config.
        - Enregistre l'historique et marque l'attribution comme ``traitee``.
        - Si fin du workflow : positionne ``date_decision_finale`` et synchronise
          ``statut`` texte (APPROVED/PAID/DRAFT) avec le statut final.
        - Sinon : crée les attributions pour la nouvelle étape.
        """
        if periode.etape_courante_id is None:
            raise PaieWorkflowStateError(
                f"Période {periode.id} n'est pas dans le workflow"
            )

        stmt = select(ActionEtapeProcessus).where(ActionEtapeProcessus.id == action_id)
        action = (await db.execute(stmt)).scalar_one_or_none()
        if action is None:
            raise PaieWorkflowStateError(f"Action {action_id} introuvable")

        if action.etape_id != periode.etape_courante_id:
            raise PaieWorkflowStateError(
                "L'action ne s'applique pas à l'étape courante de la période"
            )

        if not await cls.is_user_valideur(db, periode, valideur_employe_id):
            raise PaieWorkflowPermissionError(
                "Vous n'êtes pas le valideur attribué à cette étape"
            )

        etape_actuelle_id = periode.etape_courante_id
        nouveau_statut_id = action.statut_cible_id

        # Mise à jour statut global
        periode.statut_global_id = nouveau_statut_id

        # Transition d'étape
        if action.etape_suivante_id is not None:
            periode.etape_courante_id = action.etape_suivante_id
            workflow_termine = False
        else:
            workflow_termine = True

        # Historique
        historique = HistoriqueDemande(
            demande_type=cls.DEMANDE_TYPE,
            demande_id=periode.id,
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
            demande_id=periode.id,
            etape_id=etape_actuelle_id,
            employe_id=valideur_employe_id,
            demande_type=cls.DEMANDE_TYPE,
        )

        # Synchroniser le statut texte rétro-compatible
        statut_final = await db.get(StatutProcessus, nouveau_statut_id)
        if statut_final is not None:
            statut_texte = STATUT_TEXTUEL_PAR_CODE.get(statut_final.code_statut)
            if statut_texte is not None:
                periode.statut = statut_texte

        if workflow_termine:
            periode.date_decision_finale = datetime.utcnow()
            if statut_final is not None and statut_final.code_statut == CodeStatutPaie.PAYE.value:
                # Trace technique : qui a "marqué payé" via le workflow
                periode.approuve_par_id = periode.approuve_par_id or None
                periode.date_approbation = periode.date_approbation or datetime.utcnow()
        else:
            etape_suivante = await db.get(EtapeProcessus, periode.etape_courante_id)
            if etape_suivante is None:
                raise PaieWorkflowConfigError(
                    f"Étape suivante {periode.etape_courante_id} introuvable"
                )
            valideurs = await AttributionService.find_valideurs(
                db, etape_suivante, periode.responsable_id
            )
            await AttributionService.create_attributions(
                db,
                demande_id=periode.id,
                etape=etape_suivante,
                valideurs=valideurs,
                demande_type=cls.DEMANDE_TYPE,
            )

        await db.flush()
        return periode
