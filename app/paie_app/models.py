"""Payroll management models"""
from datetime import datetime, date
from typing import Optional, TYPE_CHECKING
from decimal import Decimal
from sqlalchemy import (
    String, Integer, Boolean, DateTime, Date, Text, Numeric,
    ForeignKey, UniqueConstraint, JSON
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.paie_app.constants import (
    AlertSeverity,
    AlertStatus,
    PeriodeStatutTexte,
)

if TYPE_CHECKING:
    from app.user_app.models import Employe


class BaseModel(Base):
    """Abstract base model with common fields"""
    __abstract__ = True

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )


class Alert(BaseModel):
    """Alert model for payroll system"""
    __tablename__ = "paie_alert"

    alert_type: Mapped[str] = mapped_column(String(50))
    severity: Mapped[str] = mapped_column(
        String(20), default=AlertSeverity.MEDIUM.value
    )
    status: Mapped[str] = mapped_column(
        String(20), default=AlertStatus.ACTIVE.value
    )

    title: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSON, default=dict)

    employe_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("rh_employe.id", ondelete="CASCADE"),
        nullable=True
    )
    periode_paie_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("paie_periode.id", ondelete="CASCADE"),
        nullable=True
    )

    created_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("user_management_user.id", ondelete="SET NULL"),
        nullable=True
    )
    acknowledged_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("user_management_user.id", ondelete="SET NULL"),
        nullable=True
    )
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    resolved_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("user_management_user.id", ondelete="SET NULL"),
        nullable=True
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )

    email_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    email_sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )

    # Relationships
    employe: Mapped[Optional["Employe"]] = relationship(
        "Employe", back_populates="alerts"
    )


class RetenueEmploye(BaseModel):
    """Employee deduction model"""
    __tablename__ = "paie_retenu_salaire"

    employe_id: Mapped[int] = mapped_column(
        ForeignKey("rh_employe.id", ondelete="CASCADE")
    )
    type_retenue: Mapped[str] = mapped_column(String(20))
    description: Mapped[str] = mapped_column(String(500))
    montant_mensuel: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    montant_total: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    montant_deja_deduit: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=0
    )
    date_debut: Mapped[date] = mapped_column(Date)
    date_fin: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    est_active: Mapped[bool] = mapped_column(Boolean, default=True)
    est_recurrente: Mapped[bool] = mapped_column(Boolean, default=True)
    cree_par_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("user_management_user.id", ondelete="SET NULL"),
        nullable=True
    )

    banque_beneficiaire: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    compte_beneficiaire: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    modification_history: Mapped[list] = mapped_column(JSON, default=list)

    # Relationships
    employe: Mapped["Employe"] = relationship(
        "Employe", back_populates="retenues"
    )


class PeriodePaie(BaseModel):
    """Payroll period model.

    La période de paie porte désormais un workflow dynamique piloté par les
    tables génériques partagées avec ``conge_app`` (``cg_statut_processus``,
    ``cg_etape_processus``, ``cg_demande_attribution``, ``cg_historique_demande``).
    Le champ ``statut`` texte historique est conservé pour la rétro-compatibilité :
    il reflète l'état global mais le workflow reste l'unique source de vérité.
    """

    __tablename__ = "paie_periode"

    annee: Mapped[int] = mapped_column(Integer)
    mois: Mapped[int] = mapped_column(Integer)
    date_debut: Mapped[date] = mapped_column(Date)
    date_fin: Mapped[date] = mapped_column(Date)
    statut: Mapped[str] = mapped_column(
        String(20), default=PeriodeStatutTexte.DRAFT.value
    )

    traite_par_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("user_management_user.id", ondelete="SET NULL"),
        nullable=True
    )
    date_traitement: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    approuve_par_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("user_management_user.id", ondelete="SET NULL"),
        nullable=True
    )
    date_approbation: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    nombre_employes: Mapped[int] = mapped_column(Integer, default=0)
    masse_salariale_brute: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    total_cotisations_patronales: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    total_cotisations_salariales: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    total_net_a_payer: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)

    # -- Workflow dynamique (partagé avec conge_app) --
    etape_courante_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("cg_etape_processus.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    statut_global_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("cg_statut_processus.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    responsable_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("rh_employe.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    date_soumission: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    date_decision_finale: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    entries: Mapped[list["EntreePaie"]] = relationship(
        "EntreePaie",
        back_populates="periode_paie",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint('annee', 'mois', name='uq_annee_mois'),
    )


class EntreePaie(BaseModel):
    """Payroll entry model"""
    __tablename__ = "paie_entree"

    employe_id: Mapped[int] = mapped_column(ForeignKey("rh_employe.id", ondelete="CASCADE"))
    periode_paie_id: Mapped[int] = mapped_column(ForeignKey("paie_periode.id", ondelete="CASCADE"))

    contrat_reference: Mapped[dict] = mapped_column(JSON, default=dict)

    salaire_base: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    indemnite_logement: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    indemnite_deplacement: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    indemnite_fonction: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    allocation_familiale: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    autres_avantages: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    salaire_brut: Mapped[Decimal] = mapped_column(Numeric(12, 2))

    cotisations_patronales: Mapped[dict] = mapped_column(JSON, default=dict)
    cotisations_salariales: Mapped[dict] = mapped_column(JSON, default=dict)
    retenues_diverses: Mapped[dict] = mapped_column(JSON, default=dict)

    total_charge_salariale: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    base_imposable: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    salaire_net: Mapped[Decimal] = mapped_column(Numeric(12, 2))

    payslip_generated: Mapped[bool] = mapped_column(Boolean, default=False)
    payslip_file: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    payslip_generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    is_validated: Mapped[bool] = mapped_column(Boolean, default=False)
    validation_errors: Mapped[list] = mapped_column(JSON, default=list)

    calculated_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("user_management_user.id", ondelete="SET NULL"),
        nullable=True
    )
    calculated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    validated_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("user_management_user.id", ondelete="SET NULL"),
        nullable=True
    )
    validated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    modification_history: Mapped[list] = mapped_column(JSON, default=list)

    # Relationships
    periode_paie: Mapped["PeriodePaie"] = relationship("PeriodePaie", back_populates="entries")

    __table_args__ = (
        UniqueConstraint('employe_id', 'periode_paie_id', name='uq_employe_periode'),
    )
