"""Pydantic schemas for paie_app"""
from datetime import datetime, date
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, ConfigDict
from decimal import Decimal

from app.paie_app.constants import PeriodeStatutTexte


class AlertBase(BaseModel):
    alert_type: str = Field(..., max_length=50)
    severity: str = Field(..., max_length=20)
    status: str = Field(..., max_length=20)
    title: str = Field(..., max_length=255)
    message: str
    details: Optional[Dict[str, Any]] = None
    employe_id: Optional[int] = None
    periode_paie_id: Optional[int] = None
    created_by_id: Optional[int] = None


class AlertCreate(AlertBase):
    pass


class AlertUpdate(BaseModel):
    status: Optional[str] = Field(None, max_length=20)
    acknowledged_by_id: Optional[int] = None
    resolved_by_id: Optional[int] = None
    email_sent: Optional[bool] = None


class AlertResponse(AlertBase):
    id: int
    acknowledged_by_id: Optional[int] = None
    acknowledged_at: Optional[datetime] = None
    resolved_by_id: Optional[int] = None
    resolved_at: Optional[datetime] = None
    email_sent: bool
    email_sent_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class RetenueEmployeBase(BaseModel):
    employe_id: int
    type_retenue: str = Field(..., max_length=50)
    description: str
    montant_mensuel: Decimal
    montant_total: Decimal
    montant_deja_deduit: Decimal = Decimal("0.00")
    date_debut: date
    date_fin: Optional[date] = None
    est_active: bool = True
    est_recurrente: bool = False
    banque_beneficiaire: Optional[str] = Field(None, max_length=255)
    compte_beneficiaire: Optional[str] = Field(None, max_length=255)


class RetenueEmployeCreate(RetenueEmployeBase):
    cree_par_id: Optional[int] = None


class RetenueEmployeUpdate(BaseModel):
    type_retenue: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = None
    montant_mensuel: Optional[Decimal] = None
    montant_total: Optional[Decimal] = None
    montant_deja_deduit: Optional[Decimal] = None
    date_debut: Optional[date] = None
    date_fin: Optional[date] = None
    est_active: Optional[bool] = None
    est_recurrente: Optional[bool] = None


class RetenueEmployeResponse(RetenueEmployeBase):
    id: int
    cree_par_id: Optional[int] = None
    modification_history: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class PeriodePaieBase(BaseModel):
    annee: int
    mois: int = Field(..., ge=1, le=12)
    date_debut: date
    date_fin: date
    statut: str = Field(default=PeriodeStatutTexte.DRAFT.value, max_length=20)


class PeriodePaieCreate(PeriodePaieBase):
    pass


class PeriodePaieUpdate(BaseModel):
    statut: Optional[str] = Field(None, max_length=20)
    traite_par_id: Optional[int] = None
    approuve_par_id: Optional[int] = None


class PeriodePaieResponse(PeriodePaieBase):
    id: int
    traite_par_id: Optional[int] = None
    date_traitement: Optional[datetime] = None
    approuve_par_id: Optional[int] = None
    date_approbation: Optional[datetime] = None
    nombre_employes: Optional[int] = None
    masse_salariale_brute: Optional[Decimal] = None
    total_cotisations_patronales: Optional[Decimal] = None
    total_cotisations_salariales: Optional[Decimal] = None
    total_net_a_payer: Optional[Decimal] = None
    # Workflow
    etape_courante_id: Optional[int] = None
    statut_global_id: Optional[int] = None
    responsable_id: Optional[int] = None
    date_soumission: Optional[datetime] = None
    date_decision_finale: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Schémas workflow paie
# ---------------------------------------------------------------------------


class SubmitPeriodeRequest(BaseModel):
    """Corps de la requête de soumission au workflow."""

    responsable_id: Optional[int] = Field(
        default=None,
        description=(
            "Employé responsable utilisé si une étape du workflow est "
            "configurée avec `is_responsable=True`."
        ),
    )


class AppliquerActionPaieRequest(BaseModel):
    action_id: int
    commentaire: Optional[str] = None


class ActionPaieResponse(BaseModel):
    id: int
    etape_id: int
    nom_action: str
    statut_cible_id: int
    etape_suivante_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class ActionsPaiePossiblesResponse(BaseModel):
    etape_courante_id: Optional[int]
    is_valideur: bool
    actions: List[ActionPaieResponse]


class AttributionPaieResponse(BaseModel):
    id: int
    demande_type: str
    demande_id: int
    etape_id: int
    valideur_attribue_id: int
    date_attribution: datetime
    statut: str

    model_config = ConfigDict(from_attributes=True)


class HistoriquePaieResponse(BaseModel):
    id: int
    demande_type: str
    demande_id: int
    etape_id: int
    action_id: int
    nouveau_statut_id: int
    valideur_id: int
    commentaire: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EntreePaieBase(BaseModel):
    employe_id: int
    periode_paie_id: int
    contrat_reference: Optional[str] = Field(None, max_length=100)
    salaire_base: Decimal
    indemnite_logement: Decimal = Decimal("0.00")
    indemnite_deplacement: Decimal = Decimal("0.00")
    indemnite_fonction: Decimal = Decimal("0.00")
    allocation_familiale: Decimal = Decimal("0.00")
    autres_avantages: Decimal = Decimal("0.00")


class EntreePaieCreate(EntreePaieBase):
    calculated_by_id: Optional[int] = None


class EntreePaieUpdate(BaseModel):
    salaire_base: Optional[Decimal] = None
    indemnite_logement: Optional[Decimal] = None
    indemnite_deplacement: Optional[Decimal] = None
    indemnite_fonction: Optional[Decimal] = None
    allocation_familiale: Optional[Decimal] = None
    autres_avantages: Optional[Decimal] = None
    is_validated: Optional[bool] = None
    validated_by_id: Optional[int] = None


class EntreePaieResponse(EntreePaieBase):
    id: int
    salaire_brut: Optional[Decimal] = None
    cotisations_patronales: Optional[Decimal] = None
    cotisations_salariales: Optional[Decimal] = None
    retenues_diverses: Optional[Decimal] = None
    total_charge_salariale: Optional[Decimal] = None
    base_imposable: Optional[Decimal] = None
    salaire_net: Optional[Decimal] = None
    payslip_generated: bool
    payslip_file: Optional[str] = None
    payslip_generated_at: Optional[datetime] = None
    is_validated: bool
    validation_errors: Optional[Dict[str, Any]] = None
    calculated_by_id: Optional[int] = None
    calculated_at: Optional[datetime] = None
    validated_by_id: Optional[int] = None
    validated_at: Optional[datetime] = None
    modification_history: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)



# Modification History Schemas
class ModificationRecord(BaseModel):
    """Single modification record"""
    timestamp: str
    user_id: int
    user_name: str
    user_email: str
    action: str
    reason: Optional[str] = None
    changes: Dict[str, Dict[str, Any]] = Field(default_factory=dict)


class ModificationHistoryResponse(BaseModel):
    """Response for modification history"""
    resource_type: str
    resource_id: int
    history: list[ModificationRecord]
    total_modifications: int
