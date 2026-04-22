"""User management models"""
from datetime import datetime
from decimal import Decimal
from typing import Optional, TYPE_CHECKING
from sqlalchemy import (
    String, Integer, Boolean, DateTime, Date, Text,
    ForeignKey, UniqueConstraint, Numeric, CheckConstraint
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.user_app.constants import (
    DEFAULT_DEVISE,
    DEVISE_MAX_LENGTH,
    SEXE_MAX_LENGTH,
    STATUT_EMPLOI_MAX_LENGTH,
    STATUT_MATRIMONIAL_MAX_LENGTH,
    TYPE_CONTRAT_MAX_LENGTH,
    Sexe,
    StatutEmploi,
    StatutMatrimonial,
    TypeContrat,
)

if TYPE_CHECKING:
    from app.paie_app.models import RetenueEmploye, Alert


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


class Service(BaseModel):
    """Service/Department model"""
    __tablename__ = "rh_service"

    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    titre: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    service_groups: Mapped[list["ServiceGroup"]] = relationship(
        "ServiceGroup",
        back_populates="service",
        cascade="all, delete-orphan"
    )


class Group(BaseModel):
    """Group/Role model for RBAC"""
    __tablename__ = "user_management_group"

    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    service_groups: Mapped[list["ServiceGroup"]] = relationship(
        "ServiceGroup",
        back_populates="group",
        cascade="all, delete-orphan"
    )
    user_groups: Mapped[list["UserGroup"]] = relationship(
        "UserGroup",
        back_populates="group",
        cascade="all, delete-orphan"
    )
    group_permissions: Mapped[list["GroupPermission"]] = relationship(
        "GroupPermission",
        back_populates="group",
        cascade="all, delete-orphan"
    )


class ServiceGroup(Base):
    """Many-to-many relationship between Service and Group"""
    __tablename__ = "rh_service_group"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("rh_service.id", ondelete="CASCADE"))
    group_id: Mapped[int] = mapped_column(ForeignKey("user_management_group.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # Relationships
    service: Mapped["Service"] = relationship("Service", back_populates="service_groups")
    group: Mapped["Group"] = relationship("Group", back_populates="service_groups")
    employes: Mapped[list["Employe"]] = relationship("Employe", back_populates="poste")

    __table_args__ = (
        UniqueConstraint('service_id', 'group_id', name='uq_service_group'),
    )


class User(BaseModel):
    """User account model"""
    __tablename__ = "user_management_user"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password: Mapped[str] = mapped_column(String(255))
    nom: Mapped[str] = mapped_column(String(255))
    prenom: Mapped[str] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    photo: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)
    is_staff: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    date_joined: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    employe_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("rh_employe.id", ondelete="CASCADE"),
        nullable=True
    )

    # Relationships
    employe: Mapped[Optional["Employe"]] = relationship("Employe", back_populates="user_account")
    user_groups: Mapped[list["UserGroup"]] = relationship(
        "UserGroup",
        back_populates="user",
        foreign_keys="UserGroup.user_id"
    )
    assigned_user_groups: Mapped[list["UserGroup"]] = relationship(
        "UserGroup",
        back_populates="assigned_by_user",
        foreign_keys="UserGroup.assigned_by_id"
    )


class UserGroup(BaseModel):
    """Many-to-many relationship between User and Group with metadata"""
    __tablename__ = "user_management_usergroup"

    user_id: Mapped[int] = mapped_column(ForeignKey("user_management_user.id", ondelete="CASCADE"))
    group_id: Mapped[int] = mapped_column(ForeignKey("user_management_group.id", ondelete="CASCADE"))
    assigned_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("user_management_user.id", ondelete="SET NULL"),
        nullable=True
    )
    assigned_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="user_groups",
        foreign_keys=[user_id]
    )
    group: Mapped["Group"] = relationship("Group", back_populates="user_groups")
    assigned_by_user: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="assigned_user_groups",
        foreign_keys=[assigned_by_id]
    )


class Permission(BaseModel):
    """System permissions for controlling access to resources and actions"""
    __tablename__ = "user_management_permission"

    codename: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[int] = mapped_column(Integer)  # ContentType ID
    resource: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(50))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    group_permissions: Mapped[list["GroupPermission"]] = relationship(
        "GroupPermission",
        back_populates="permission",
        cascade="all, delete-orphan"
    )

    # Table constraints
    # NOTE: no CHECK constraint on `action` — the set of valid actions is
    # driven by the application (create_permissions.py + custom workflows)
    # and must remain extensible (APPROVE, MANAGE_TYPES, MANAGE_SOLDES,
    # MANAGE_WORKFLOW, EXPORT, VIEW, ...). The authoritative match happens
    # on `codename` in PermissionService.check_permission.
    __table_args__ = (
        UniqueConstraint('resource', 'action', name='uq_permission_resource_action'),
    )

    def __str__(self) -> str:
        return f"{self.resource}.{self.action}"


class GroupPermission(BaseModel):
    """Many-to-many relationship between Group and Permission"""
    __tablename__ = "user_management_grouppermission"

    group_id: Mapped[int] = mapped_column(
        ForeignKey("user_management_group.id", ondelete="CASCADE")
    )
    permission_id: Mapped[int] = mapped_column(
        ForeignKey("user_management_permission.id", ondelete="CASCADE")
    )
    granted: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("user_management_user.id", ondelete="SET NULL"),
        nullable=True
    )

    # Relationships
    group: Mapped["Group"] = relationship("Group", back_populates="group_permissions")
    permission: Mapped["Permission"] = relationship(
        "Permission", back_populates="group_permissions"
    )
    created_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[created_by_id]
    )

    # Table constraints
    __table_args__ = (
        UniqueConstraint('group_id', 'permission_id', name='uq_group_permission'),
    )

    def __str__(self) -> str:
        status = "granted" if self.granted else "denied"
        return f"{self.group.code} -> {self.permission.codename} ({status})"


class Employe(BaseModel):
    """Enhanced Employee model with complete personal and professional fields"""
    __tablename__ = "rh_employe"

    # Personal information
    prenom: Mapped[str] = mapped_column(String(255))
    nom: Mapped[str] = mapped_column(String(255))
    postnom: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    date_naissance: Mapped[Date] = mapped_column(Date)
    sexe: Mapped[str] = mapped_column(String(SEXE_MAX_LENGTH))  # see Sexe enum
    statut_matrimonial: Mapped[str] = mapped_column(
        String(STATUT_MATRIMONIAL_MAX_LENGTH)
    )  # see StatutMatrimonial enum
    nationalite: Mapped[str] = mapped_column(String(100))

    # Banking information
    banque: Mapped[str] = mapped_column(String(255))
    numero_compte: Mapped[str] = mapped_column(String(255))
    niveau_etude: Mapped[str] = mapped_column(String(255))
    numero_inss: Mapped[str] = mapped_column(String(255))

    # Contact information
    email_personnel: Mapped[str] = mapped_column(String(255))
    email_professionnel: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    telephone_personnel: Mapped[str] = mapped_column(String(17))
    telephone_professionnel: Mapped[Optional[str]] = mapped_column(
        String(17), nullable=True
    )

    # Address
    adresse_ligne1: Mapped[str] = mapped_column(String(200))
    adresse_ligne2: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    ville: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    province: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    code_postal: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    pays: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    matricule: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Employment information
    poste_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("rh_service_group.id", ondelete="SET NULL"),
        nullable=True
    )
    responsable_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("rh_employe.id", ondelete="SET NULL"),
        nullable=True
    )
    date_embauche: Mapped[Date] = mapped_column(Date)
    statut_emploi: Mapped[str] = mapped_column(
        String(STATUT_EMPLOI_MAX_LENGTH),
        default=StatutEmploi.ACTIVE.value,
    )

    # Family information
    nombre_enfants: Mapped[int] = mapped_column(Integer, default=0)
    nom_conjoint: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    biographie: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Emergency contact
    nom_contact_urgence: Mapped[str] = mapped_column(String(100))
    lien_contact_urgence: Mapped[str] = mapped_column(String(50))
    telephone_contact_urgence: Mapped[str] = mapped_column(String(17))

    # Relationships
    poste: Mapped[Optional["ServiceGroup"]] = relationship(
        "ServiceGroup", back_populates="employes"
    )
    responsable: Mapped[Optional["Employe"]] = relationship(
        "Employe",
        remote_side="Employe.id",
        foreign_keys=[responsable_id],
        back_populates="subordonnes"
    )
    subordonnes: Mapped[list["Employe"]] = relationship(
        "Employe",
        foreign_keys="Employe.responsable_id",
        back_populates="responsable"
    )
    user_account: Mapped[Optional["User"]] = relationship(
        "User", back_populates="employe"
    )
    contrats: Mapped[list["Contrat"]] = relationship(
        "Contrat", back_populates="employe", cascade="all, delete-orphan"
    )
    documents: Mapped[list["Document"]] = relationship(
        "Document", back_populates="employe", cascade="all, delete-orphan"
    )
    retenues: Mapped[list["RetenueEmploye"]] = relationship(
        "RetenueEmploye", back_populates="employe", cascade="all, delete-orphan"
    )
    alerts: Mapped[list["Alert"]] = relationship(
        "Alert", back_populates="employe", cascade="all, delete-orphan"
    )

    # Table constraints
    # CHECK expressions are rebuilt from the corresponding enum in
    # app.user_app.constants so that the DB constraint stays in sync with
    # the Python-level source of truth.
    __table_args__ = (
        CheckConstraint(
            Sexe.check_constraint_expression("sexe"),
            name="ck_employe_sexe"
        ),
        CheckConstraint(
            StatutMatrimonial.check_constraint_expression("statut_matrimonial"),
            name="ck_employe_statut_matrimonial"
        ),
        CheckConstraint(
            StatutEmploi.check_constraint_expression("statut_emploi"),
            name="ck_employe_statut_emploi"
        ),
        CheckConstraint(
            "nombre_enfants >= 0",
            name="ck_employe_nombre_enfants_positive"
        ),
        CheckConstraint(
            "date_embauche <= CURRENT_DATE",
            name="ck_employe_date_embauche_past"
        ),
    )

    @property
    def full_name(self) -> str:
        """Returns the full name of the employee"""
        parts = [self.nom]
        if self.postnom:
            parts.append(self.postnom)
        parts.append(self.prenom)
        return " ".join(parts)

    def __str__(self) -> str:
        return f"{self.id} - {self.nom} {self.prenom}"


class Contrat(BaseModel):
    """Enhanced Contract model with complete salary components"""
    __tablename__ = "rh_contrat"

    employe_id: Mapped[int] = mapped_column(
        ForeignKey("rh_employe.id", ondelete="CASCADE")
    )
    type_contrat: Mapped[str] = mapped_column(
        String(TYPE_CONTRAT_MAX_LENGTH)
    )  # see TypeContrat enum
    date_debut: Mapped[Date] = mapped_column(Date)
    date_fin: Mapped[Optional[Date]] = mapped_column(Date, nullable=True)

    # Salary components
    salaire_base: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    indemnite_logement: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    indemnite_transport: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    indemnite_deplacement: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    indemnite_fonction: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    prime_fonction: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    autre_avantage: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)

    # Social contributions
    assurance_patronale: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    assurance_salariale: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    fpc_patronale: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    fpc_salariale: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)

    devise: Mapped[str] = mapped_column(
        String(DEVISE_MAX_LENGTH), default=DEFAULT_DEVISE
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    employe: Mapped["Employe"] = relationship("Employe", back_populates="contrats")

    # Table constraints
    __table_args__ = (
        CheckConstraint(
            TypeContrat.check_constraint_expression("type_contrat"),
            name="ck_contrat_type_contrat"
        ),
        CheckConstraint(
            "salaire_base > 0",
            name="ck_contrat_salaire_base_positive"
        ),
        CheckConstraint(
            "indemnite_logement >= 0",
            name="ck_contrat_indemnite_logement_positive"
        ),
        CheckConstraint(
            "indemnite_transport >= 0",
            name="ck_contrat_indemnite_transport_positive"
        ),
        CheckConstraint(
            "indemnite_fonction >= 0",
            name="ck_contrat_indemnite_fonction_positive"
        ),
        CheckConstraint(
            "date_fin IS NULL OR date_fin > date_debut",
            name="ck_contrat_date_fin_after_debut"
        ),
    )

    def __str__(self) -> str:
        return f"{self.type_contrat} - {self.salaire_base} {self.devise}"


class Document(BaseModel):
    """Enhanced Document model for employee documents"""
    __tablename__ = "rh_document"

    employe_id: Mapped[int] = mapped_column(
        ForeignKey("rh_employe.id", ondelete="CASCADE")
    )
    type_document: Mapped[str] = mapped_column(String(50))
    titre: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fichier: Mapped[str] = mapped_column(String(500))
    date_upload: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expiry_date: Mapped[Optional[Date]] = mapped_column(Date, nullable=True)
    uploaded_by: Mapped[str] = mapped_column(String(255))

    # Relationships
    employe: Mapped["Employe"] = relationship("Employe", back_populates="documents")

    def __str__(self) -> str:
        return f"{self.employe.full_name} - {self.titre}"
