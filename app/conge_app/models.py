"""Leave management SQLAlchemy models (workflow-based)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class _TimestampMixin:
    """Champs de timestamp réutilisés par tous les modèles du module."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class TypeConge(_TimestampMixin, Base):
    """Type de congé (ex: Congé Annuel, Maladie, Sans solde)."""

    __tablename__ = "cg_type_conge"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    nom: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    nb_jours_max_par_an: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    report_autorise: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    necessite_validation: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    soldes: Mapped[list["SoldeConge"]] = relationship(
        "SoldeConge", back_populates="type_conge", cascade="all, delete-orphan"
    )
    demandes: Mapped[list["DemandeConge"]] = relationship(
        "DemandeConge", back_populates="type_conge", cascade="all, delete-orphan"
    )


class SoldeConge(_TimestampMixin, Base):
    """Solde annuel par employé et par type de congé."""

    __tablename__ = "cg_solde_conge"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    employe_id: Mapped[int] = mapped_column(
        ForeignKey("rh_employe.id", ondelete="CASCADE"), index=True, nullable=False
    )
    type_conge_id: Mapped[int] = mapped_column(
        ForeignKey("cg_type_conge.id", ondelete="CASCADE"), index=True, nullable=False
    )
    annee: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    alloue: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    utilise: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    restant: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    reporte: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    date_expiration: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    type_conge: Mapped["TypeConge"] = relationship("TypeConge", back_populates="soldes")

    __table_args__ = (
        UniqueConstraint("employe_id", "type_conge_id", "annee", name="uq_solde_employe_type_annee"),
    )


class StatutProcessus(_TimestampMixin, Base):
    """Statut générique utilisable par n'importe quel processus de workflow."""

    __tablename__ = "cg_statut_processus"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code_statut: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)


class EtapeProcessus(_TimestampMixin, Base):
    """Étape du workflow d'un processus (ex: validation N+1 puis RH pour CONGE)."""

    __tablename__ = "cg_etape_processus"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code_processus: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    ordre: Mapped[int] = mapped_column(Integer, nullable=False)
    nom_etape: Mapped[str] = mapped_column(String(100), nullable=False)
    poste_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("rh_service_group.id", ondelete="SET NULL"), nullable=True, index=True
    )
    is_responsable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    actions: Mapped[list["ActionEtapeProcessus"]] = relationship(
        "ActionEtapeProcessus",
        back_populates="etape",
        foreign_keys="ActionEtapeProcessus.etape_id",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("code_processus", "ordre", name="uq_etape_processus_ordre"),
    )


class ActionEtapeProcessus(_TimestampMixin, Base):
    """Action applicable sur une étape (ex: APPROUVER, REJETER)."""

    __tablename__ = "cg_action_etape_processus"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    etape_id: Mapped[int] = mapped_column(
        ForeignKey("cg_etape_processus.id", ondelete="CASCADE"), nullable=False, index=True
    )
    nom_action: Mapped[str] = mapped_column(String(50), nullable=False)
    statut_cible_id: Mapped[int] = mapped_column(
        ForeignKey("cg_statut_processus.id", ondelete="RESTRICT"), nullable=False
    )
    etape_suivante_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("cg_etape_processus.id", ondelete="SET NULL"), nullable=True
    )

    etape: Mapped["EtapeProcessus"] = relationship(
        "EtapeProcessus", foreign_keys=[etape_id], back_populates="actions"
    )
    statut_cible: Mapped["StatutProcessus"] = relationship(
        "StatutProcessus", foreign_keys=[statut_cible_id]
    )
    etape_suivante: Mapped[Optional["EtapeProcessus"]] = relationship(
        "EtapeProcessus", foreign_keys=[etape_suivante_id]
    )


class DemandeConge(_TimestampMixin, Base):
    """Demande de congé d'un employé."""

    __tablename__ = "cg_demande_conge"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    employe_id: Mapped[int] = mapped_column(
        ForeignKey("rh_employe.id", ondelete="CASCADE"), index=True, nullable=False
    )
    type_conge_id: Mapped[int] = mapped_column(
        ForeignKey("cg_type_conge.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    date_debut: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    demi_journee_debut: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    date_fin: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    demi_journee_fin: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    nb_jours_ouvres: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    etape_courante_id: Mapped[int] = mapped_column(
        ForeignKey("cg_etape_processus.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    responsable_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("rh_employe.id", ondelete="SET NULL"), nullable=True, index=True
    )
    statut_global_id: Mapped[int] = mapped_column(
        ForeignKey("cg_statut_processus.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    date_soumission: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    date_decision_finale: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    type_conge: Mapped["TypeConge"] = relationship("TypeConge", back_populates="demandes")
    etape_courante: Mapped["EtapeProcessus"] = relationship(
        "EtapeProcessus", foreign_keys=[etape_courante_id]
    )
    statut_global: Mapped["StatutProcessus"] = relationship(
        "StatutProcessus", foreign_keys=[statut_global_id]
    )

    __table_args__ = (
        CheckConstraint(
            "demi_journee_debut IS NULL OR demi_journee_debut IN ('matin', 'apres-midi')",
            name="ck_demi_journee_debut",
        ),
        CheckConstraint(
            "demi_journee_fin IS NULL OR demi_journee_fin IN ('matin', 'apres-midi')",
            name="ck_demi_journee_fin",
        ),
        CheckConstraint("date_fin >= date_debut", name="ck_demande_dates_ordre"),
    )


class DemandeAttribution(_TimestampMixin, Base):
    """Attribution d'une étape à un valideur (polymorphique pour être réutilisable)."""

    __tablename__ = "cg_demande_attribution"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    demande_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    demande_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    etape_id: Mapped[int] = mapped_column(
        ForeignKey("cg_etape_processus.id", ondelete="CASCADE"), nullable=False, index=True
    )
    valideur_attribue_id: Mapped[int] = mapped_column(
        ForeignKey("rh_employe.id", ondelete="CASCADE"), nullable=False, index=True
    )
    date_attribution: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    statut: Mapped[str] = mapped_column(
        String(30), default="en_attente", nullable=False, index=True
    )

    __table_args__ = (
        CheckConstraint(
            "statut IN ('en_attente', 'prise_en_charge', 'traitee')",
            name="ck_attribution_statut",
        ),
        Index("idx_attribution_demande", "demande_type", "demande_id"),
    )


class HistoriqueDemande(_TimestampMixin, Base):
    """Journal des actions appliquées sur une demande (polymorphique)."""

    __tablename__ = "cg_historique_demande"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    demande_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    demande_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    etape_id: Mapped[int] = mapped_column(
        ForeignKey("cg_etape_processus.id", ondelete="RESTRICT"), nullable=False
    )
    action_id: Mapped[int] = mapped_column(
        ForeignKey("cg_action_etape_processus.id", ondelete="RESTRICT"), nullable=False
    )
    nouveau_statut_id: Mapped[int] = mapped_column(
        ForeignKey("cg_statut_processus.id", ondelete="RESTRICT"), nullable=False
    )
    valideur_id: Mapped[int] = mapped_column(
        ForeignKey("rh_employe.id", ondelete="CASCADE"), nullable=False
    )
    commentaire: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("idx_historique_demande", "demande_type", "demande_id"),
    )
