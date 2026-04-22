"""FastAPI routes for user_app"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, BackgroundTasks, Form, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
import json

from app.core.database import get_db
from app.core.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    create_refresh_token,
    verify_token,
    get_current_user
)
from app.core.permissions import require_permission
from app.user_app import schemas
from app.user_app.models import Service, Group, ServiceGroup, User, Employe, Permission, GroupPermission, UserGroup, Contrat, Document
from app.user_app.services import EmployeeService, GroupService, PermissionService
from app.audit_app.constants import AuditAction, AuditResourceType
from app.audit_app.services import AuditService

router = APIRouter()

# ************************************************************************
# AUTHENTIFICATION ROUTES
# ************************************************************************
auth_router = APIRouter(prefix="/auth", tags=["Authentication"])


@auth_router.post("/login", response_model=schemas.TokenResponse)
async def login(
    credentials: schemas.LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Authenticate user and return JWT tokens"""
    # Get user by email
    result = await db.execute(select(User).where(User.email == credentials.email))
    user = result.scalar_one_or_none()

    if not user:
        # Log failed login attempt
        await AuditService.log_login(
            db=db,
            user=None,
            request=request,
            success=False
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Aucun utilisateur correspondant à cette adresse email"
        )

    # Verify password
    if not verify_password(credentials.password, user.password):
        # Log failed login attempt
        await AuditService.log_login(
            db=db,
            user=user,
            request=request,
            success=False
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Mot de passe incorrect"
        )

    # Check if user is active
    if not user.is_active:
        # Log failed login attempt
        await AuditService.log_login(
            db=db,
            user=user,
            request=request,
            success=False
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ce compte est désactivé"
        )

    # Create tokens
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    # Log successful login
    await AuditService.log_login(
        db=db,
        user=user,
        request=request,
        success=True
    )

    return {
        "access": access_token,
        "refresh": refresh_token,
        "user": {
            "id": user.id,
            "email": user.email,
            "nom": user.nom,
            "prenom": user.prenom,
            "is_superuser": user.is_superuser
        }
    }


@auth_router.post("/refresh", response_model=schemas.AccessTokenResponse)
async def refresh_access_token(request: schemas.RefreshTokenRequest):
    """Refresh access token using refresh token"""
    try:
        payload = verify_token(request.refresh_token, "refresh")
        new_access_token = create_access_token(payload["user_id"])
        return {"access_token": new_access_token}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        ) from e


@auth_router.post("/logout")
async def logout(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Logout user (client should delete tokens)"""
    # Log the logout
    await AuditService.log_logout(
        db=db,
        user=current_user,
        request=request
    )

    return {
        "message": "Déconnecté avec succès. Supprimez les tokens côté client."
    }


@auth_router.get("/protected")
async def protected_route(current_user: User = Depends(get_current_user)):
    """Protected route for testing authentication"""
    return {
        "message": f"Bonjour {current_user.prenom or current_user.nom}",
        "user_id": current_user.id
    }

# ************************************************************************
# SERVICE ROUTES
# ************************************************************************

service_router = APIRouter(prefix="/services", tags=["Services"])


@service_router.get("/")
async def list_services(
    skip: int = 0,
    limit: int = 100,
    no_pagination: bool = Query(False),
    expand: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_permission("service", "read"))
):
    """List all services with optional pagination and expansion"""
    from app.core.query_utils import parse_expand_param, apply_expansion
    query = select(Service)

    # Apply expansion
    if expand:
        expand_fields = parse_expand_param(expand)
        query = apply_expansion(query, Service, expand_fields)

    # Get total count
    count_query = select(func.count()).select_from(Service)
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination if requested
    if not no_pagination:
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        services = result.scalars().all()
        return {
            "results": list(services),
            "total": total,
            "skip": skip,
            "limit": limit
        }
    else:
        result = await db.execute(query)
        services = result.scalars().all()
        return {
            "results": list(services),
            "total": total
        }


@service_router.post("/", response_model=schemas.ServiceResponse)
async def create_service(
    service: schemas.ServiceCreate,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_permission("service", "create"))
):
    """Create a new service"""
    # Check if code already exists
    existing_service = await db.execute(
        select(Service).where(Service.code == service.code)
    )
    if existing_service.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ce code existe déjà"
        )

    db_service = Service(**service.model_dump())
    db.add(db_service)
    await db.commit()
    await db.refresh(db_service)
    return db_service


@service_router.get("/{service_id}", response_model=schemas.ServiceResponse)
async def get_service(
    service_id: int,
    expand: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_permission("service", "read"))
):
    """Get service by ID with optional expansion"""
    from app.core.query_utils import parse_expand_param, apply_expansion
    query = select(Service).where(Service.id == service_id)

    # Apply expansion
    if expand:
        expand_fields = parse_expand_param(expand)
        query = apply_expansion(query, Service, expand_fields)

    result = await db.execute(query)
    service = result.scalar_one_or_none()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    return service


@service_router.put("/{service_id}", response_model=schemas.ServiceResponse)
async def update_service(
    service_id: int,
    service_update: schemas.ServiceUpdate,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_permission("service", "update"))
):
    """Update service"""
    from sqlalchemy import select
    result = await db.execute(
        select(Service).where(Service.id == service_id)
    )
    service = result.scalar_one_or_none()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    for key, value in service_update.model_dump(exclude_unset=True).items():
        setattr(service, key, value)

    await db.commit()
    await db.refresh(service)
    return service


@service_router.delete("/{service_id}")
async def delete_service(
    service_id: int,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_permission("service", "delete"))
):
    """Delete service"""
    from sqlalchemy import select
    result = await db.execute(
        select(Service).where(Service.id == service_id)
    )
    service = result.scalar_one_or_none()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    await db.delete(service)
    await db.commit()
    return {"message": "Service deleted successfully"}


# ************************************************************************
# SERVICE GROUP ROUTES
# ************************************************************************

service_group_router = APIRouter(
    prefix="/service-groups",
    tags=["Service Groups"]
)


@service_group_router.get("/")
async def list_service_groups(
    service_id: Optional[int] = Query(None),
    group_id: Optional[int] = Query(None),
    skip: int = 0,
    limit: int = 100,
    no_pagination: bool = Query(False),
    expand: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_permission("service_group", "read"))
):
    """List service groups with optional filters and pagination"""
    from app.core.query_utils import parse_expand_param, apply_expansion
    from app.user_app.models import ServiceGroup

    query = select(ServiceGroup)

    # Apply filters
    if service_id is not None:
        query = query.where(ServiceGroup.service_id == service_id)
    if group_id is not None:
        query = query.where(ServiceGroup.group_id == group_id)

    # Get total count (before expansion to avoid unnecessary joins)
    count_query = select(func.count()).select_from(ServiceGroup)
    if service_id is not None:
        count_query = count_query.where(ServiceGroup.service_id == service_id)
    if group_id is not None:
        count_query = count_query.where(ServiceGroup.group_id == group_id)
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply expansion
    if expand:
        expand_fields = parse_expand_param(expand)
        query = apply_expansion(query, ServiceGroup, expand_fields)

    # Apply pagination if requested
    if not no_pagination:
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        service_groups = result.scalars().all()
        return {
            "results": list(service_groups),
            "total": total,
            "skip": skip,
            "limit": limit
        }
    else:
        result = await db.execute(query)
        service_groups = result.scalars().all()
        return {
            "results": list(service_groups),
            "total": total
        }


@service_group_router.post(
    "/",
    response_model=schemas.ServiceGroupResponse,
    status_code=status.HTTP_201_CREATED
)
async def create_service_group(
    service_group: schemas.ServiceGroupCreate,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_permission("service_group", "create"))
):
    """Create a service group association"""
    from app.user_app.models import ServiceGroup

    # Validate service exists
    result = await db.execute(
        select(Service).where(Service.id == service_group.service_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=404,
            detail=f"Service with ID {service_group.service_id} not found"
        )

    # Validate group exists
    result = await db.execute(
        select(Group).where(Group.id == service_group.group_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=404,
            detail=f"Group with ID {service_group.group_id} not found"
        )

    # Check for duplicate
    result = await db.execute(
        select(ServiceGroup).where(
            ServiceGroup.service_id == service_group.service_id,
            ServiceGroup.group_id == service_group.group_id
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="Service group association already exists"
        )

    # Create service group
    db_service_group = ServiceGroup(**service_group.model_dump())
    db.add(db_service_group)
    await db.commit()
    await db.refresh(db_service_group)
    return db_service_group


@service_group_router.get(
    "/{service_group_id}",
    response_model=schemas.ServiceGroupResponse
)
async def get_service_group(
    service_group_id: int,
    expand: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_permission("service_group", "read"))
):
    """Get service group by ID with optional expansion"""
    from app.core.query_utils import parse_expand_param, apply_expansion
    from app.user_app.models import ServiceGroup

    query = select(ServiceGroup).where(ServiceGroup.id == service_group_id)

    # Apply expansion
    if expand:
        expand_fields = parse_expand_param(expand)
        query = apply_expansion(query, ServiceGroup, expand_fields)

    result = await db.execute(query)
    service_group = result.scalar_one_or_none()
    if not service_group:
        raise HTTPException(status_code=404, detail="Service group not found")
    return service_group


@service_group_router.put(
    "/{service_group_id}",
    response_model=schemas.ServiceGroupResponse
)
async def update_service_group(
    service_group_id: int,
    service_group_update: schemas.ServiceGroupUpdate,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_permission("service_group", "update"))
):
    """Update service group"""
    from app.user_app.models import ServiceGroup

    result = await db.execute(
        select(ServiceGroup).where(ServiceGroup.id == service_group_id)
    )
    service_group = result.scalar_one_or_none()
    if not service_group:
        raise HTTPException(status_code=404, detail="Service group not found")

    # Update fields
    update_data = service_group_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(service_group, key, value)

    await db.commit()
    await db.refresh(service_group)
    return service_group


@service_group_router.delete("/{service_group_id}")
async def delete_service_group(
    service_group_id: int,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_permission("service_group", "delete"))
):
    """Delete service group"""
    from app.user_app.models import ServiceGroup

    result = await db.execute(
        select(ServiceGroup).where(ServiceGroup.id == service_group_id)
    )
    service_group = result.scalar_one_or_none()
    if not service_group:
        raise HTTPException(status_code=404, detail="Service group not found")

    await db.delete(service_group)
    await db.commit()
    return {"message": "Service group deleted successfully"}


# ************************************************************************
# GROUPE ROUTES
# ************************************************************************

group_router = APIRouter(prefix="/groups", tags=["Groups"])


@group_router.get("/")
async def list_groups(
    is_active: Optional[bool] = Query(None),
    skip: int = 0,
    limit: int = 100,
    no_pagination: bool = Query(False),
    expand: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_permission("group", "read"))
):
    """List all groups with optional pagination and expansion"""
    from app.core.query_utils import parse_expand_param, apply_expansion

    query = select(Group)

    # Apply filters
    if is_active is not None:
        query = query.where(Group.is_active == is_active)

    # Apply expansion
    if expand:
        expand_fields = parse_expand_param(expand)
        query = apply_expansion(query, Group, expand_fields)

    # Get total count
    count_query = select(func.count()).select_from(Group)
    if is_active is not None:
        count_query = count_query.where(Group.is_active == is_active)
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply ordering
    query = query.order_by(Group.code)

    # Apply pagination if requested
    if not no_pagination:
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        groups = result.scalars().all()
        return {
            "results": list(groups),
            "total": total,
            "skip": skip,
            "limit": limit
        }
    else:
        result = await db.execute(query)
        groups = result.scalars().all()
        return {
            "results": list(groups),
            "total": total
        }


@group_router.post("/", response_model=schemas.GroupResponse)
async def create_group(
    group: schemas.GroupCreateWithServices,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_permission("group", "create"))
):
    """Create a new group with service associations"""
    try:
        group_data = group.model_dump(exclude={"service_ids"})
        db_group, _ = await GroupService.create_with_services(
            db, group_data, group.service_ids
        )
        await db.commit()
        await db.refresh(db_group)
        return db_group
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        ) from e


@group_router.get("/{group_id}", response_model=schemas.GroupResponse)
async def get_group(
    group_id: int,
    expand: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_permission("group", "read"))
):
    """Get group by ID with optional expansion"""
    from app.core.query_utils import parse_expand_param, apply_expansion

    query = select(Group).where(Group.id == group_id)

    # Apply expansion
    if expand:
        expand_fields = parse_expand_param(expand)
        query = apply_expansion(query, Group, expand_fields)

    result = await db.execute(query)
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    return group


@group_router.put("/{group_id}", response_model=schemas.GroupResponse)
async def update_group(
    group_id: int,
    group_update: schemas.GroupUpdate,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_permission("group", "update"))
):
    """Update group"""
    from sqlalchemy import select
    result = await db.execute(
        select(Group).where(Group.id == group_id)
    )
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    for key, value in group_update.model_dump(exclude_unset=True).items():
        setattr(group, key, value)

    await db.commit()
    await db.refresh(group)
    return group


@group_router.delete("/{group_id}")
async def delete_group(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_permission("group", "delete"))
):
    """Delete group with validation"""
    try:
        result = await GroupService.delete_with_validation(db, group_id)
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        ) from e


# ************************************************************************
# EMPLOYE ROUTES
# ************************************************************************
employe_router = APIRouter(prefix="/employees", tags=["Employees"])


@employe_router.get("/")
async def list_employees(
    poste_id: Optional[int] = Query(None),
    statut_emploi: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    expand: Optional[str] = Query(None),
    ordering: Optional[str] = Query('-id'),
    skip: int = 0,
    limit: int = 100,
    no_pagination: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_permission("employe", "read"))
):
    """List all employees with filters, search, and pagination"""
    from app.core.query_utils import parse_expand_param, apply_expansion, apply_search, apply_ordering

    # Base query
    query = select(Employe)

    # Apply filters
    if poste_id is not None:
        query = query.where(Employe.poste_id == poste_id)

    if statut_emploi:
        query = query.where(Employe.statut_emploi == statut_emploi)

    # Apply search
    if search:
        search_fields = [
            'prenom', 'nom', 'postnom', 'email_personnel',
            'email_professionnel', 'matricule', 'telephone_personnel'
        ]
        query = apply_search(query, Employe, search_fields, search)

    # Get total count (before expansion to avoid unnecessary joins)
    # Use subquery to get accurate count with all filters applied
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply expansion
    if expand:
        expand_fields = parse_expand_param(expand)
        query = apply_expansion(query, Employe, expand_fields)

    # Apply ordering
    query = apply_ordering(query, Employe, ordering)

    # Apply pagination if requested
    if not no_pagination:
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        employees = result.scalars().all()
        return {
            "results": list(employees),
            "total": total,
            "skip": skip,
            "limit": limit
        }
    else:
        result = await db.execute(query)
        employees = result.scalars().all()
        return {
            "results": list(employees),
            "total": total
        }


@employe_router.post("/", response_model=schemas.EmployeResponse)
async def create_employee(
    employee: schemas.EmployeCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("employe", "create"))
):
    """Create a new employee (basic creation without user account)"""
    try:
        db_employee = await EmployeeService.create_employee(db, employee)
        await db.commit()
        await db.refresh(db_employee)

        # Log the creation
        await AuditService.log_model_change(
            db=db,
            user=current_user,
            instance=db_employee,
            action=AuditAction.CREATE.value,
            request=request
        )

        return db_employee
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        ) from e


@employe_router.post("/with-user", response_model=schemas.EmployeCreateResponse)
async def create_employee_with_user(
    employee: schemas.EmployeCreateWithUser,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("employe", "create"))
):
    """
    Create employee with user account and optional group assignment

    This follows the rhBack logic:
    1. Create employee
    2. Create user account linked to employee
    3. Optionally assign user to a group (if group_id provided)
    4. Send welcome email with credentials

    Required permission: employe.CREATE
    """
    try:
        result = await EmployeeService.create_employee_with_user(
            db,
            employee,
            created_by=current_user,
            background_tasks=background_tasks
        )
        await db.commit()
        return {
            "employee": result["employee"],
            "user": result["user"],
            "group_assigned": result["group_assigned"]
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        ) from e


@employe_router.post(
    "/create-complete",
    response_model=schemas.CompleteEmployeeResponse
)
async def create_complete_employee(
    background_tasks: BackgroundTasks,
    employee: str = Form(...),
    contract: str = Form(...),
    documents_metadata: str = Form(...),
    files: List[UploadFile] = File(default=[]),
    password: Optional[str] = Form(default="12345678"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("employe", "create"))
):
    """
    Create complete employee with contract, documents, user account,
    optional group assignment, and ServiceGroup creation

    This endpoint accepts FormData with:
    - employee: JSON string with employee data
    - contract: JSON string with contract data
    - documents_metadata: JSON string with array of document metadata
    - files: List of uploaded files (optional, matched by index with documents_metadata)
    - password: Optional password (default: "12345678")
    - group_id: Optional group ID

    This endpoint creates:
    1. Employee record
    2. ServiceGroup association (if employee has poste_id and group_id)
    3. Contract
    4. Documents (if provided with files)
    5. User account
    6. Group assignment (if group_id provided)
    7. Send welcome email with credentials

    All operations are performed in a single transaction.
    If any step fails, all changes are rolled back.

    Required permission: employe.CREATE
    """
    from app.core.storage_service import get_storage_service
    storage = get_storage_service()

    try:
        # Parse JSON strings from FormData
        employee_data = schemas.EmployeCreate(**json.loads(employee))
        contract_data = schemas.ContratCreate(**json.loads(contract))
        documents_meta = json.loads(documents_metadata)

        # Prepare documents data with actual files
        documents_data = []

        for idx, doc_meta_dict in enumerate(documents_meta):
            doc_meta = schemas.DocumentMetadata(**doc_meta_dict)

            # Check if there's a corresponding file
            if idx < len(files) and files[idx] and files[idx].filename:
                file = files[idx]

                try:
                    file_content = await file.read()
                    # Persist the uploaded file on the local filesystem
                    public_url = storage.upload_file(
                        file_content=file_content,
                        original_filename=file.filename,
                        folder="documents"
                    )
                    if not public_url:
                        raise HTTPException(
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Erreur lors de l'upload du fichier: {file.filename}"
                        )
                    documents_data.append((doc_meta, public_url))
                except HTTPException:
                    raise
                except Exception as e:
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,detail=f"Erreur lors de l'upload du fichier: {str(e)}")
            else:
                # No file provided for this document metadata
                documents_data.append((doc_meta, None))

        # Create complete employee
        result = await EmployeeService.create_complete_employee(
            db=db,
            employee_data=employee_data,
            contract_data=contract_data,
            documents_data=documents_data,
            password=password,
            created_by=current_user,
            background_tasks=background_tasks
        )
        await db.commit()

        return {
            "success": True,
            "message": "Employé créé avec succès",
            "data": {
                "employee_id": result["employee"].id,
                "user_id": result["user"].id,
                "contract_id": result["contract"].id,
                "documents_count": len(result["documents"]),
                "group_assigned": result["group_assigned"],
            }
        }
    except ValueError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        ) from e
    except json.JSONDecodeError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Format JSON invalide: {str(e)}"
        ) from e
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la création de l'employé: {str(e)}"
        ) from e


@employe_router.get("/{employee_id}", response_model=schemas.EmployeResponse)
async def get_employee(
    employee_id: int,
    expand: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_permission("employe", "read"))
):
    """Get employee by ID with optional relation expansion"""
    employee = await EmployeeService.get_with_relations(
        db, employee_id, expand=expand
    )
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    return employee


@employe_router.put("/{employee_id}", response_model=schemas.EmployeResponse)
async def update_employee(
    employee_id: int,
    employee_update: schemas.EmployeUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("employe", "update"))
):
    """Update employee"""
    from sqlalchemy import select
    result = await db.execute(
        select(Employe).where(Employe.id == employee_id)
    )
    employee = result.scalar_one_or_none()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Capture old values before update
    old_values = AuditService._extract_model_values(employee)

    for key, value in employee_update.model_dump(exclude_unset=True).items():
        setattr(employee, key, value)

    await db.commit()
    await db.refresh(employee)

    # Log the update
    await AuditService.log_model_change(
        db=db,
        user=current_user,
        instance=employee,
        action=AuditAction.UPDATE.value,
        old_values=old_values,
        request=request
    )

    return employee


@employe_router.delete("/{employee_id}")
async def delete_employee(
    employee_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("employe", "delete"))
):
    """Delete employee"""
    from sqlalchemy import select
    result = await db.execute(
        select(Employe).where(Employe.id == employee_id)
    )
    employee = result.scalar_one_or_none()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Capture old values before deletion
    old_values = AuditService._extract_model_values(employee)

    await db.delete(employee)
    await db.commit()

    # Log the deletion
    await AuditService.log_action(
        db=db,
        user=current_user,
        action=AuditAction.DELETE.value,
        resource_type=AuditResourceType.EMPLOYE.value,
        resource_id=str(employee_id),
        old_values=old_values,
        request=request
    )

    return {"message": "Employee deleted successfully"}


@employe_router.get("/export")
async def export_employees(
    format: str = Query("excel", pattern="^(excel|csv|json)$"),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("employe", "read"))
):
    """
    Export employees data

    Supported formats: excel, csv, json
    """
    # Get all employees (in a real implementation, apply filters)
    result = await db.execute(select(Employe))
    employees = result.scalars().all()

    # Log the export
    await AuditService.log_export(
        db=db,
        user=current_user,
        resource_type=AuditResourceType.EMPLOYE.value,
        format_type=format,
        count=len(employees),
        request=request
    )

    # Return placeholder response (actual export implementation would go here)
    return {
        "message": f"Export {format} requested",
        "count": len(employees),
        "format": format
    }


# ************************************************************************
# PERMISSION ROUTES
# ************************************************************************

permission_router = APIRouter(prefix="/permissions", tags=["Permissions"])


@permission_router.get("/")
async def list_permissions(
    skip: int = 0,
    limit: int = 100,
    no_pagination: bool = Query(False),
    expand: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_permission("permission", "read"))
):
    """List all permissions with optional pagination and expansion"""
    from app.core.query_utils import parse_expand_param, apply_expansion

    query = select(Permission).order_by(Permission.resource, Permission.action)

    # Apply expansion
    if expand:
        expand_fields = parse_expand_param(expand)
        query = apply_expansion(query, Permission, expand_fields)

    # Get total count
    count_query = select(func.count()).select_from(Permission)
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination if requested
    if not no_pagination:
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        permissions = result.scalars().all()
        return {
            "results": list(permissions),
            "total": total,
            "skip": skip,
            "limit": limit
        }
    else:
        result = await db.execute(query)
        permissions = result.scalars().all()
        return {
            "results": list(permissions),
            "total": total
        }


@permission_router.get("/{permission_id}", response_model=schemas.PermissionResponse)
async def get_permission(
    permission_id: int,
    expand: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_permission("permission", "read"))
):
    """Get permission by ID with optional expansion"""
    from app.core.query_utils import parse_expand_param, apply_expansion

    query = select(Permission).where(Permission.id == permission_id)

    # Apply expansion
    if expand:
        expand_fields = parse_expand_param(expand)
        query = apply_expansion(query, Permission, expand_fields)

    result = await db.execute(query)
    permission = result.scalar_one_or_none()
    if not permission:
        raise HTTPException(status_code=404, detail="Permission not found")
    return permission


@permission_router.post("/", response_model=schemas.PermissionResponse, status_code=status.HTTP_201_CREATED)
async def create_permission(
    permission: schemas.PermissionCreate,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_permission("permission", "create"))
):
    """Create a new permission"""
    # Check if permission already exists
    result = await db.execute(
        select(Permission).where(
            Permission.resource == permission.resource,
            Permission.action == permission.action
        )
    )
    existing_permission = result.scalar_one_or_none()
    if existing_permission:
        raise HTTPException(
            status_code=400,
            detail=f"Permission for resource '{permission.resource}' with action '{permission.action}' already exists"
        )

    db_permission = Permission(**permission.model_dump())
    db.add(db_permission)
    await db.commit()
    await db.refresh(db_permission)
    return db_permission


# ************************************************************************
# GROUP PERMISSION ROUTES
# ************************************************************************

group_permission_router = APIRouter(
    prefix="/group-permissions",
    tags=["Group Permissions"]
)


@group_permission_router.get("/")
async def list_group_permissions(
    group_id: Optional[int] = Query(None),
    permission_id: Optional[int] = Query(None),
    granted: Optional[bool] = Query(None),
    skip: int = 0,
    limit: int = 100,
    no_pagination: bool = Query(False),
    expand: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_permission("group_permission", "read"))
):
    """List group permissions with filters, pagination, and expansion"""
    from app.core.query_utils import parse_expand_param, apply_expansion

    query = select(GroupPermission)

    # Apply filters
    if group_id is not None:
        query = query.where(GroupPermission.group_id == group_id)
    if permission_id is not None:
        query = query.where(GroupPermission.permission_id == permission_id)
    if granted is not None:
        query = query.where(GroupPermission.granted == granted)

    # Get total count (before expansion to avoid unnecessary joins)
    count_query = select(func.count()).select_from(GroupPermission)
    if group_id is not None:
        count_query = count_query.where(GroupPermission.group_id == group_id)
    if permission_id is not None:
        count_query = count_query.where(GroupPermission.permission_id == permission_id)
    if granted is not None:
        count_query = count_query.where(GroupPermission.granted == granted)
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply expansion
    if expand:
        expand_fields = parse_expand_param(expand)
        query = apply_expansion(query, GroupPermission, expand_fields)

    # Apply pagination if requested
    if not no_pagination:
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        group_permissions = result.scalars().all()
        return {
            "results": list(group_permissions),
            "total": total,
            "skip": skip,
            "limit": limit
        }
    else:
        result = await db.execute(query)
        group_permissions = result.scalars().all()
        return {
            "results": list(group_permissions),
            "total": total
        }


@group_permission_router.get(
    "/{group_permission_id}",
    response_model=schemas.GroupPermissionResponse
)
async def get_group_permission(
    group_permission_id: int,
    expand: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_permission("group_permission", "read"))
):
    """Get group permission by ID with optional expansion"""
    from app.core.query_utils import parse_expand_param, apply_expansion

    query = select(GroupPermission).where(GroupPermission.id == group_permission_id)

    # Apply expansion
    if expand:
        expand_fields = parse_expand_param(expand)
        query = apply_expansion(query, GroupPermission, expand_fields)

    result = await db.execute(query)
    group_permission = result.scalar_one_or_none()
    if not group_permission:
        raise HTTPException(status_code=404, detail="Group permission not found")
    return group_permission


@group_permission_router.post(
    "/",
    response_model=schemas.GroupPermissionResponse,
    status_code=status.HTTP_201_CREATED
)
async def create_group_permission(
    group_permission: schemas.GroupPermissionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("group_permission", "create"))
):
    """Create a group permission assignment"""
    try:
        db_group_permission = await PermissionService.create_group_permission(
            db,
            group_id=group_permission.group_id,
            permission_id=group_permission.permission_id,
            granted=group_permission.granted,
            created_by_id=current_user.id
        )
        await db.commit()
        await db.refresh(db_group_permission)
        return db_group_permission
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        ) from e


@group_permission_router.put(
    "/{group_permission_id}",
    response_model=schemas.GroupPermissionResponse
)
async def update_group_permission(
    group_permission_id: int,
    group_permission_update: schemas.GroupPermissionUpdate,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_permission("group_permission", "update"))
):
    """Update group permission (granted flag)"""
    from sqlalchemy import select
    result = await db.execute(
        select(GroupPermission).where(GroupPermission.id == group_permission_id)
    )
    group_permission = result.scalar_one_or_none()
    if not group_permission:
        raise HTTPException(status_code=404, detail="Group permission not found")

    if group_permission_update.granted is not None:
        group_permission.granted = group_permission_update.granted

    await db.commit()
    await db.refresh(group_permission)
    return group_permission


@group_permission_router.delete("/{group_permission_id}")
async def delete_group_permission(
    group_permission_id: int,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_permission("group_permission", "delete"))
):
    """Delete group permission"""
    from sqlalchemy import select
    result = await db.execute(
        select(GroupPermission).where(GroupPermission.id == group_permission_id)
    )
    group_permission = result.scalar_one_or_none()
    if not group_permission:
        raise HTTPException(status_code=404, detail="Group permission not found")

    await db.delete(group_permission)
    await db.commit()
    return {"message": "Group permission deleted successfully"}


@group_permission_router.get(
    "/users/{user_id}/permissions",
    response_model=schemas.UserPermissionsResponse
)
async def get_user_permissions(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_permission("permission", "read"))
):
    """Get user's effective permissions based on group memberships"""
    from sqlalchemy import select
    # Validate user exists
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Get effective permissions
    permissions_data = await PermissionService.get_effective_permissions(db, user_id)
    return permissions_data


# ************************************************************************
# CONTRAT ROUTES
# ************************************************************************

contrat_router = APIRouter(prefix="/contracts", tags=["Contracts"])


@contrat_router.get("/")
async def list_contracts(
    employe_id: Optional[int] = Query(None),
    is_active: Optional[bool] = Query(None),
    skip: int = 0,
    limit: int = 100,
    no_pagination: bool = Query(False),
    expand: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_permission("contrat", "read"))
):
    """List contracts with optional filters and pagination"""
    from app.core.query_utils import parse_expand_param, apply_expansion

    query = select(Contrat)

    # Apply filters
    if employe_id is not None:
        query = query.where(Contrat.employe_id == employe_id)
    if is_active is not None:
        query = query.where(Contrat.is_active == is_active)

    # Get total count (before expansion to avoid unnecessary joins)
    count_query = select(func.count()).select_from(Contrat)
    if employe_id is not None:
        count_query = count_query.where(Contrat.employe_id == employe_id)
    if is_active is not None:
        count_query = count_query.where(Contrat.is_active == is_active)
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply expansion
    if expand:
        expand_fields = parse_expand_param(expand)
        query = apply_expansion(query, Contrat, expand_fields)

    # Apply pagination if requested
    if not no_pagination:
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        contracts = result.scalars().all()
        return {
            "results": list(contracts),
            "total": total,
            "skip": skip,
            "limit": limit
        }
    else:
        result = await db.execute(query)
        contracts = result.scalars().all()
        return {
            "results": list(contracts),
            "total": total
        }


@contrat_router.post(
    "/",
    response_model=schemas.ContratResponse,
    status_code=status.HTTP_201_CREATED
)
async def create_contract(
    contract: schemas.ContratCreate,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_permission("contrat", "create"))
):
    """Create a new contract"""
    # Validate employee exists
    if contract.employe_id:
        result = await db.execute(
            select(Employe).where(Employe.id == contract.employe_id)
        )
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=404,
                detail=f"Employee with ID {contract.employe_id} not found"
            )

    db_contract = Contrat(**contract.model_dump())
    db.add(db_contract)
    await db.commit()
    await db.refresh(db_contract)
    return db_contract


@contrat_router.get("/{contract_id}", response_model=schemas.ContratResponse)
async def get_contract(
    contract_id: int,
    expand: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_permission("contrat", "read"))
):
    """Get contract by ID with optional expansion"""
    from app.core.query_utils import parse_expand_param, apply_expansion

    query = select(Contrat).where(Contrat.id == contract_id)

    # Apply expansion
    if expand:
        expand_fields = parse_expand_param(expand)
        query = apply_expansion(query, Contrat, expand_fields)

    result = await db.execute(query)
    contract = result.scalar_one_or_none()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    return contract


@contrat_router.put("/{contract_id}", response_model=schemas.ContratResponse)
async def update_contract(
    contract_id: int,
    contract_update: schemas.ContratUpdate,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_permission("contrat", "update"))
):
    """Update contract"""
    result = await db.execute(
        select(Contrat).where(Contrat.id == contract_id)
    )
    contract = result.scalar_one_or_none()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    # Update fields
    update_data = contract_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(contract, key, value)

    await db.commit()
    await db.refresh(contract)
    return contract


@contrat_router.delete("/{contract_id}")
async def delete_contract(
    contract_id: int,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_permission("contrat", "delete"))
):
    """Delete contract"""
    result = await db.execute(
        select(Contrat).where(Contrat.id == contract_id)
    )
    contract = result.scalar_one_or_none()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    await db.delete(contract)
    await db.commit()
    return {"message": "Contract deleted successfully"}


# ************************************************************************
# USER ROUTES
# ************************************************************************

user_router = APIRouter(prefix="/users", tags=["Users"])


@user_router.get("/")
async def list_users(
    skip: int = 0,
    limit: int = 100,
    no_pagination: bool = Query(False),
    expand: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_permission("user", "read"))
):
    """List all users with optional pagination and expansion"""
    from app.core.query_utils import parse_expand_param, apply_expansion

    query = select(User)

    # Apply expansion
    if expand:
        expand_fields = parse_expand_param(expand)
        query = apply_expansion(query, User, expand_fields)

    # Get total count
    count_query = select(func.count(User.id)).select_from(User)
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination if requested
    if not no_pagination:
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        users = result.scalars().all()
        return {
            "results": list(users),
            "total": total,
            "skip": skip,
            "limit": limit
        }
    else:
        result = await db.execute(query)
        users = result.scalars().all()
        return {
            "results": list(users),
            "total": total
        }


@user_router.post("/", response_model=schemas.UserResponse)
async def create_user(
    user: schemas.UserCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("user", "create"))
):
    """Create a new user"""
    # Check if email already exists
    result = await db.execute(
        select(User).where(User.email == user.email)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )

    # Hash password
    hashed_password = get_password_hash(user.password)
    user_data = user.model_dump()
    user_data["password"] = hashed_password

    db_user = User(**user_data)
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)

    # Log the creation
    await AuditService.log_model_change(
        db=db,
        user=current_user,
        instance=db_user,
        action=AuditAction.CREATE.value,
        request=request
    )

    return db_user


@user_router.get("/{user_id}", response_model=schemas.UserResponse)
async def get_user(
    user_id: int,
    expand: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_permission("user", "read"))
):
    """Get user by ID with optional expansion"""
    from app.core.query_utils import parse_expand_param, apply_expansion

    query = select(User).where(User.id == user_id)

    # Apply expansion
    if expand:
        expand_fields = parse_expand_param(expand)
        query = apply_expansion(query, User, expand_fields)

    result = await db.execute(query)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@user_router.put("/{user_id}", response_model=schemas.UserResponse)
async def update_user(
    user_id: int,
    user_update: schemas.UserUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("user", "update"))
):
    """Update user"""
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Capture old values before update
    old_values = AuditService._extract_model_values(user)

    # Update fields
    update_data = user_update.model_dump(exclude_unset=True)

    # Hash password if provided
    if "password" in update_data and update_data["password"]:
        update_data["password"] = get_password_hash(update_data["password"])

    for key, value in update_data.items():
        setattr(user, key, value)

    await db.commit()
    await db.refresh(user)

    # Log the update
    await AuditService.log_model_change(
        db=db,
        user=current_user,
        instance=user,
        action=AuditAction.UPDATE.value,
        old_values=old_values,
        request=request
    )

    return user


@user_router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("user", "delete"))
):
    """Delete user"""
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Capture old values before deletion
    old_values = AuditService._extract_model_values(user)

    await db.delete(user)
    await db.commit()

    # Log the deletion
    await AuditService.log_action(
        db=db,
        user=current_user,
        action=AuditAction.DELETE.value,
        resource_type=AuditResourceType.USER.value,
        resource_id=str(user_id),
        old_values=old_values,
        request=request
    )

    return {"message": "User deleted successfully"}


# ************************************************************************
# DOCUMENT ROUTES
# ************************************************************************

document_router = APIRouter(prefix="/documents", tags=["Documents"])


@document_router.get("/")
async def list_documents(
    employe_id: Optional[int] = Query(None),
    type_document: Optional[str] = Query(None),
    skip: int = 0,
    limit: int = 100,
    no_pagination: bool = Query(False),
    expand: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_permission("document", "read"))
):
    """List documents with optional filters and pagination"""
    from app.core.query_utils import parse_expand_param, apply_expansion

    query = select(Document)

    # Apply filters
    if employe_id is not None:
        query = query.where(Document.employe_id == employe_id)
    if type_document is not None:
        query = query.where(Document.type_document == type_document)

    # Get total count (before expansion to avoid unnecessary joins)
    count_query = select(func.count()).select_from(Document)
    if employe_id is not None:
        count_query = count_query.where(Document.employe_id == employe_id)
    if type_document is not None:
        count_query = count_query.where(Document.type_document == type_document)
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply expansion
    if expand:
        expand_fields = parse_expand_param(expand)
        query = apply_expansion(query, Document, expand_fields)

    # Apply pagination if requested
    if not no_pagination:
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        documents = result.scalars().all()
        return {
            "results": list(documents),
            "total": total,
            "skip": skip,
            "limit": limit
        }
    else:
        result = await db.execute(query)
        documents = result.scalars().all()
        return {
            "results": list(documents),
            "total": total
        }


@document_router.post(
    "/",
    response_model=schemas.DocumentResponse,
    status_code=status.HTTP_201_CREATED
)
async def create_document(
    document: schemas.DocumentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("document", "create"))
):
    """Create a new document"""
    # Validate employee exists
    result = await db.execute(
        select(Employe).where(Employe.id == document.employe_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=404,
            detail=f"Employee with ID {document.employe_id} not found"
        )

    db_document = Document(**document.model_dump())
    db.add(db_document)
    await db.commit()
    await db.refresh(db_document)
    return db_document


@document_router.get("/{document_id}", response_model=schemas.DocumentResponse)
async def get_document(
    document_id: int,
    expand: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_permission("document", "read"))
):
    """Get document by ID with optional expansion"""
    from app.core.query_utils import parse_expand_param, apply_expansion

    query = select(Document).where(Document.id == document_id)

    # Apply expansion
    if expand:
        expand_fields = parse_expand_param(expand)
        query = apply_expansion(query, Document, expand_fields)

    result = await db.execute(query)
    document = result.scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@document_router.put("/{document_id}", response_model=schemas.DocumentResponse)
async def update_document(
    document_id: int,
    document_update: schemas.DocumentUpdate,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_permission("document", "update"))
):
    """Update document"""
    result = await db.execute(
        select(Document).where(Document.id == document_id)
    )
    document = result.scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Update fields
    update_data = document_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(document, key, value)

    await db.commit()
    await db.refresh(document)
    return document


@document_router.delete("/{document_id}")
async def delete_document(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_permission("document", "delete"))
):
    """Delete document"""
    result = await db.execute(
        select(Document).where(Document.id == document_id)
    )
    document = result.scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    await db.delete(document)
    await db.commit()
    return {"message": "Document deleted successfully"}


# ************************************************************************
# USER GROUP ROUTES
# ************************************************************************

user_group_router = APIRouter(prefix="/user-groups", tags=["User Groups"])


@user_group_router.get("/")
async def list_user_groups(
    user_id: Optional[int] = Query(None),
    group_id: Optional[int] = Query(None),
    is_active: Optional[bool] = Query(None),
    skip: int = 0,
    limit: int = 100,
    no_pagination: bool = Query(False),
    expand: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_permission("user_group", "read"))
):
    """List user groups with optional filters and pagination"""
    from app.core.query_utils import parse_expand_param, apply_expansion

    query = select(UserGroup)

    # Apply filters
    if user_id is not None:
        query = query.where(UserGroup.user_id == user_id)
    if group_id is not None:
        query = query.where(UserGroup.group_id == group_id)
    if is_active is not None:
        query = query.where(UserGroup.is_active == is_active)

    # Get total count (before expansion to avoid unnecessary joins)
    count_query = select(func.count()).select_from(UserGroup)
    if user_id is not None:
        count_query = count_query.where(UserGroup.user_id == user_id)
    if group_id is not None:
        count_query = count_query.where(UserGroup.group_id == group_id)
    if is_active is not None:
        count_query = count_query.where(UserGroup.is_active == is_active)
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply expansion
    if expand:
        expand_fields = parse_expand_param(expand)
        query = apply_expansion(query, UserGroup, expand_fields)

    # Apply pagination if requested
    if not no_pagination:
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        user_groups = result.scalars().all()
        return {
            "results": list(user_groups),
            "total": total,
            "skip": skip,
            "limit": limit
        }
    else:
        result = await db.execute(query)
        user_groups = result.scalars().all()
        return {
            "results": list(user_groups),
            "total": total
        }


@user_group_router.post(
    "/",
    response_model=schemas.UserGroupResponse,
    status_code=status.HTTP_201_CREATED
)
async def create_user_group(
    user_group: schemas.UserGroupCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("user_group", "create"))
):
    """Create a user group assignment"""
    # Validate user exists
    result = await db.execute(
        select(User).where(User.id == user_group.user_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=404,
            detail=f"User with ID {user_group.user_id} not found"
        )

    # Validate group exists
    result = await db.execute(
        select(Group).where(Group.id == user_group.group_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=404,
            detail=f"Group with ID {user_group.group_id} not found"
        )

    # Check for duplicate
    result = await db.execute(
        select(UserGroup).where(
            UserGroup.user_id == user_group.user_id,
            UserGroup.group_id == user_group.group_id
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="User group assignment already exists"
        )

    # Create user group
    user_group_data = user_group.model_dump()
    if not user_group_data.get('assigned_by_id'):
        user_group_data['assigned_by_id'] = current_user.id

    db_user_group = UserGroup(**user_group_data)
    db.add(db_user_group)
    await db.commit()
    await db.refresh(db_user_group)
    return db_user_group


@user_group_router.get(
    "/{user_group_id}",
    response_model=schemas.UserGroupResponse
)
async def get_user_group(
    user_group_id: int,
    expand: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_permission("user_group", "read"))
):
    """Get user group by ID with optional expansion"""
    from app.core.query_utils import parse_expand_param, apply_expansion

    query = select(UserGroup).where(UserGroup.id == user_group_id)

    # Apply expansion
    if expand:
        expand_fields = parse_expand_param(expand)
        query = apply_expansion(query, UserGroup, expand_fields)

    result = await db.execute(query)
    user_group = result.scalar_one_or_none()
    if not user_group:
        raise HTTPException(status_code=404, detail="User group not found")
    return user_group


@user_group_router.put(
    "/{user_group_id}",
    response_model=schemas.UserGroupResponse
)
async def update_user_group(
    user_group_id: int,
    user_group_update: schemas.UserGroupUpdate,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_permission("user_group", "update"))
):
    """Update user group (is_active status)"""
    result = await db.execute(
        select(UserGroup).where(UserGroup.id == user_group_id)
    )
    user_group = result.scalar_one_or_none()
    if not user_group:
        raise HTTPException(status_code=404, detail="User group not found")

    # Update fields
    if user_group_update.is_active is not None:
        user_group.is_active = user_group_update.is_active

    await db.commit()
    await db.refresh(user_group)
    return user_group


@user_group_router.delete("/{user_group_id}")
async def delete_user_group(
    user_group_id: int,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_permission("user_group", "delete"))
):
    """Delete user group"""
    result = await db.execute(
        select(UserGroup).where(UserGroup.id == user_group_id)
    )
    user_group = result.scalar_one_or_none()
    if not user_group:
        raise HTTPException(status_code=404, detail="User group not found")

    await db.delete(user_group)
    await db.commit()
    return {"message": "User group deleted successfully"}


# ************************************************************************
# BULK OPERATIONS - USER GROUPS
# ************************************************************************

@user_group_router.post(
    "/bulk-assign/",
    response_model=schemas.BulkOperationResponse,
    status_code=status.HTTP_201_CREATED
)
async def bulk_assign_users_to_groups(
    data: schemas.BulkUserGroupAssign,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("user_group", "update"))
):
    """
    Bulk assign users to groups

    This endpoint allows assigning multiple users to multiple groups in a single operation.

    Parameters:
    - user_ids: List of user IDs to assign
    - group_ids: List of group IDs to assign users to
    - is_active: Whether the assignments should be active (default: True)
    - replace_existing: If True, removes existing group assignments for these users first

    Returns:
    - BulkOperationResponse with counts of created, updated, and failed operations
    """
    created_count = 0
    updated_count = 0
    failed_count = 0
    errors = []

    try:
        # Validate all users exist
        for user_id in data.user_ids:
            result = await db.execute(select(User).where(User.id == user_id))
            if not result.scalar_one_or_none():
                errors.append(f"User with ID {user_id} not found")
                failed_count += 1

        # Validate all groups exist
        for group_id in data.group_ids:
            result = await db.execute(select(Group).where(Group.id == group_id))
            if not result.scalar_one_or_none():
                errors.append(f"Group with ID {group_id} not found")
                failed_count += 1

        # If there are validation errors, return early
        if errors:
            return schemas.BulkOperationResponse(
                success=False,
                message="Validation failed",
                created_count=0,
                updated_count=0,
                failed_count=failed_count,
                errors=errors
            )

        # If replace_existing is True, remove existing assignments for these users
        if data.replace_existing:
            for user_id in data.user_ids:
                result = await db.execute(
                    select(UserGroup).where(UserGroup.user_id == user_id)
                )
                existing_assignments = result.scalars().all()
                for assignment in existing_assignments:
                    await db.delete(assignment)

        # Create assignments for each user-group combination
        for user_id in data.user_ids:
            for group_id in data.group_ids:
                try:
                    # Check if assignment already exists
                    result = await db.execute(
                        select(UserGroup).where(
                            UserGroup.user_id == user_id,
                            UserGroup.group_id == group_id
                        )
                    )
                    existing = result.scalar_one_or_none()

                    if existing:
                        # Update existing assignment
                        existing.is_active = data.is_active
                        updated_count += 1
                    else:
                        # Create new assignment
                        user_group = UserGroup(
                            user_id=user_id,
                            group_id=group_id,
                            is_active=data.is_active,
                            assigned_by_id=current_user.id
                        )
                        db.add(user_group)
                        created_count += 1

                except Exception as e:
                    errors.append(f"Failed to assign user {user_id} to group {group_id}: {str(e)}")
                    failed_count += 1

        await db.commit()

        return schemas.BulkOperationResponse(
            success=True,
            message=f"Successfully processed {created_count + updated_count} assignments",
            created_count=created_count,
            updated_count=updated_count,
            failed_count=failed_count,
            errors=errors
        )

    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Bulk assignment failed: {str(e)}"
        ) from e


@user_group_router.post(
    "/bulk-remove/",
    response_model=schemas.BulkOperationResponse
)
async def bulk_remove_users_from_groups(
    data: schemas.BulkUserGroupRemove,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_permission("user_group", "update"))
):
    """
    Bulk remove users from groups

    This endpoint allows removing multiple users from multiple groups in a single operation.

    Parameters:
    - user_ids: List of user IDs
    - group_ids: List of group IDs to remove users from

    Returns:
    - BulkOperationResponse with count of deleted assignments
    """
    deleted_count = 0
    failed_count = 0
    errors = []

    try:
        # Remove assignments for each user-group combination
        for user_id in data.user_ids:
            for group_id in data.group_ids:
                try:
                    result = await db.execute(
                        select(UserGroup).where(
                            UserGroup.user_id == user_id,
                            UserGroup.group_id == group_id
                        )
                    )
                    user_group = result.scalar_one_or_none()

                    if user_group:
                        await db.delete(user_group)
                        deleted_count += 1
                    else:
                        errors.append(
                            f"Assignment not found for user {user_id} and group {group_id}"
                        )
                        failed_count += 1

                except Exception as e:
                    errors.append(
                        f"Failed to remove user {user_id} from group {group_id}: {str(e)}"
                    )
                    failed_count += 1

        await db.commit()

        return schemas.BulkOperationResponse(
            success=True,
            message=f"Successfully removed {deleted_count} assignments",
            deleted_count=deleted_count,
            failed_count=failed_count,
            errors=errors
        )

    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Bulk removal failed: {str(e)}"
        ) from e


# ************************************************************************
# BULK OPERATIONS - GROUP PERMISSIONS
# ************************************************************************

@group_permission_router.post(
    "/bulk-update/{group_id}/",
    response_model=schemas.BulkOperationResponse
)
async def bulk_update_group_permissions(
    group_id: int,
    data: schemas.BulkGroupPermissionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("group_permission", "update"))
):
    """
    Bulk update group permissions

    This endpoint allows updating multiple permissions for a group in a single operation.

    Parameters:
    - group_id: The group ID to update permissions for
    - permissions: List of permission updates with permission_id and granted status
      Example: [{"permission_id": 1, "granted": true}, {"permission_id": 2, "granted": false}]

    Returns:
    - BulkOperationResponse with counts of created, updated, and failed operations
    """
    created_count = 0
    updated_count = 0
    failed_count = 0
    errors = []

    try:
        # Validate group exists
        result = await db.execute(select(Group).where(Group.id == group_id))
        group = result.scalar_one_or_none()
        if not group:
            raise HTTPException(
                status_code=404,
                detail=f"Group with ID {group_id} not found"
            )

        # Process each permission update
        for perm_data in data.permissions:
            try:
                permission_id = perm_data.get("permission_id")
                granted = perm_data.get("granted", True)

                if not permission_id:
                    errors.append("Missing permission_id in permission data")
                    failed_count += 1
                    continue

                # Validate permission exists
                result = await db.execute(
                    select(Permission).where(Permission.id == permission_id)
                )
                permission = result.scalar_one_or_none()
                if not permission:
                    errors.append(f"Permission with ID {permission_id} not found")
                    failed_count += 1
                    continue

                # Check if group permission already exists
                result = await db.execute(
                    select(GroupPermission).where(
                        GroupPermission.group_id == group_id,
                        GroupPermission.permission_id == permission_id
                    )
                )
                existing = result.scalar_one_or_none()

                if existing:
                    # Update existing permission
                    existing.granted = granted
                    updated_count += 1
                else:
                    # Create new group permission
                    group_permission = GroupPermission(
                        group_id=group_id,
                        permission_id=permission_id,
                        granted=granted,
                        created_by_id=current_user.id
                    )
                    db.add(group_permission)
                    created_count += 1

            except Exception as e:
                errors.append(
                    f"Failed to update permission {perm_data.get('permission_id')}: {str(e)}"
                )
                failed_count += 1

        await db.commit()

        return schemas.BulkOperationResponse(
            success=True,
            message=f"Successfully processed {created_count + updated_count} permissions",
            created_count=created_count,
            updated_count=updated_count,
            failed_count=failed_count,
            errors=errors
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Bulk permission update failed: {str(e)}"
        ) from e


# Include all routers
def get_user_app_router():
    """Get combined router for user_app"""
    main_router = APIRouter()
    main_router.include_router(auth_router)
    main_router.include_router(service_router)
    main_router.include_router(service_group_router)
    main_router.include_router(poste_router)
    main_router.include_router(group_router)
    main_router.include_router(employe_router)
    main_router.include_router(permission_router)
    main_router.include_router(group_permission_router)
    main_router.include_router(user_router)
    main_router.include_router(user_group_router)
    main_router.include_router(contrat_router)
    main_router.include_router(document_router)
    return main_router



# ************************************************************************
# POSTE ROUTES (Wrapper around Group + ServiceGroup)
# ************************************************************************

poste_router = APIRouter(prefix="/postes", tags=["Postes"])


@poste_router.get("/")
async def list_postes(
    service_id: Optional[int] = Query(None),
    skip: int = 0,
    limit: int = 100,
    no_pagination: bool = Query(False),
    expand: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_permission("poste", "read"))
):
    """
    List all postes (ServiceGroups with their associated Groups)

    A poste is a position/role that combines:
    - A Group (for RBAC)
    - A ServiceGroup (linking the group to a service)
    """
    from app.core.query_utils import parse_expand_param, apply_expansion
    from app.user_app.models import ServiceGroup

    query = select(ServiceGroup)

    # Apply filters
    if service_id is not None:
        query = query.where(ServiceGroup.service_id == service_id)

    # Get total count
    count_query = select(func.count()).select_from(ServiceGroup)
    if service_id is not None:
        count_query = count_query.where(ServiceGroup.service_id == service_id)
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply expansion (always expand group and service for poste view)
    expand_fields = ['group', 'service']
    if expand:
        expand_fields.extend(parse_expand_param(expand))
    query = apply_expansion(query, ServiceGroup, expand_fields)

    # Apply pagination if requested
    if not no_pagination:
        query = query.offset(skip).limit(limit)

    result = await db.execute(query)
    service_groups = result.scalars().all()

    # Transform to Poste format
    postes = []
    for sg in service_groups:
        poste_data = {
            "id": sg.id,
            "code": sg.group.code if sg.group else "",
            "titre": sg.group.name if sg.group else "",
            "description": sg.group.description if sg.group else None,
            "service_id": sg.service_id,
            "group_id": sg.group_id,
            "service": sg.service,
            "created_at": sg.created_at,
            "updated_at": sg.updated_at
        }
        postes.append(poste_data)

    if not no_pagination:
        return {
            "results": postes,
            "total": total,
            "skip": skip,
            "limit": limit
        }
    else:
        return {
            "results": postes,
            "total": total
        }


@poste_router.post("/", response_model=schemas.PosteResponse, status_code=status.HTTP_201_CREATED)
async def create_poste(
    poste: schemas.PosteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("poste", "create"))
):
    """
    Create a new poste (creates Group + ServiceGroup)

    This endpoint:
    1. Creates a Group with the provided code, titre (name), and description
    2. Creates a ServiceGroup linking the new group to the specified service
    3. Returns the combined poste information
    """
    try:
        # Validate service exists
        result = await db.execute(
            select(Service).where(Service.id == poste.service_id)
        )
        service = result.scalar_one_or_none()
        if not service:
            raise HTTPException(
                status_code=404,
                detail=f"Service with ID {poste.service_id} not found"
            )

        # Check if group with same code already exists
        result = await db.execute(
            select(Group).where(func.upper(Group.code) == poste.code.upper())
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail=f"A group with code '{poste.code}' already exists"
            )

        # Create the group
        group = Group(
            code=poste.code,
            name=poste.titre,
            description=poste.description,
            is_active=True
        )
        db.add(group)
        await db.flush()
        await db.refresh(group)

        # Create the service group association
        service_group = ServiceGroup(
            service_id=poste.service_id,
            group_id=group.id
        )
        db.add(service_group)
        await db.flush()
        await db.refresh(service_group)

        # Load relationships for response
        await db.refresh(service_group, ['service', 'group'])

        await db.commit()

        # Return poste format
        return schemas.PosteResponse(
            id=service_group.id,
            code=group.code,
            titre=group.name,
            description=group.description,
            service_id=service_group.service_id,
            group_id=group.id,
            service=service,
            created_at=service_group.created_at,
            updated_at=service_group.updated_at
        )

    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create poste: {str(e)}"
        ) from e


@poste_router.get("/{poste_id}", response_model=schemas.PosteResponse)
async def get_poste(
    poste_id: int,
    expand: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_permission("poste", "read"))
):
    """Get poste by ID (ServiceGroup ID)"""
    from app.core.query_utils import parse_expand_param, apply_expansion
    from app.user_app.models import ServiceGroup

    query = select(ServiceGroup).where(ServiceGroup.id == poste_id)

    # Always expand group and service
    expand_fields = ['group', 'service']
    if expand:
        expand_fields.extend(parse_expand_param(expand))
    query = apply_expansion(query, ServiceGroup, expand_fields)

    result = await db.execute(query)
    service_group = result.scalar_one_or_none()

    if not service_group:
        raise HTTPException(status_code=404, detail="Poste not found")

    # Return poste format
    return schemas.PosteResponse(
        id=service_group.id,
        code=service_group.group.code if service_group.group else "",
        titre=service_group.group.name if service_group.group else "",
        description=service_group.group.description if service_group.group else None,
        service_id=service_group.service_id,
        group_id=service_group.group_id,
        service=service_group.service,
        created_at=service_group.created_at,
        updated_at=service_group.updated_at
    )


@poste_router.put("/{poste_id}", response_model=schemas.PosteResponse)
async def update_poste(
    poste_id: int,
    poste_update: schemas.PosteUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("poste", "update"))
):
    """
    Update poste (updates Group and optionally ServiceGroup)

    This endpoint:
    1. Updates the associated Group's code, name (titre), and description
    2. If service_id is provided, updates the ServiceGroup's service_id
    """
    from app.user_app.models import ServiceGroup

    try:
        # Get the service group
        result = await db.execute(
            select(ServiceGroup)
            .options(selectinload(ServiceGroup.group), selectinload(ServiceGroup.service))
            .where(ServiceGroup.id == poste_id)
        )
        service_group = result.scalar_one_or_none()

        if not service_group:
            raise HTTPException(status_code=404, detail="Poste not found")

        # Update the group
        group = service_group.group
        if not group:
            raise HTTPException(status_code=404, detail="Associated group not found")

        update_data = poste_update.model_dump(exclude_unset=True)

        # Update group fields
        if 'code' in update_data:
            # Check if new code conflicts with existing groups
            result = await db.execute(
                select(Group).where(
                    func.upper(Group.code) == update_data['code'].upper(),
                    Group.id != group.id
                )
            )
            if result.scalar_one_or_none():
                raise HTTPException(
                    status_code=400,
                    detail=f"A group with code '{update_data['code']}' already exists"
                )
            group.code = update_data['code']

        if 'titre' in update_data:
            group.name = update_data['titre']

        if 'description' in update_data:
            group.description = update_data['description']

        # Update service_id if provided
        if 'service_id' in update_data:
            # Validate new service exists
            result = await db.execute(
                select(Service).where(Service.id == update_data['service_id'])
            )
            if not result.scalar_one_or_none():
                raise HTTPException(
                    status_code=404,
                    detail=f"Service with ID {update_data['service_id']} not found"
                )
            service_group.service_id = update_data['service_id']

        await db.commit()
        await db.refresh(service_group)
        await db.refresh(group)

        # Reload relationships
        await db.refresh(service_group, ['service', 'group'])

        # Return poste format
        return schemas.PosteResponse(
            id=service_group.id,
            code=group.code,
            titre=group.name,
            description=group.description,
            service_id=service_group.service_id,
            group_id=group.id,
            service=service_group.service,
            created_at=service_group.created_at,
            updated_at=service_group.updated_at
        )

    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update poste: {str(e)}"
        ) from e


@poste_router.delete("/{poste_id}")
async def delete_poste(
    poste_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("poste", "delete"))
):
    """
    Delete poste (deletes ServiceGroup and associated Group)

    This endpoint:
    1. Deletes the ServiceGroup
    2. Deletes the associated Group (if no other ServiceGroups reference it)

    Note: The Group deletion will cascade to delete UserGroups and GroupPermissions
    """
    from app.user_app.models import ServiceGroup

    try:
        # Get the service group with its group
        result = await db.execute(
            select(ServiceGroup)
            .options(selectinload(ServiceGroup.group))
            .where(ServiceGroup.id == poste_id)
        )
        service_group = result.scalar_one_or_none()

        if not service_group:
            raise HTTPException(status_code=404, detail="Poste not found")

        group = service_group.group
        group_id = service_group.group_id

        # Delete the service group first
        await db.delete(service_group)
        await db.flush()

        # Check if the group is still referenced by other service groups
        result = await db.execute(
            select(func.count(ServiceGroup.id))
            .where(ServiceGroup.group_id == group_id)
        )
        other_service_groups_count = result.scalar() or 0

        # If no other service groups reference this group, delete it
        if other_service_groups_count == 0 and group:
            # Check if group has active users
            result = await db.execute(
                select(func.count(UserGroup.id))
                .where(
                    UserGroup.group_id == group_id,
                    UserGroup.is_active.is_(True)
                )
            )
            active_users_count = result.scalar() or 0

            if active_users_count > 0:
                await db.rollback()
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot delete poste. The associated group has {active_users_count} active user(s)"
                )

            # Delete the group (will cascade to UserGroups and GroupPermissions)
            await db.delete(group)

        await db.commit()

        return {
            "message": "Poste deleted successfully",
            "group_deleted": other_service_groups_count == 0
        }

    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete poste: {str(e)}"
        ) from e


