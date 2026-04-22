"""Script d'initialisation des données par défaut du workflow paie.

Crée (de manière idempotente) :
- Les statuts manquants (``EN_MODIFICATION``, ``PAYE``) en complément de ceux
  déjà créés par ``init_conge_defaults``.
- Les 4 étapes du workflow ``PAIE`` : Calcul RH → Validation Chef service →
  Validation Direction → Paiement.
- Les actions (APPROUVER, REJETER, DEMANDER_MODIF, PRET_A_VALIDER, MARQUER_PAYE)
  associées à chaque étape.

Les entités existantes ne sont jamais écrasées : seules les lignes manquantes
sont ajoutées. Idempotent.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conge_app.models import (
    ActionEtapeProcessus,
    EtapeProcessus,
    StatutProcessus,
)
from app.paie_app.constants import (
    CodeProcessusPaie,
    CodeStatutPaie,
    NomActionPaie,
)


# Liste de tous les statuts (incluant ceux déjà créés par le module congé,
# pour garantir leur présence même si le script congé n'a pas été lancé).
_ALL_PAIE_STATUTS: list[str] = [s.value for s in CodeStatutPaie]


async def _ensure_statut(db: AsyncSession, code_statut: str) -> StatutProcessus:
    stmt = select(StatutProcessus).where(StatutProcessus.code_statut == code_statut)
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        return existing
    statut = StatutProcessus(code_statut=code_statut)
    db.add(statut)
    await db.flush()
    return statut


async def _ensure_etape(
    db: AsyncSession,
    code_processus: str,
    ordre: int,
    nom_etape: str,
    is_responsable: bool,
    poste_id: int | None = None,
) -> EtapeProcessus:
    stmt = select(EtapeProcessus).where(
        EtapeProcessus.code_processus == code_processus,
        EtapeProcessus.ordre == ordre,
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        return existing
    etape = EtapeProcessus(
        code_processus=code_processus,
        ordre=ordre,
        nom_etape=nom_etape,
        is_responsable=is_responsable,
        poste_id=poste_id,
    )
    db.add(etape)
    await db.flush()
    return etape


async def _ensure_action(
    db: AsyncSession,
    etape_id: int,
    nom_action: str,
    statut_cible_id: int,
    etape_suivante_id: int | None,
) -> ActionEtapeProcessus:
    stmt = select(ActionEtapeProcessus).where(
        ActionEtapeProcessus.etape_id == etape_id,
        ActionEtapeProcessus.nom_action == nom_action,
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        return existing
    action = ActionEtapeProcessus(
        etape_id=etape_id,
        nom_action=nom_action,
        statut_cible_id=statut_cible_id,
        etape_suivante_id=etape_suivante_id,
    )
    db.add(action)
    await db.flush()
    return action


async def init_paie_workflow_defaults(db: AsyncSession) -> None:
    """Initialise le workflow PAIE par défaut.

    Idempotent : peut être appelé à chaque démarrage sans écraser l'existant.

    Le workflow est linéaire :

    1. ``CALCUL_RH`` — la RH calcule / ajuste la paie.
       Actions : ``PRET_A_VALIDER`` → étape 2 (statut EN_COURS).
    2. ``VALIDATION_CHEF_SERVICE`` — validation hiérarchique (is_responsable=True).
       Actions : ``APPROUVER`` → étape 3, ``REJETER`` (fin, REJETE),
       ``DEMANDER_MODIF`` → étape 1 (EN_MODIFICATION).
    3. ``VALIDATION_DIRECTION`` — validation direction.
       Actions : ``APPROUVER`` → étape 4 (VALIDE),
       ``REJETER`` (fin, REJETE), ``DEMANDER_MODIF`` → étape 1 (EN_MODIFICATION).
    4. ``PAIEMENT`` — exécution du paiement.
       Actions : ``MARQUER_PAYE`` (fin, PAYE).

    Les ``poste_id`` des étapes 1, 3 et 4 ne sont **pas** renseignés par le
    script : l'administrateur doit les définir ensuite via la config (ou le
    seed d'init supplémentaire propre à l'organisation). En attendant, les
    étapes non-``is_responsable`` sans ``poste_id`` restent bloquées (aucune
    attribution possible) — c'est volontaire, pour alerter l'admin.
    """
    # 1. Statuts (y compris ceux du module congé, pour être autonome)
    statuts: dict[str, StatutProcessus] = {}
    for code in _ALL_PAIE_STATUTS:
        statuts[code] = await _ensure_statut(db, code)

    # 2. Étapes
    code_processus = CodeProcessusPaie.PAIE.value
    etape_calcul = await _ensure_etape(
        db,
        code_processus=code_processus,
        ordre=1,
        nom_etape="Calcul RH",
        is_responsable=False,
        poste_id=None,
    )
    etape_chef = await _ensure_etape(
        db,
        code_processus=code_processus,
        ordre=2,
        nom_etape="Validation Chef de service",
        is_responsable=True,
        poste_id=None,
    )
    etape_direction = await _ensure_etape(
        db,
        code_processus=code_processus,
        ordre=3,
        nom_etape="Validation Direction",
        is_responsable=False,
        poste_id=None,
    )
    etape_paiement = await _ensure_etape(
        db,
        code_processus=code_processus,
        ordre=4,
        nom_etape="Paiement",
        is_responsable=False,
        poste_id=None,
    )

    # 3. Actions
    # Étape 1 : Calcul RH → soumet à l'étape suivante
    await _ensure_action(
        db,
        etape_id=etape_calcul.id,
        nom_action=NomActionPaie.PRET_A_VALIDER.value,
        statut_cible_id=statuts[CodeStatutPaie.EN_COURS.value].id,
        etape_suivante_id=etape_chef.id,
    )

    # Étape 2 : Chef de service
    await _ensure_action(
        db,
        etape_id=etape_chef.id,
        nom_action=NomActionPaie.APPROUVER.value,
        statut_cible_id=statuts[CodeStatutPaie.EN_COURS.value].id,
        etape_suivante_id=etape_direction.id,
    )
    await _ensure_action(
        db,
        etape_id=etape_chef.id,
        nom_action=NomActionPaie.REJETER.value,
        statut_cible_id=statuts[CodeStatutPaie.REJETE.value].id,
        etape_suivante_id=None,
    )
    await _ensure_action(
        db,
        etape_id=etape_chef.id,
        nom_action=NomActionPaie.DEMANDER_MODIF.value,
        statut_cible_id=statuts[CodeStatutPaie.EN_MODIFICATION.value].id,
        etape_suivante_id=etape_calcul.id,
    )

    # Étape 3 : Direction
    await _ensure_action(
        db,
        etape_id=etape_direction.id,
        nom_action=NomActionPaie.APPROUVER.value,
        statut_cible_id=statuts[CodeStatutPaie.VALIDE.value].id,
        etape_suivante_id=etape_paiement.id,
    )
    await _ensure_action(
        db,
        etape_id=etape_direction.id,
        nom_action=NomActionPaie.REJETER.value,
        statut_cible_id=statuts[CodeStatutPaie.REJETE.value].id,
        etape_suivante_id=None,
    )
    await _ensure_action(
        db,
        etape_id=etape_direction.id,
        nom_action=NomActionPaie.DEMANDER_MODIF.value,
        statut_cible_id=statuts[CodeStatutPaie.EN_MODIFICATION.value].id,
        etape_suivante_id=etape_calcul.id,
    )

    # Étape 4 : Paiement
    await _ensure_action(
        db,
        etape_id=etape_paiement.id,
        nom_action=NomActionPaie.MARQUER_PAYE.value,
        statut_cible_id=statuts[CodeStatutPaie.PAYE.value].id,
        etape_suivante_id=None,
    )

    await db.commit()
