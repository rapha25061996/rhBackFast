"""Pydantic schemas for the leave management module."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.conge_app.constants import CodeProcessus, DemiJournee, StatutAttribution


# ---------------------------------------------------------------------------
# TypeConge
# ---------------------------------------------------------------------------


class TypeCongeBase(BaseModel):
    nom: str = Field(..., max_length=100)
    code: str = Field(..., max_length=20)
    nb_jours_max_par_an: float = Field(default=0.0, ge=0)
    report_autorise: bool = True
    necessite_validation: bool = True
    description: Optional[str] = None


class TypeCongeCreate(TypeCongeBase):
    pass


class TypeCongeUpdate(BaseModel):
    nom: Optional[str] = Field(None, max_length=100)
    nb_jours_max_par_an: Optional[float] = Field(None, ge=0)
    report_autorise: Optional[bool] = None
    necessite_validation: Optional[bool] = None
    description: Optional[str] = None


class TypeCongeResponse(TypeCongeBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaginatedTypeConge(BaseModel):
    items: list[TypeCongeResponse]
    total: int
    skip: int
    limit: int


# ---------------------------------------------------------------------------
# SoldeConge
# ---------------------------------------------------------------------------


class SoldeCongeBase(BaseModel):
    employe_id: int
    type_conge_id: int
    annee: int = Field(..., ge=2000, le=2100)
    alloue: float = Field(default=0.0, ge=0)
    utilise: float = Field(default=0.0, ge=0)
    restant: float = Field(default=0.0)
    reporte: float = Field(default=0.0, ge=0)
    date_expiration: Optional[date] = None


class SoldeCongeCreate(SoldeCongeBase):
    pass


class SoldeCongeUpsert(BaseModel):
    employe_id: int
    type_conge_id: int
    annee: int = Field(..., ge=2000, le=2100)
    alloue: float = Field(..., ge=0)
    reporte: float = Field(default=0.0, ge=0)
    date_expiration: Optional[date] = None


class SoldeCongeResponse(SoldeCongeBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaginatedSoldeConge(BaseModel):
    items: list[SoldeCongeResponse]
    total: int
    skip: int
    limit: int


# ---------------------------------------------------------------------------
# Workflow : statut, étape, action
# ---------------------------------------------------------------------------


class StatutProcessusBase(BaseModel):
    code_statut: str = Field(..., max_length=50)


class StatutProcessusCreate(StatutProcessusBase):
    pass


class StatutProcessusResponse(StatutProcessusBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EtapeProcessusBase(BaseModel):
    code_processus: str = Field(..., max_length=50)
    ordre: int = Field(..., ge=0)
    nom_etape: str = Field(..., max_length=100)
    poste_id: Optional[int] = None
    is_responsable: bool = False


class EtapeProcessusCreate(EtapeProcessusBase):
    pass


class EtapeProcessusUpdate(BaseModel):
    ordre: Optional[int] = Field(None, ge=0)
    nom_etape: Optional[str] = Field(None, max_length=100)
    poste_id: Optional[int] = None
    is_responsable: Optional[bool] = None


class EtapeProcessusResponse(EtapeProcessusBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ActionEtapeBase(BaseModel):
    etape_id: int
    nom_action: str = Field(..., max_length=50)
    statut_cible_id: int
    etape_suivante_id: Optional[int] = None


class ActionEtapeCreate(ActionEtapeBase):
    pass


class ActionEtapeUpdate(BaseModel):
    nom_action: Optional[str] = Field(None, max_length=50)
    statut_cible_id: Optional[int] = None
    etape_suivante_id: Optional[int] = None


class ActionEtapeResponse(ActionEtapeBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# DemandeConge
# ---------------------------------------------------------------------------


class DemandeCongeCreate(BaseModel):
    employe_id: int
    type_conge_id: int
    date_debut: date
    demi_journee_debut: Optional[DemiJournee] = None
    date_fin: date
    demi_journee_fin: Optional[DemiJournee] = None

    @field_validator("demi_journee_debut", "demi_journee_fin", mode="before")
    @classmethod
    def _normalize_demi(cls, value: object) -> object:
        if isinstance(value, str) and value == "":
            return None
        return value

    @model_validator(mode="after")
    def _check_dates(self) -> "DemandeCongeCreate":
        if self.date_fin < self.date_debut:
            raise ValueError("date_fin doit être >= date_debut")
        return self


class DemandeCongeResponse(BaseModel):
    id: int
    employe_id: int
    type_conge_id: int
    date_debut: date
    demi_journee_debut: Optional[str] = None
    date_fin: date
    demi_journee_fin: Optional[str] = None
    nb_jours_ouvres: float
    etape_courante_id: int
    responsable_id: Optional[int] = None
    statut_global_id: int
    date_soumission: datetime
    date_decision_finale: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaginatedDemandeConge(BaseModel):
    items: list[DemandeCongeResponse]
    total: int
    skip: int
    limit: int


# ---------------------------------------------------------------------------
# Attribution & Historique
# ---------------------------------------------------------------------------


class AttributionResponse(BaseModel):
    id: int
    demande_type: str
    demande_id: int
    etape_id: int
    valideur_attribue_id: int
    date_attribution: datetime
    statut: StatutAttribution

    model_config = ConfigDict(from_attributes=True)


class HistoriqueResponse(BaseModel):
    id: int
    demande_type: str
    demande_id: int
    etape_id: int
    action_id: int
    nouveau_statut_id: int
    valideur_id: int
    commentaire: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DemandeCongeDetail(DemandeCongeResponse):
    historique: list[HistoriqueResponse] = []
    attributions: list[AttributionResponse] = []


# ---------------------------------------------------------------------------
# Actions utilisateur sur une demande
# ---------------------------------------------------------------------------


class AppliquerActionRequest(BaseModel):
    action_id: int
    commentaire: Optional[str] = None


class ActionsPossiblesResponse(BaseModel):
    etape_courante_id: int
    is_valideur: bool
    actions: list[ActionEtapeResponse]


# ---------------------------------------------------------------------------
# Divers
# ---------------------------------------------------------------------------


class ProcessusFilter(BaseModel):
    """Filtre simple utilisé pour lister les étapes d'un processus."""

    code_processus: CodeProcessus = CodeProcessus.CONGE
