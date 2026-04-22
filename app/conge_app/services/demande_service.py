"""Service principal de gestion des demandes de congé."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conge_app.constants import (
    DEFAULT_COUNTRY_CODE,
    DEFAULT_HOLIDAY_LANGUAGE,
    CodeProcessus,
    CodeStatut,
    DemiJournee,
)
from app.conge_app.models import (
    DemandeAttribution,
    DemandeConge,
    TypeConge,
)
from app.conge_app.schemas import DemandeCongeCreate
from app.conge_app.services.attribution_service import AttributionService
from app.conge_app.services.solde_service import SoldeService
from app.conge_app.services.workflow_service import (
    WorkflowConfigError,
    WorkflowService,
)
from app.conge_app.services.working_days_service import WorkingDaysService
from app.user_app.models import Employe


class DemandeCongeService:
    """Création, consultation, et filtrage des demandes de congé."""

    DEMANDE_TYPE = CodeProcessus.CONGE.value

    # ------------------------------------------------------------------
    # Création
    # ------------------------------------------------------------------

    @classmethod
    async def create_demande(
        cls,
        db: AsyncSession,
        payload: DemandeCongeCreate,
        country_code: str = DEFAULT_COUNTRY_CODE,
        language: str = DEFAULT_HOLIDAY_LANGUAGE,
    ) -> DemandeConge:
        """Crée une demande avec calcul des jours ouvrés, vérification du solde
        et initialisation du workflow CONGE."""
        # 1. Valider l'employé
        employe = await db.get(Employe, payload.employe_id)
        if employe is None:
            raise LookupError(f"Employé {payload.employe_id} introuvable")

        # 2. Valider le type de congé
        type_conge = await db.get(TypeConge, payload.type_conge_id)
        if type_conge is None:
            raise LookupError(f"Type de congé {payload.type_conge_id} introuvable")

        # 3. Calcul des jours ouvrés
        nb_jours_ouvres = WorkingDaysService.count_working_days(
            date_debut=payload.date_debut,
            date_fin=payload.date_fin,
            demi_journee_debut=payload.demi_journee_debut,
            demi_journee_fin=payload.demi_journee_fin,
            country_code=country_code,
            language=language,
        )
        if nb_jours_ouvres <= 0:
            raise ValueError(
                "La demande ne couvre aucun jour ouvré (week-ends/jours fériés uniquement)"
            )

        # 4. Vérification du solde (année = année de date_debut)
        annee = payload.date_debut.year
        solde = await SoldeService.get_solde(
            db, employe.id, type_conge.id, annee
        )
        if solde is None:
            raise ValueError(
                f"Aucun solde {type_conge.code} configuré pour l'employé {employe.id} en {annee}"
            )
        if not SoldeService.can_debit(solde, nb_jours_ouvres):
            raise PermissionError(
                f"Solde insuffisant : demandé={nb_jours_ouvres}, restant={solde.restant}"
            )

        # 5. Workflow : première étape + statut initial
        first_etape = await WorkflowService.get_first_etape(db, cls.DEMANDE_TYPE)
        statut_initial = await WorkflowService.get_statut_by_code(
            db, CodeStatut.EN_ATTENTE.value
        )

        # 6. Création de la demande
        demande = DemandeConge(
            employe_id=employe.id,
            type_conge_id=type_conge.id,
            date_debut=payload.date_debut,
            demi_journee_debut=(
                payload.demi_journee_debut.value
                if isinstance(payload.demi_journee_debut, DemiJournee)
                else payload.demi_journee_debut
            ),
            date_fin=payload.date_fin,
            demi_journee_fin=(
                payload.demi_journee_fin.value
                if isinstance(payload.demi_journee_fin, DemiJournee)
                else payload.demi_journee_fin
            ),
            nb_jours_ouvres=nb_jours_ouvres,
            etape_courante_id=first_etape.id,
            responsable_id=employe.responsable_id,
            statut_global_id=statut_initial.id,
            date_soumission=datetime.utcnow(),
        )
        db.add(demande)
        await db.flush()

        # 7. Attributions pour la première étape
        valideurs = await AttributionService.find_valideurs(
            db, first_etape, employe.responsable_id
        )
        if not valideurs:
            # Aucun valideur trouvé → configuration incomplète, on laisse la demande
            # mais on la signale via ValueError pour que l'API retourne 409.
            raise WorkflowConfigError(
                "Aucun valideur n'a pu être attribué à la première étape "
                "(responsable absent et poste vide)"
            )
        await AttributionService.create_attributions(
            db,
            demande_id=demande.id,
            etape=first_etape,
            valideurs=valideurs,
            demande_type=cls.DEMANDE_TYPE,
        )

        await db.flush()
        return demande

    # ------------------------------------------------------------------
    # Lecture
    # ------------------------------------------------------------------

    @staticmethod
    async def get_demande(db: AsyncSession, demande_id: int) -> DemandeConge | None:
        return await db.get(DemandeConge, demande_id)

    @classmethod
    async def list_demandes(
        cls,
        db: AsyncSession,
        employe_id: int | None = None,
        mode_valideur_employe_id: int | None = None,
        skip: int = 0,
        limit: int = 100,
        expand_options: list | None = None,
    ) -> tuple[list[DemandeConge], int]:
        """Liste les demandes.

        - ``employe_id`` : filtre par auteur.
        - ``mode_valideur_employe_id`` : liste les demandes dont l'étape courante est
          attribuée à cet employé avec statut ``prise_en_charge`` **ou** ``en_attente``.
        - ``expand_options`` : options SQLAlchemy (``selectinload(...)``) à appliquer
          pour le chargement optionnel des relations.
        """
        stmt = select(DemandeConge)
        if expand_options:
            stmt = stmt.options(*expand_options)

        if mode_valideur_employe_id is not None:
            sub = select(DemandeAttribution.demande_id).where(
                and_(
                    DemandeAttribution.demande_type == cls.DEMANDE_TYPE,
                    DemandeAttribution.valideur_attribue_id == mode_valideur_employe_id,
                    or_(
                        DemandeAttribution.statut == "en_attente",
                        DemandeAttribution.statut == "prise_en_charge",
                    ),
                )
            )
            stmt = stmt.where(DemandeConge.id.in_(sub))

        if employe_id is not None:
            stmt = stmt.where(DemandeConge.employe_id == employe_id)

        stmt = stmt.order_by(DemandeConge.date_soumission.desc())
        count_stmt = select(DemandeConge.id)
        if mode_valideur_employe_id is not None:
            sub = select(DemandeAttribution.demande_id).where(
                and_(
                    DemandeAttribution.demande_type == cls.DEMANDE_TYPE,
                    DemandeAttribution.valideur_attribue_id == mode_valideur_employe_id,
                    or_(
                        DemandeAttribution.statut == "en_attente",
                        DemandeAttribution.statut == "prise_en_charge",
                    ),
                )
            )
            count_stmt = count_stmt.where(DemandeConge.id.in_(sub))
        if employe_id is not None:
            count_stmt = count_stmt.where(DemandeConge.employe_id == employe_id)

        result_count = await db.execute(count_stmt)
        total = len(result_count.all())

        stmt = stmt.offset(skip).limit(limit)
        result = await db.execute(stmt)
        return list(result.scalars().all()), total
