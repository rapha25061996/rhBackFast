"""Script d'initialisation des données par défaut du module congé.

Crée (de manière idempotente) :
- Les statuts génériques de processus (EN_ATTENTE, EN_COURS, VALIDE, REJETE, ANNULE).
- Les types de congé par défaut (Annuel, Maladie, Sans solde).
- Les étapes du workflow ``CONGE`` (Responsable N+1 puis RH).
- Les actions (APPROUVER, REJETER) associées à chaque étape.

Les entités déjà existantes ne sont pas écrasées, leurs FK sont simplement réutilisés.
"""
from __future__ import annotations

from typing import Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conge_app.constants import CodeProcessus, CodeStatut
from app.conge_app.models import (
    ActionEtapeProcessus,
    EtapeProcessus,
    StatutProcessus,
    TypeConge,
)

DEFAULT_STATUTS: list[str] = [statut.value for statut in CodeStatut]

DEFAULT_TYPES_CONGE: list[dict] = [
    {
        "code": "CA",
        "nom": "Congé Annuel",
        "nb_jours_max_par_an": 30.0,
        "report_autorise": True,
        "necessite_validation": True,
        "description": "Congé annuel payé standard",
    },
    {
        "code": "CM",
        "nom": "Congé Maladie",
        "nb_jours_max_par_an": 15.0,
        "report_autorise": False,
        "necessite_validation": True,
        "description": "Congé maladie sur justificatif",
    },
    {
        "code": "CSS",
        "nom": "Congé Sans Solde",
        "nb_jours_max_par_an": 0.0,
        "report_autorise": False,
        "necessite_validation": True,
        "description": "Congé non rémunéré",
    },
]


async def _ensure_statut(db: AsyncSession, code_statut: str) -> StatutProcessus:
    stmt = select(StatutProcessus).where(StatutProcessus.code_statut == code_statut)
    result = await db.execute(stmt)
    statut = result.scalar_one_or_none()
    if statut is not None:
        return statut
    statut = StatutProcessus(code_statut=code_statut)
    db.add(statut)
    await db.flush()
    return statut


async def _ensure_type_conge(db: AsyncSession, payload: dict) -> TypeConge:
    stmt = select(TypeConge).where(TypeConge.code == payload["code"])
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing
    type_conge = TypeConge(**payload)
    db.add(type_conge)
    await db.flush()
    return type_conge


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
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()
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
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()
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


async def init_conge_defaults(db: AsyncSession) -> None:
    """Initialise les données par défaut pour le module congé.

    Idempotent : peut être lancé à chaque démarrage sans écraser l'existant.
    """
    # 1. Statuts
    statuts: dict[str, StatutProcessus] = {}
    for code in DEFAULT_STATUTS:
        statuts[code] = await _ensure_statut(db, code)

    # 2. Types de congé
    for payload in DEFAULT_TYPES_CONGE:
        await _ensure_type_conge(db, payload)

    # 3. Étapes du workflow CONGE
    etape_responsable = await _ensure_etape(
        db,
        code_processus=CodeProcessus.CONGE.value,
        ordre=1,
        nom_etape="Validation Responsable N+1",
        is_responsable=True,
    )
    etape_rh = await _ensure_etape(
        db,
        code_processus=CodeProcessus.CONGE.value,
        ordre=2,
        nom_etape="Validation RH",
        is_responsable=False,
        # poste_id doit être renseigné par un admin via l'endpoint
        # PATCH /api/conge/workflow/etapes/{id} pour pointer vers le poste RH.
        poste_id=None,
    )

    # 4. Actions par étape
    await _ensure_action(
        db,
        etape_id=etape_responsable.id,
        nom_action="APPROUVER",
        statut_cible_id=statuts[CodeStatut.EN_COURS.value].id,
        etape_suivante_id=etape_rh.id,
    )
    await _ensure_action(
        db,
        etape_id=etape_responsable.id,
        nom_action="REJETER",
        statut_cible_id=statuts[CodeStatut.REJETE.value].id,
        etape_suivante_id=None,
    )
    await _ensure_action(
        db,
        etape_id=etape_rh.id,
        nom_action="APPROUVER",
        statut_cible_id=statuts[CodeStatut.VALIDE.value].id,
        etape_suivante_id=None,
    )
    await _ensure_action(
        db,
        etape_id=etape_rh.id,
        nom_action="REJETER",
        statut_cible_id=statuts[CodeStatut.REJETE.value].id,
        etape_suivante_id=None,
    )

    await db.commit()


InitHook = Callable[[AsyncSession], Awaitable[None]]
