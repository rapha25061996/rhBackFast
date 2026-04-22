"""FastAPI routes for the workflow-based leave management module."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conge_app.constants import (
    CodeProcessus,
)
from app.conge_app.models import (
    ActionEtapeProcessus,
    DemandeAttribution,
    DemandeConge,
    EtapeProcessus,
    HistoriqueDemande,
    SoldeConge,
    StatutProcessus,
    TypeConge,
)
from app.conge_app.schemas import (
    ActionEtapeCreate,
    ActionEtapeResponse,
    ActionEtapeUpdate,
    ActionsPossiblesResponse,
    AppliquerActionRequest,
    AttributionResponse,
    DemandeCongeCreate,
    DemandeCongeDetail,
    DemandeCongeResponse,
    EtapeProcessusCreate,
    EtapeProcessusResponse,
    EtapeProcessusUpdate,
    HistoriqueResponse,
    PaginatedDemandeConge,
    PaginatedSoldeConge,
    PaginatedTypeConge,
    SoldeCongeResponse,
    SoldeCongeUpsert,
    StatutProcessusCreate,
    StatutProcessusResponse,
    TypeCongeCreate,
    TypeCongeResponse,
    TypeCongeUpdate,
)
from app.conge_app.services import (
    AttributionService,
    DemandeCongeService,
    SoldeService,
    WorkflowService,
)
from app.conge_app.services.workflow_service import (
    WorkflowConfigError,
    WorkflowPermissionError,
    WorkflowStateError,
)
from app.core.database import get_db
from app.core.permissions import require_permission
from app.core.query_utils import apply_expansion, build_expand_options, parse_expand_param
from app.user_app.models import Employe, User


router = APIRouter(prefix="/api/conge", tags=["Congé Management"])


# ---------------------------------------------------------------------------
# Utilitaires internes
# ---------------------------------------------------------------------------


def _resolve_employe_id(current_user: User) -> int:
    """Retourne l'``employe_id`` lié à l'utilisateur ou lève 400."""
    if current_user.employe_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Votre compte utilisateur n'est lié à aucun employé",
        )
    return current_user.employe_id


# ---------------------------------------------------------------------------
# Types de congé
# ---------------------------------------------------------------------------


@router.get("/types", response_model=PaginatedTypeConge)
async def list_types_conge(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("conge", "view")),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    search: Optional[str] = Query(None),
    expand: Optional[str] = Query(None, description="Relations à inclure (soldes, demandes)"),
):
    stmt = select(TypeConge)
    count_stmt = select(func.count()).select_from(TypeConge)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(or_(TypeConge.nom.ilike(like), TypeConge.code.ilike(like)))
        count_stmt = count_stmt.where(
            or_(TypeConge.nom.ilike(like), TypeConge.code.ilike(like))
        )
    total = (await db.execute(count_stmt)).scalar() or 0
    if expand:
        stmt = apply_expansion(stmt, TypeConge, parse_expand_param(expand))
    stmt = stmt.order_by(TypeConge.nom.asc()).offset(skip).limit(limit)
    items = (await db.execute(stmt)).scalars().all()
    return PaginatedTypeConge(
        items=[TypeCongeResponse.model_validate(i) for i in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.post(
    "/types", response_model=TypeCongeResponse, status_code=status.HTTP_201_CREATED
)
async def create_type_conge(
    payload: TypeCongeCreate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("conge", "manage_types")),
):
    existing = (
        await db.execute(select(TypeConge).where(TypeConge.code == payload.code))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Un type de congé avec le code '{payload.code}' existe déjà",
        )
    type_conge = TypeConge(**payload.model_dump())
    db.add(type_conge)
    await db.commit()
    await db.refresh(type_conge)
    return type_conge


@router.patch("/types/{type_id}", response_model=TypeCongeResponse)
async def update_type_conge(
    type_id: int,
    payload: TypeCongeUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("conge", "manage_types")),
):
    type_conge = await db.get(TypeConge, type_id)
    if type_conge is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Type introuvable")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(type_conge, field, value)
    await db.commit()
    await db.refresh(type_conge)
    return type_conge


@router.delete("/types/{type_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_type_conge(
    type_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("conge", "manage_types")),
):
    type_conge = await db.get(TypeConge, type_id)
    if type_conge is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Type introuvable")
    await db.delete(type_conge)
    await db.commit()


# ---------------------------------------------------------------------------
# Soldes
# ---------------------------------------------------------------------------


@router.get("/soldes/me", response_model=list[SoldeCongeResponse])
async def list_my_soldes(
    annee: Optional[int] = Query(None, ge=2000, le=2100),
    expand: Optional[str] = Query(None, description="Relations à inclure (type_conge)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("conge", "view")),
):
    employe_id = _resolve_employe_id(current_user)
    stmt = select(SoldeConge).where(SoldeConge.employe_id == employe_id)
    if annee is not None:
        stmt = stmt.where(SoldeConge.annee == annee)
    if expand:
        stmt = apply_expansion(stmt, SoldeConge, parse_expand_param(expand))
    stmt = stmt.order_by(SoldeConge.annee.desc())
    items = (await db.execute(stmt)).scalars().all()
    return [SoldeCongeResponse.model_validate(i) for i in items]


@router.get("/soldes", response_model=PaginatedSoldeConge)
async def list_soldes(
    employe_id: Optional[int] = Query(None),
    annee: Optional[int] = Query(None, ge=2000, le=2100),
    type_conge_id: Optional[int] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    expand: Optional[str] = Query(None, description="Relations à inclure (type_conge)"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("conge", "manage_soldes")),
):
    stmt = select(SoldeConge)
    count_stmt = select(func.count()).select_from(SoldeConge)
    clauses = []
    if employe_id is not None:
        clauses.append(SoldeConge.employe_id == employe_id)
    if annee is not None:
        clauses.append(SoldeConge.annee == annee)
    if type_conge_id is not None:
        clauses.append(SoldeConge.type_conge_id == type_conge_id)
    if clauses:
        stmt = stmt.where(and_(*clauses))
        count_stmt = count_stmt.where(and_(*clauses))
    total = (await db.execute(count_stmt)).scalar() or 0
    if expand:
        stmt = apply_expansion(stmt, SoldeConge, parse_expand_param(expand))
    stmt = stmt.order_by(SoldeConge.annee.desc()).offset(skip).limit(limit)
    items = (await db.execute(stmt)).scalars().all()
    return PaginatedSoldeConge(
        items=[SoldeCongeResponse.model_validate(i) for i in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.post("/soldes", response_model=SoldeCongeResponse)
async def upsert_solde(
    payload: SoldeCongeUpsert,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("conge", "manage_soldes")),
):
    employe = await db.get(Employe, payload.employe_id)
    if employe is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employé introuvable")
    type_conge = await db.get(TypeConge, payload.type_conge_id)
    if type_conge is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Type introuvable")
    solde = await SoldeService.upsert(
        db,
        employe_id=payload.employe_id,
        type_conge_id=payload.type_conge_id,
        annee=payload.annee,
        alloue=payload.alloue,
        reporte=payload.reporte,
        date_expiration=payload.date_expiration,
    )
    await db.commit()
    await db.refresh(solde)
    return solde


# ---------------------------------------------------------------------------
# Workflow : statuts
# ---------------------------------------------------------------------------


@router.get("/workflow/statuts", response_model=list[StatutProcessusResponse])
async def list_statuts(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("conge", "manage_workflow")),
):
    items = (
        (await db.execute(select(StatutProcessus).order_by(StatutProcessus.code_statut.asc())))
        .scalars()
        .all()
    )
    return [StatutProcessusResponse.model_validate(i) for i in items]


@router.post(
    "/workflow/statuts",
    response_model=StatutProcessusResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_statut(
    payload: StatutProcessusCreate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("conge", "manage_workflow")),
):
    existing = (
        await db.execute(
            select(StatutProcessus).where(StatutProcessus.code_statut == payload.code_statut)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Code statut déjà utilisé"
        )
    statut = StatutProcessus(code_statut=payload.code_statut)
    db.add(statut)
    await db.commit()
    await db.refresh(statut)
    return statut


# ---------------------------------------------------------------------------
# Workflow : étapes
# ---------------------------------------------------------------------------


@router.get("/workflow/etapes", response_model=list[EtapeProcessusResponse])
async def list_etapes(
    code_processus: str = Query(CodeProcessus.CONGE.value),
    expand: Optional[str] = Query(None, description="Relations à inclure (actions)"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("conge", "manage_workflow")),
):
    stmt = (
        select(EtapeProcessus)
        .where(EtapeProcessus.code_processus == code_processus)
    )
    if expand:
        stmt = apply_expansion(stmt, EtapeProcessus, parse_expand_param(expand))
    stmt = stmt.order_by(EtapeProcessus.ordre.asc())
    items = (await db.execute(stmt)).scalars().all()
    return [EtapeProcessusResponse.model_validate(i) for i in items]


@router.post(
    "/workflow/etapes",
    response_model=EtapeProcessusResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_etape(
    payload: EtapeProcessusCreate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("conge", "manage_workflow")),
):
    etape = EtapeProcessus(**payload.model_dump())
    db.add(etape)
    try:
        await db.commit()
    except Exception as exc:  # unique constraint violation, etc.
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await db.refresh(etape)
    return etape


@router.patch("/workflow/etapes/{etape_id}", response_model=EtapeProcessusResponse)
async def update_etape(
    etape_id: int,
    payload: EtapeProcessusUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("conge", "manage_workflow")),
):
    etape = await db.get(EtapeProcessus, etape_id)
    if etape is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Étape introuvable")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(etape, field, value)
    await db.commit()
    await db.refresh(etape)
    return etape


@router.delete("/workflow/etapes/{etape_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_etape(
    etape_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("conge", "manage_workflow")),
):
    etape = await db.get(EtapeProcessus, etape_id)
    if etape is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Étape introuvable")
    await db.delete(etape)
    await db.commit()


# ---------------------------------------------------------------------------
# Workflow : actions
# ---------------------------------------------------------------------------


@router.get("/workflow/actions", response_model=list[ActionEtapeResponse])
async def list_actions(
    etape_id: Optional[int] = Query(None),
    expand: Optional[str] = Query(None, description="Relations à inclure (etape, statut_cible, etape_suivante)"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("conge", "manage_workflow")),
):
    stmt = select(ActionEtapeProcessus)
    if etape_id is not None:
        stmt = stmt.where(ActionEtapeProcessus.etape_id == etape_id)
    if expand:
        stmt = apply_expansion(stmt, ActionEtapeProcessus, parse_expand_param(expand))
    stmt = stmt.order_by(ActionEtapeProcessus.id.asc())
    items = (await db.execute(stmt)).scalars().all()
    return [ActionEtapeResponse.model_validate(i) for i in items]


@router.post(
    "/workflow/actions",
    response_model=ActionEtapeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_action(
    payload: ActionEtapeCreate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("conge", "manage_workflow")),
):
    etape = await db.get(EtapeProcessus, payload.etape_id)
    if etape is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Étape introuvable")
    statut = await db.get(StatutProcessus, payload.statut_cible_id)
    if statut is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Statut cible introuvable"
        )
    if payload.etape_suivante_id is not None:
        etape_suivante = await db.get(EtapeProcessus, payload.etape_suivante_id)
        if etape_suivante is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Étape suivante introuvable",
            )
    action = ActionEtapeProcessus(**payload.model_dump())
    db.add(action)
    await db.commit()
    await db.refresh(action)
    return action


@router.patch("/workflow/actions/{action_id}", response_model=ActionEtapeResponse)
async def update_action(
    action_id: int,
    payload: ActionEtapeUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("conge", "manage_workflow")),
):
    action = await db.get(ActionEtapeProcessus, action_id)
    if action is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action introuvable")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(action, field, value)
    await db.commit()
    await db.refresh(action)
    return action


@router.delete("/workflow/actions/{action_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_action(
    action_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("conge", "manage_workflow")),
):
    action = await db.get(ActionEtapeProcessus, action_id)
    if action is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action introuvable")
    await db.delete(action)
    await db.commit()


# ---------------------------------------------------------------------------
# Demandes
# ---------------------------------------------------------------------------


@router.post(
    "/demandes",
    response_model=DemandeCongeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_demande(
    payload: DemandeCongeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("conge", "create")),
):
    # Un employé ne peut créer que pour lui-même, sauf superuser.
    if not current_user.is_superuser:
        user_employe_id = _resolve_employe_id(current_user)
        if payload.employe_id != user_employe_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vous ne pouvez créer une demande que pour vous-même",
            )
    try:
        demande = await DemandeCongeService.create_demande(db, payload)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except WorkflowConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    await db.commit()
    await db.refresh(demande)
    return demande


@router.get("/demandes", response_model=PaginatedDemandeConge)
async def list_demandes(
    mode: str = Query("mine", description="'mine', 'a_valider', ou 'all'"),
    employe_id: Optional[int] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    expand: Optional[str] = Query(
        None,
        description="Relations à inclure (type_conge, etape_courante, statut_global)",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("conge", "view")),
):
    if mode == "mine":
        filter_employe = _resolve_employe_id(current_user)
        valideur_filter = None
    elif mode == "a_valider":
        valideur_filter = _resolve_employe_id(current_user)
        filter_employe = None
    elif mode == "all":
        if not current_user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Accès refusé (superuser requis pour mode=all)",
            )
        filter_employe = employe_id
        valideur_filter = None
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="mode doit valoir 'mine', 'a_valider' ou 'all'",
        )

    expand_options = _build_demande_expand_options(expand)
    items, total = await DemandeCongeService.list_demandes(
        db,
        employe_id=filter_employe,
        mode_valideur_employe_id=valideur_filter,
        skip=skip,
        limit=limit,
        expand_options=expand_options,
    )
    return PaginatedDemandeConge(
        items=[DemandeCongeResponse.model_validate(i) for i in items],
        total=total,
        skip=skip,
        limit=limit,
    )


def _build_demande_expand_options(expand: Optional[str]) -> list:
    """Construit les options ``selectinload`` pour ``DemandeConge``.

    Utilise l'utilitaire générique ``build_expand_options`` pour transformer
    le paramètre `?expand=...` en chaînes de ``selectinload`` prêtes à être
    passées à ``select(...).options(*opts)`` côté service.
    """
    if not expand:
        return []
    return build_expand_options(DemandeConge, parse_expand_param(expand))


async def _fetch_demande_or_404(db: AsyncSession, demande_id: int) -> DemandeConge:
    demande = await db.get(DemandeConge, demande_id)
    if demande is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Demande introuvable")
    return demande


def _assert_can_view_demande(current_user: User, demande: DemandeConge) -> None:
    if current_user.is_superuser:
        return
    if demande.employe_id == current_user.employe_id:
        return
    # Laisser passer : la vérification fine (valideur attribué) est faite
    # sur les actions ; pour la consultation on reste permissif tant que
    # `conge.view` est accordé.


@router.get("/demandes/{demande_id}", response_model=DemandeCongeDetail)
async def get_demande(
    demande_id: int,
    expand: Optional[str] = Query(
        None,
        description="Relations à inclure (type_conge, etape_courante, statut_global)",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("conge", "view")),
):
    options = _build_demande_expand_options(expand)
    if options:
        stmt = select(DemandeConge).options(*options).where(DemandeConge.id == demande_id)
        demande = (await db.execute(stmt)).scalar_one_or_none()
        if demande is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Demande introuvable")
    else:
        demande = await _fetch_demande_or_404(db, demande_id)
    _assert_can_view_demande(current_user, demande)

    hist_stmt = (
        select(HistoriqueDemande)
        .where(
            HistoriqueDemande.demande_type == CodeProcessus.CONGE.value,
            HistoriqueDemande.demande_id == demande.id,
        )
        .order_by(HistoriqueDemande.created_at.asc())
    )
    historique = (await db.execute(hist_stmt)).scalars().all()

    attr_stmt = select(DemandeAttribution).where(
        DemandeAttribution.demande_type == CodeProcessus.CONGE.value,
        DemandeAttribution.demande_id == demande.id,
    )
    attributions = (await db.execute(attr_stmt)).scalars().all()

    payload = DemandeCongeDetail.model_validate(demande).model_dump()
    payload["historique"] = [HistoriqueResponse.model_validate(h) for h in historique]
    payload["attributions"] = [AttributionResponse.model_validate(a) for a in attributions]
    return DemandeCongeDetail.model_validate(payload)


@router.get("/demandes/{demande_id}/actions", response_model=ActionsPossiblesResponse)
async def actions_possibles(
    demande_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("conge", "view")),
):
    demande = await _fetch_demande_or_404(db, demande_id)
    employe_id = current_user.employe_id
    is_valideur = False
    if employe_id is not None:
        is_valideur = await WorkflowService.is_user_valideur(db, demande, employe_id)

    actions = await WorkflowService.list_actions_for_etape(db, demande.etape_courante_id)
    return ActionsPossiblesResponse(
        etape_courante_id=demande.etape_courante_id,
        is_valideur=is_valideur,
        actions=[ActionEtapeResponse.model_validate(a) for a in actions],
    )


@router.post(
    "/demandes/{demande_id}/prendre-en-charge",
    response_model=AttributionResponse,
)
async def prendre_en_charge(
    demande_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("conge", "approve")),
):
    demande = await _fetch_demande_or_404(db, demande_id)
    employe_id = _resolve_employe_id(current_user)
    try:
        attribution = await AttributionService.take_ownership(
            db,
            demande_id=demande.id,
            etape_id=demande.etape_courante_id,
            employe_id=employe_id,
            demande_type=CodeProcessus.CONGE.value,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(attribution)
    return attribution


@router.post("/demandes/{demande_id}/valider", response_model=DemandeCongeResponse)
async def appliquer_action(
    demande_id: int,
    payload: AppliquerActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("conge", "approve")),
):
    demande = await _fetch_demande_or_404(db, demande_id)
    employe_id = _resolve_employe_id(current_user)
    try:
        demande = await WorkflowService.apply_action(
            db,
            demande=demande,
            action_id=payload.action_id,
            valideur_employe_id=employe_id,
            commentaire=payload.commentaire,
        )
    except WorkflowPermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except WorkflowStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except WorkflowConfigError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    await db.commit()
    await db.refresh(demande)
    return demande
