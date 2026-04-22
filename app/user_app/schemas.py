"""Pydantic schemas for user_app"""
from datetime import datetime, date
from typing import Optional, List, Generic, TypeVar
from decimal import Decimal
from pydantic import BaseModel, EmailStr, Field, ConfigDict

from app.user_app.constants import (
    DEFAULT_DEVISE,
    DEVISE_MAX_LENGTH,
    SEXE_MAX_LENGTH,
    STATUT_EMPLOI_MAX_LENGTH,
    STATUT_MATRIMONIAL_MAX_LENGTH,
    TYPE_CONTRAT_MAX_LENGTH,
    StatutEmploi,
)

T = TypeVar('T')


# ************************************************************************
# SERVICE SCHEMAS
# ************************************************************************

class ServiceBase(BaseModel):
    code: str = Field(..., max_length=50)
    titre: str = Field(..., max_length=255)
    description: Optional[str] = None
    is_active: bool = True


class ServiceCreate(ServiceBase):
    pass


class ServiceUpdate(BaseModel):
    code: Optional[str] = Field(None, max_length=50)
    titre: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class ServiceResponse(ServiceBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ************************************************************************
# GROUP SCHEMAS
# ************************************************************************

class GroupBase(BaseModel):
    code: str = Field(..., max_length=50)
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    is_active: bool = True


class GroupCreate(GroupBase):
    pass


class GroupUpdate(BaseModel):
    code: Optional[str] = Field(None, max_length=50)
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class GroupResponse(GroupBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GroupCreateWithServices(GroupCreate):
    """Schema for creating group with service associations"""
    service_ids: List[int] = Field(
        default=[],
        description="List of service IDs to associate"
    )


class GroupResponseWithMeta(GroupResponse):
    """Group response with additional metadata"""
    service_groups_count: Optional[int] = None
    user_groups_count: Optional[int] = None


# ************************************************************************
# USER SCHEMAS
# ************************************************************************

class UserBase(BaseModel):
    email: EmailStr
    nom: str = Field(..., max_length=255)
    prenom: str = Field(..., max_length=255)
    phone: Optional[str] = Field(None, max_length=20)
    is_active: bool = True
    is_superuser: bool = False
    is_staff: bool = False


class UserCreate(UserBase):
    password: str = Field(..., min_length=8)
    employe_id: Optional[int] = None


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    nom: Optional[str] = Field(None, max_length=255)
    prenom: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=20)
    password: Optional[str] = Field(None, min_length=8)
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None
    is_staff: Optional[bool] = None
    employe_id: Optional[int] = None


class UserResponse(UserBase):
    id: int
    photo: Optional[str] = None
    last_login: Optional[datetime] = None
    date_joined: datetime
    employe_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ************************************************************************
# AUTH SCHEMAS
# ************************************************************************

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access: str
    refresh: str
    user: dict


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class AccessTokenResponse(BaseModel):
    access_token: str


# ************************************************************************
# EMPLOYE SCHEMAS
# ************************************************************************

class EmployeBase(BaseModel):
    prenom: str = Field(..., max_length=255)
    nom: str = Field(..., max_length=255)
    postnom: Optional[str] = Field(None, max_length=255)
    date_naissance: date
    sexe: str = Field(..., max_length=SEXE_MAX_LENGTH)
    statut_matrimonial: str = Field(
        ..., max_length=STATUT_MATRIMONIAL_MAX_LENGTH
    )
    nationalite: str = Field(..., max_length=100)
    banque: str = Field(..., max_length=255)
    numero_compte: str = Field(..., max_length=255)
    niveau_etude: str = Field(..., max_length=255)
    numero_inss: str = Field(..., max_length=255)
    email_personnel: EmailStr
    email_professionnel: Optional[EmailStr] = None
    telephone_personnel: str = Field(..., max_length=17)
    telephone_professionnel: Optional[str] = Field(None, max_length=17)
    adresse_ligne1: str = Field(..., max_length=200)
    adresse_ligne2: Optional[str] = Field(None, max_length=200)
    ville: Optional[str] = Field(None, max_length=100)
    province: Optional[str] = Field(None, max_length=100)
    code_postal: Optional[str] = Field(None, max_length=20)
    pays: Optional[str] = Field(None, max_length=100)
    matricule: Optional[str] = Field(None, max_length=100)
    poste_id: Optional[int] = None
    responsable_id: Optional[int] = None
    date_embauche: date
    statut_emploi: str = Field(
        default=StatutEmploi.ACTIVE.value,
        max_length=STATUT_EMPLOI_MAX_LENGTH,
    )
    nombre_enfants: int = 0
    nom_conjoint: Optional[str] = Field(None, max_length=100)
    biographie: Optional[str] = None
    nom_contact_urgence: str = Field(..., max_length=100)
    lien_contact_urgence: str = Field(..., max_length=50)
    telephone_contact_urgence: str = Field(..., max_length=17)


class EmployeCreate(EmployeBase):
    pass


class EmployeUpdate(BaseModel):
    prenom: Optional[str] = Field(None, max_length=255)
    nom: Optional[str] = Field(None, max_length=255)
    postnom: Optional[str] = Field(None, max_length=255)
    date_naissance: Optional[date] = None
    sexe: Optional[str] = Field(None, max_length=SEXE_MAX_LENGTH)
    statut_matrimonial: Optional[str] = Field(
        None, max_length=STATUT_MATRIMONIAL_MAX_LENGTH
    )
    nationalite: Optional[str] = Field(None, max_length=100)
    email_personnel: Optional[EmailStr] = None
    telephone_personnel: Optional[str] = Field(None, max_length=17)
    adresse_ligne1: Optional[str] = Field(None, max_length=200)
    date_embauche: Optional[date] = None
    statut_emploi: Optional[str] = Field(
        None, max_length=STATUT_EMPLOI_MAX_LENGTH
    )
    poste_id: Optional[int] = None


class EmployeResponse(EmployeBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EmployeCreateWithUser(EmployeCreate):
    """Schema for creating employee with user account"""
    password: Optional[str] = Field(default="12345678", min_length=5)
    poste_id: int = Field(
        ...,
        description="Poste ID (ServiceGroup) to assign to the user"
    )


class EmployeCreateResponse(BaseModel):
    """Response for employee creation with user account"""
    employee: EmployeResponse
    user: Optional[UserResponse] = None
    group_assigned: bool = False

    model_config = ConfigDict(from_attributes=True)


class EmployeFilter(BaseModel):
    """Filter parameters for employee list"""
    poste_id: Optional[int] = None
    statut_emploi: Optional[str] = None
    search: Optional[str] = None
    expand: Optional[str] = None
    skip: int = 0
    limit: int = 100
    ordering: Optional[str] = '-id'


# ************************************************************************
# CONTRAT SCHEMAS
# ************************************************************************

class ContratBase(BaseModel):
    """Base contract schema"""
    type_contrat: str = Field(..., max_length=TYPE_CONTRAT_MAX_LENGTH)
    date_debut: date
    date_fin: Optional[date] = None
    salaire_base: Decimal = Field(..., gt=0)
    indemnite_logement: Decimal = Field(default=0, ge=0)
    indemnite_transport: Decimal = Field(default=0, ge=0)
    indemnite_deplacement: Decimal = Field(default=0, ge=0)
    indemnite_fonction: Decimal = Field(default=0, ge=0)
    prime_fonction: Decimal = Field(default=0, ge=0)
    autre_avantage: Decimal = Field(default=0, ge=0)
    assurance_patronale: Decimal = Field(default=0, ge=0)
    assurance_salariale: Decimal = Field(default=0, ge=0)
    fpc_patronale: Decimal = Field(default=0, ge=0)
    fpc_salariale: Decimal = Field(default=0, ge=0)
    devise: str = Field(
        default=DEFAULT_DEVISE, max_length=DEVISE_MAX_LENGTH
    )
    is_active: bool = True


class ContratCreate(ContratBase):
    """Schema for creating a contract"""
    employe_id: Optional[int] = None


class ContratUpdate(BaseModel):
    """Schema for updating a contract"""
    type_contrat: Optional[str] = Field(
        None, max_length=TYPE_CONTRAT_MAX_LENGTH
    )
    date_debut: Optional[date] = None
    date_fin: Optional[date] = None
    salaire_base: Optional[Decimal] = Field(None, gt=0)
    indemnite_logement: Optional[Decimal] = Field(None, ge=0)
    indemnite_transport: Optional[Decimal] = Field(None, ge=0)
    indemnite_deplacement: Optional[Decimal] = Field(None, ge=0)
    indemnite_fonction: Optional[Decimal] = Field(None, ge=0)
    prime_fonction: Optional[Decimal] = Field(None, ge=0)
    autre_avantage: Optional[Decimal] = Field(None, ge=0)
    assurance_patronale: Optional[Decimal] = Field(None, ge=0)
    assurance_salariale: Optional[Decimal] = Field(None, ge=0)
    fpc_patronale: Optional[Decimal] = Field(None, ge=0)
    fpc_salariale: Optional[Decimal] = Field(None, ge=0)
    devise: Optional[str] = Field(None, max_length=DEVISE_MAX_LENGTH)
    is_active: Optional[bool] = None


class ContratResponse(ContratBase):
    """Contract response schema"""
    id: int
    employe_id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ************************************************************************
# DOCUMENT SCHEMAS
# ************************************************************************

class DocumentMetadata(BaseModel):
    """Document metadata for upload"""
    type_document: str = Field(..., max_length=50)
    titre: str = Field(..., max_length=255)
    description: Optional[str] = None
    expiry_date: Optional[date] = None


class DocumentCreate(DocumentMetadata):
    """Schema for creating a document"""
    employe_id: int
    fichier: str = Field(..., max_length=500)
    uploaded_by: str = Field(..., max_length=255)


class DocumentUpdate(BaseModel):
    """Schema for updating a document"""
    type_document: Optional[str] = Field(None, max_length=50)
    titre: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    expiry_date: Optional[date] = None


class DocumentResponse(BaseModel):
    """Document response schema"""
    id: int
    employe_id: int
    type_document: str
    titre: str
    description: Optional[str]
    fichier: str
    date_upload: datetime
    expiry_date: Optional[date]
    uploaded_by: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ************************************************************************
# COMPLETE EMPLOYEE CREATION SCHEMAS
# ************************************************************************

class CompleteEmployeeRequest(BaseModel):
    """Request for complete employee creation"""
    employee: EmployeCreate
    contract: ContratCreate
    documents_metadata: List[DocumentMetadata] = []
    password: str = Field(default="12345678", min_length=5)
    group_id: Optional[int] = Field(
        None,
        description="Optional group ID to assign to the user"
    )


class CompleteEmployeeResponse(BaseModel):
    """Response for complete employee creation"""
    success: bool
    message: str
    data: dict

    model_config = ConfigDict(from_attributes=True)


# ************************************************************************
# PERMISSION SCHEMAS
# ************************************************************************

class PermissionBase(BaseModel):
    """Base permission schema"""
    name: str = Field(..., max_length=255)
    codename: str = Field(..., max_length=100)
    content_type: int
    resource: str = Field(..., max_length=100)
    action: str = Field(..., max_length=50)
    description: Optional[str] = None


class PermissionCreate(PermissionBase):
    """Schema for creating a permission"""
    pass


class PermissionResponse(PermissionBase):
    """Permission response schema"""
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ************************************************************************
# GROUP PERMISSION SCHEMAS
# ************************************************************************

class GroupPermissionBase(BaseModel):
    """Base group permission schema"""
    group_id: int
    permission_id: int
    granted: bool = True


class GroupPermissionCreate(GroupPermissionBase):
    """Schema for creating a group permission"""
    created_by_id: Optional[int] = None


class GroupPermissionUpdate(BaseModel):
    """Schema for updating a group permission"""
    granted: Optional[bool] = None


class GroupPermissionResponse(BaseModel):
    """Group permission response schema"""
    id: int
    group_id: int
    permission_id: int
    granted: bool
    created_by_id: Optional[int]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GroupPermissionFilter(BaseModel):
    """Filter parameters for group permission list"""
    group_id: Optional[int] = None
    permission_id: Optional[int] = None
    granted: Optional[bool] = None
    search: Optional[str] = None
    expand: Optional[str] = None
    skip: int = 0
    limit: int = 100
    ordering: Optional[str] = 'group_id'


class UserPermissionsResponse(BaseModel):
    """Response for user effective permissions"""
    groups: List[dict]
    permissions: List[dict]
    permission_count: int
    group_count: int

    model_config = ConfigDict(from_attributes=True)


# ************************************************************************
# SERVICE GROUP SCHEMAS
# ************************************************************************

class ServiceGroupBase(BaseModel):
    """Base service group schema"""
    service_id: int
    group_id: int


class ServiceGroupCreate(ServiceGroupBase):
    """Schema for creating a service group"""
    pass


class ServiceGroupUpdate(BaseModel):
    """Schema for updating a service group"""
    service_id: Optional[int] = None
    group_id: Optional[int] = None


class ServiceGroupResponse(ServiceGroupBase):
    """Service group response schema"""
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ************************************************************************
# USER GROUP SCHEMAS
# ************************************************************************

class UserGroupBase(BaseModel):
    """Base user group schema"""
    user_id: int
    group_id: int
    is_active: bool = True


class UserGroupCreate(UserGroupBase):
    """Schema for creating a user group"""
    assigned_by_id: Optional[int] = None


class UserGroupUpdate(BaseModel):
    """Schema for updating a user group"""
    is_active: Optional[bool] = None


class UserGroupResponse(UserGroupBase):
    """User group response schema"""
    id: int
    assigned_by_id: Optional[int]
    assigned_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ************************************************************************
# PAGINATION SCHEMAS
# ************************************************************************

class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response"""
    results: List[T]
    total: int
    skip: int
    limit: int
    meta: Optional[dict] = None

    model_config = ConfigDict(from_attributes=True)


class GroupFilter(BaseModel):
    """Filter parameters for group list"""
    is_active: Optional[bool] = None
    search: Optional[str] = None
    expand: Optional[str] = None
    skip: int = 0
    limit: int = 100
    ordering: Optional[str] = 'code'


# ************************************************************************
# BULK OPERATION SCHEMAS
# ************************************************************************

class BulkUserGroupAssign(BaseModel):
    """Schema for bulk assigning users to groups"""
    user_ids: List[int] = Field(..., min_length=1)
    group_ids: List[int] = Field(..., min_length=1)
    is_active: bool = Field(default=True)
    replace_existing: bool = Field(default=False)


class BulkUserGroupRemove(BaseModel):
    """Schema for bulk removing users from groups"""
    user_ids: List[int] = Field(..., min_length=1)
    group_ids: List[int] = Field(..., min_length=1)


class BulkGroupPermissionUpdate(BaseModel):
    """Schema for bulk updating group permissions"""
    permissions: List[dict] = Field(..., min_length=1)


class BulkOperationResponse(BaseModel):
    """Response for bulk operations"""
    success: bool
    message: str
    created_count: int = 0
    updated_count: int = 0
    deleted_count: int = 0
    failed_count: int = 0
    errors: List[str] = []

    model_config = ConfigDict(from_attributes=True)


# ************************************************************************
# POSTE SCHEMAS (Wrapper around Group + ServiceGroup)
# ************************************************************************

class PosteBase(BaseModel):
    """Base poste schema - represents a position/role in a service"""
    code: str = Field(..., max_length=50)
    titre: str = Field(..., max_length=255)
    description: Optional[str] = None
    service_id: int


class PosteCreate(PosteBase):
    """Schema for creating a poste (creates Group + ServiceGroup)"""
    pass


class PosteUpdate(BaseModel):
    """Schema for updating a poste"""
    code: Optional[str] = Field(None, max_length=50)
    titre: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    service_id: Optional[int] = None


class PosteResponse(BaseModel):
    """Poste response schema"""
    id: int
    code: str
    titre: str
    description: Optional[str]
    service_id: int
    group_id: int
    service: Optional[ServiceResponse] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
