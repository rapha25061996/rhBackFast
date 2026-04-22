"""Endpoints du workflow dynamique paie.

Séparés de ``routes.py`` pour garder les nouveaux endpoints lisibles sans
toucher aux routes historiques (``/periodes/{id}/process``, ``/finalize``,
``/approve``) qui restent fonctionnelles.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conge_app.models import (
    ActionEtapeProcessus,
    DemandeAttribution,
    EtapeProcessus,
    HistoriqueDemande,
)
from app.conge_app.services.attribution_service import AttributionService
from app.core.database import get_db
from app.core.permissions import require_permission
from app.paie_app.models import PeriodePaie
from app.paie_app.schemas import (
    ActionPaieResponse,
    ActionsPaiePossiblesResponse,
    AppliquerActionPaieRequest,
    AttributionPaieResponse,
    HistoriquePaieResponse,
    PeriodePaieResponse,
    SubmitPeriodeRequest,
)
from app.paie_app.services.paie_workflow_service import (
    PaieWorkflowConfigError,
    PaieWorkflowPermissionError,
    PaieWorkflowService,
    PaieWorkflowStateError,
)
from app.paie_app.constants import DemandeTypePaie
from app.user_app.models import User


workflow_router = APIRouter(prefix="/periodes", tags=["Paie - Workflow"])


# ---------------------------------------------------------------------------
# Utilitaires internes
# ---------------------------------------------------------------------------


def _resolve_employe_id(current_user: User) -> int:
    if current_user.employe_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Votre compte utilisateur n'est lié à aucun employé",
        )
    return current_user.employe_id


async def _fetch_periode_or_404(db: AsyncSession, periode_id: int) -> PeriodePaie:
    periode = await db.get(PeriodePaie, periode_id)
    if periode is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Période {periode_id} introuvable",
        )
    return periode


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@workflow_router.post(
    "/{periode_id}/submit",
    response_model=PeriodePaieResponse,
    summary="Soumettre une période de paie au workflow",
)
async def submit_periode(
    periode_id: int,
    payload: SubmitPeriodeRequest = SubmitPeriodeRequest(),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("periode", "update")),
):
    """Met la période à l'étape initiale et crée les premières attributions.

    - 409 si la période est déjà dans le workflow.
    - 409 si la configuration paie (étapes/statuts) est incomplète.
    """
    periode = await _fetch_periode_or_404(db, periode_id)
    try:
        periode = await PaieWorkflowService.submit_periode(
            db, periode, responsable_id=payload.responsable_id
        )
    except PaieWorkflowStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except PaieWorkflowConfigError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(periode)
    return periode


@workflow_router.get(
    "/{periode_id}/actions",
    response_model=ActionsPaiePossiblesResponse,
    summary="Lister les actions possibles pour l'étape courante",
)
async def list_actions_possibles(
    periode_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("periode", "view")),
):
    periode = await _fetch_periode_or_404(db, periode_id)
    if periode.etape_courante_id is None:
        return ActionsPaiePossiblesResponse(
            etape_courante_id=None, is_valideur=False, actions=[]
        )
    actions = await PaieWorkflowService.list_actions_for_etape(
        db, periode.etape_courante_id
    )
    try:
        employe_id = _resolve_employe_id(current_user)
        is_valideur = await PaieWorkflowService.is_user_valideur(db, periode, employe_id)
    except HTTPException:
        is_valideur = False
    return ActionsPaiePossiblesResponse(
        etape_courante_id=periode.etape_courante_id,
        is_valideur=is_valideur,
        actions=[ActionPaieResponse.model_validate(a) for a in actions],
    )


@workflow_router.post(
    "/{periode_id}/prendre-en-charge",
    response_model=AttributionPaieResponse,
    summary="Prendre en charge l'étape (postes partagés)",
)
async def prendre_en_charge(
    periode_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("periode", "update")),
):
    periode = await _fetch_periode_or_404(db, periode_id)
    if periode.etape_courante_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Période pas encore dans le workflow",
        )
    employe_id = _resolve_employe_id(current_user)
    try:
        attribution = await AttributionService.take_ownership(
            db,
            demande_id=periode.id,
            etape_id=periode.etape_courante_id,
            employe_id=employe_id,
            demande_type=DemandeTypePaie.PERIODE_PAIE.value,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(attribution)
    return attribution


@workflow_router.post(
    "/{periode_id}/valider",
    response_model=PeriodePaieResponse,
    summary="Appliquer une action de workflow sur la période",
)
async def appliquer_action(
    periode_id: int,
    payload: AppliquerActionPaieRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("periode", "update")),
):
    periode = await _fetch_periode_or_404(db, periode_id)
    employe_id = _resolve_employe_id(current_user)
    try:
        periode = await PaieWorkflowService.apply_action(
            db,
            periode=periode,
            action_id=payload.action_id,
            valideur_employe_id=employe_id,
            commentaire=payload.commentaire,
        )
    except PaieWorkflowPermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except PaieWorkflowStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except PaieWorkflowConfigError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(periode)
    return periode


@workflow_router.get(
    "/{periode_id}/historique",
    response_model=list[HistoriquePaieResponse],
    summary="Historique complet des actions appliquées sur la période",
)
async def get_historique(
    periode_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("periode", "view")),
):
    periode = await _fetch_periode_or_404(db, periode_id)
    stmt = (
        select(HistoriqueDemande)
        .where(
            and_(
                HistoriqueDemande.demande_type == DemandeTypePaie.PERIODE_PAIE.value,
                HistoriqueDemande.demande_id == periode.id,
            )
        )
        .order_by(HistoriqueDemande.created_at.asc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [HistoriquePaieResponse.model_validate(h) for h in rows]


@workflow_router.get(
    "/{periode_id}/attributions",
    response_model=list[AttributionPaieResponse],
    summary="Attributions actuelles de l'étape courante",
)
async def list_attributions(
    periode_id: int,
    etape_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("periode", "view")),
):
    periode = await _fetch_periode_or_404(db, periode_id)
    target_etape_id = etape_id or periode.etape_courante_id
    if target_etape_id is None:
        return []
    stmt = select(DemandeAttribution).where(
        and_(
            DemandeAttribution.demande_type == DemandeTypePaie.PERIODE_PAIE.value,
            DemandeAttribution.demande_id == periode.id,
            DemandeAttribution.etape_id == target_etape_id,
        )
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [AttributionPaieResponse.model_validate(a) for a in rows]


# ---------------------------------------------------------------------------
# Endpoints de consultation de la configuration workflow PAIE
# ---------------------------------------------------------------------------


@workflow_router.get(
    "/config/etapes",
    response_model=list[dict],
    summary="Consulter les étapes configurées pour le processus PAIE",
)
async def list_etapes_paie(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("periode", "view")),
):
    stmt = (
        select(EtapeProcessus)
        .where(EtapeProcessus.code_processus == "PAIE")
        .order_by(EtapeProcessus.ordre.asc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    result: list[dict] = []
    for etape in rows:
        actions_stmt = select(ActionEtapeProcessus).where(
            ActionEtapeProcessus.etape_id == etape.id
        )
        actions = (await db.execute(actions_stmt)).scalars().all()
        result.append(
            {
                "id": etape.id,
                "ordre": etape.ordre,
                "nom_etape": etape.nom_etape,
                "poste_id": etape.poste_id,
                "is_responsable": etape.is_responsable,
                "actions": [
                    {
                        "id": a.id,
                        "nom_action": a.nom_action,
                        "statut_cible_id": a.statut_cible_id,
                        "etape_suivante_id": a.etape_suivante_id,
                    }
                    for a in actions
                ],
            }
        )
    return result
