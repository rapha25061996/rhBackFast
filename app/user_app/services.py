"""Business logic services for user_app"""
from typing import Optional, Dict, Any, List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from fastapi import BackgroundTasks

from app.user_app.models import (
    Employe, User, Group, UserGroup, ServiceGroup, Service, Contrat, Document,
    Permission, GroupPermission
)
from app.user_app.schemas import (
    EmployeCreate, EmployeCreateWithUser, UserCreate, EmployeFilter,
    ContratCreate, DocumentMetadata
)
from app.core.security import get_password_hash
from app.core.query_utils import (
    apply_search, apply_ordering, apply_expansion, parse_expand_param
)
from app.user_app.email_service import UserEmailService



class EmployeeService:
    """Service for managing employee operations"""

    @staticmethod
    async def list_with_filters(
        db: AsyncSession,
        filters: EmployeFilter
    ) -> Tuple[List[Employe], int]:
        """
        List employees with filters, search, and pagination

        Args:
            db: Database session
            filters: Filter parameters

        Returns:
            Tuple of (employees list, total count)
        """
        # Base query
        query = select(Employe)

        # Apply filters
        if filters.poste_id:
            query = query.where(Employe.poste_id == filters.poste_id)

        if filters.statut_emploi:
            query = query.where(Employe.statut_emploi == filters.statut_emploi)

        # Apply search
        if filters.search:
            search_fields = [
                'prenom', 'nom', 'postnom', 'email_personnel',
                'email_professionnel', 'matricule', 'telephone_personnel'
            ]
            query = apply_search(query, Employe, search_fields, filters.search)

        # Apply expansion
        if filters.expand:
            expand_fields = parse_expand_param(filters.expand)
            query = apply_expansion(query, Employe, expand_fields)

        # Get total count before pagination
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # Apply ordering
        query = apply_ordering(query, Employe, filters.ordering)

        # Apply pagination
        query = query.offset(filters.skip).limit(filters.limit)

        # Execute query
        result = await db.execute(query)
        employees = result.scalars().all()

        return list(employees), total

    @staticmethod
    async def get_with_relations(
        db: AsyncSession,
        employee_id: int,
        expand: Optional[str] = None
    ) -> Optional[Employe]:
        """
        Get employee by ID with optional relation expansion

        Args:
            db: Database session
            employee_id: Employee ID
            expand: Comma-separated list of relations to expand

        Returns:
            Employee instance or None
        """
        query = select(Employe).where(Employe.id == employee_id)

        # Apply expansion if requested
        if expand:
            expand_fields = parse_expand_param(expand)
            query = apply_expansion(query, Employe, expand_fields)

        result = await db.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def create_employee(
        db: AsyncSession,
        employee_data: EmployeCreate
    ) -> Employe:
        """
        Create a new employee

        Args:
            db: Database session
            employee_data: Employee creation data

        Returns:
            Created employee instance



        Raises:
            ValueError: If validation fails
        """

        # if employee_data.poste_id:
        #     result = await db.execute(
        #         select(ServiceGroup).where(ServiceGroup.id == employee_data.poste_id)
        #     )
        #     poste = result.scalar_one_or_none()
        #     if not poste:
        #         raise ValueError(
        #             f"ServiceGroup avec l'ID {employee_data.poste_id} introuvable"
        #         )

        # Validate responsable_id if provided
        if employee_data.responsable_id:
            result = await db.execute(
                select(Employe).where(Employe.id == employee_data.responsable_id)
            )
            responsable = result.scalar_one_or_none()
            if not responsable:
                raise ValueError(
                    f"Responsable avec l'ID {employee_data.responsable_id} introuvable"
                )

        # Create employee
        employee = Employe(**employee_data.model_dump())
        db.add(employee)

        try:
            await db.flush()
            await db.refresh(employee)
            return employee
        except IntegrityError as e:
            await db.rollback()
            raise ValueError(f"Erreur lors de la création de l'employé: {str(e)}") from e

    @staticmethod
    async def create_employee_with_user(
        db: AsyncSession,
        employee_data: EmployeCreateWithUser,
        created_by: Optional[User] = None,
        background_tasks: Optional[BackgroundTasks] = None
    ) -> Dict[str, Any]:
        """
        Create employee with user account and optional group assignment

        This follows the rhBack logic:
        1. Create employee
        2. Create user account linked to employee
        3. Optionally assign user to a group
        4. Send welcome email with credentials

        Args:
            db: Database session
            employee_data: Employee creation data with user info
            created_by: User creating the employee (for audit)
            background_tasks: FastAPI background tasks for email sending

        Returns:
            Dictionary with employee, user, and group_assigned status

        Raises:
            ValueError: If validation fails
        """
        try:
            # Validate email_professionnel uniqueness BEFORE any insertion
            if employee_data.email_professionnel:
                result = await db.execute(
                    select(Employe).where(
                        Employe.email_professionnel == employee_data.email_professionnel
                    )
                )
                existing_employee = result.scalar_one_or_none()
                if existing_employee:
                    raise ValueError("L'email professionnel est déjà utilisé")

            # Validate user email uniqueness BEFORE any insertion
            user_email = (
                employee_data.email_professionnel or employee_data.email_personnel
            )
            result = await db.execute(
                select(User).where(User.email == user_email)
            )
            existing_user = result.scalar_one_or_none()
            if existing_user:
                raise ValueError(
                    f"Un compte utilisateur avec l'email {user_email} existe déjà"
                )

            # Validate poste (ServiceGroup) if provided
            poste_instance = None
            if employee_data.poste_id:
                result = await db.execute(
                    select(ServiceGroup).where(
                        ServiceGroup.id == employee_data.poste_id
                    )
                )
                poste_instance = result.scalar_one_or_none()
                if not poste_instance:
                    raise ValueError(
                        f"Poste avec l'ID {employee_data.poste_id} introuvable"
                    )

            # Create employee (without password)
            employee_dict = employee_data.model_dump(
                exclude={"password"}
            )
            employee = await EmployeeService.create_employee(
                db,
                EmployeCreate(**employee_dict)
            )

            # Create user account
            password = employee_data.password or "12345678"

            user = User(
                email=user_email,
                nom=employee_data.nom,
                prenom=employee_data.prenom,
                password=get_password_hash(password),
                employe_id=employee.id,
                is_active=True,
                is_staff=False,
                is_superuser=False
            )
            db.add(user)
            await db.flush()
            await db.refresh(user)

            # Assign user to group if poste is provided
            group_assigned = False
            if poste_instance and user:
                user_group = UserGroup(
                    user_id=user.id,
                    group_id=poste_instance.group_id,
                    assigned_by_id=created_by.id if created_by else None,
                    is_active=True
                )
                db.add(user_group)
                await db.flush()
                group_assigned = True

            # Refresh objects before returning
            await db.refresh(employee)
            await db.refresh(user)

            # Send welcome email in background
            if background_tasks:
                user_full_name = f"{employee_data.prenom} {employee_data.nom}"
                email_service = UserEmailService()
                background_tasks.add_task(
                    email_service.send_welcome_email,
                    user_email,
                    user_full_name,
                    password
                )

            return {
                "employee": employee,
                "user": user,
                "group_assigned": group_assigned
            }

        except IntegrityError as e:
            await db.rollback()
            raise ValueError(f"Erreur d'intégrité des données: {str(e)}") from e
        except ValueError:
            await db.rollback()
            raise
        except Exception as e:
            await db.rollback()
            raise ValueError(f"Erreur lors de la création de l'employé: {str(e)}") from e


    @staticmethod
    async def create_complete_employee(
        db: AsyncSession,
        employee_data: EmployeCreate,
        contract_data: ContratCreate,
        documents_data: List[Tuple[DocumentMetadata, Any]],
        password: str = "12345678",
        created_by: Optional[User] = None,
        background_tasks: Optional[BackgroundTasks] = None
    ) -> Dict[str, Any]:
        """
        Create complete employee with contract, documents, user account,
        optional group assignment, and ServiceGroup creation

        Args:
            db: Database session
            employee_data: Employee creation data
            contract_data: Contract creation data
            documents_data: List of (metadata, file) tuples
            password: User password
            created_by: User creating the employee
            background_tasks: FastAPI background tasks for email sending

        Returns:
            Dictionary with employee, contract, documents, user, group_assigned

        Raises:
            ValueError: If validation fails
        """
        try:
            # Validate email_professionnel uniqueness BEFORE any insertion
            if employee_data.email_professionnel:
                result = await db.execute(
                    select(Employe).where(
                        Employe.email_professionnel == employee_data.email_professionnel
                    )
                )
                existing_employee = result.scalar_one_or_none()
                if existing_employee:
                    raise ValueError("L'email professionnel est déjà utilisé")

            # Validate user email uniqueness BEFORE any insertion
            user_email = (
                employee_data.email_professionnel or employee_data.email_personnel
            )
            result = await db.execute(
                select(User).where(User.email == user_email)
            )
            existing_user = result.scalar_one_or_none()
            if existing_user:
                raise ValueError(
                    f"Un compte utilisateur avec l'email {user_email} existe déjà"
                )

            # 1. Validate poste if provided
            poste_instance = None
            if employee_data.poste_id:
                result = await db.execute(
                    select(ServiceGroup).where(
                        ServiceGroup.id == employee_data.poste_id
                    )
                )
                poste_instance = result.scalar_one_or_none()
                if not poste_instance:
                    raise ValueError(
                        f"Poste avec l'ID {employee_data.poste_id} introuvable"
                    )

            # 2. Create employee
            employee = await EmployeeService.create_employee(db, employee_data)

            # 3. Create contract
            contract_dict = contract_data.model_dump()
            contract_dict['employe_id'] = employee.id
            contract = Contrat(**contract_dict)
            db.add(contract)
            await db.flush()
            await db.refresh(contract)

            # 4. Create documents
            created_documents = []
            for doc_metadata, doc_file in documents_data:
                document = Document(
                    employe_id=employee.id,
                    type_document=doc_metadata.type_document,
                    titre=doc_metadata.titre,
                    description=doc_metadata.description or '',
                    fichier=doc_file,
                    expiry_date=doc_metadata.expiry_date,
                    uploaded_by=created_by.email if created_by else 'System'
                )
                db.add(document)
                await db.flush()
                await db.refresh(document)
                created_documents.append(document)

            # 5. Create user account
            user = User(
                email=user_email,
                nom=employee_data.nom,
                prenom=employee_data.prenom,
                password=get_password_hash(password),
                employe_id=employee.id,
                is_active=True,
                is_staff=False,
                is_superuser=False
            )
            db.add(user)
            await db.flush()
            await db.refresh(user)

            # 6. Assign user to group if provided
            group_assigned = False
            if poste_instance and user:
                user_group = UserGroup(
                    user_id=user.id,
                    group_id=poste_instance.group_id,
                    assigned_by_id=created_by.id if created_by else None,
                    is_active=True
                )
                db.add(user_group)
                await db.flush()
                group_assigned = True

            # 7. Send welcome email in background
            if background_tasks:
                user_full_name = f"{employee_data.prenom} {employee_data.nom}"
                email_service = UserEmailService()
                background_tasks.add_task(
                    email_service.send_welcome_email,
                    user_email,
                    user_full_name,
                    password
                )

            return {
                "employee": employee,
                "contract": contract,
                "documents": created_documents,
                "user": user,
                "group_assigned": group_assigned,
            }

        except IntegrityError as e:
            await db.rollback()
            raise ValueError(f"Erreur d'intégrité des données: {str(e)}") from e
        except ValueError:
            await db.rollback()
            raise
        except Exception as e:
            await db.rollback()
            raise ValueError(f"Erreur lors de la création complète de l'employé: {str(e)}") from e

    @staticmethod
    async def get_employee_by_id(
        db: AsyncSession,
        employee_id: int
    ) -> Optional[Employe]:
        """Get employee by ID"""
        result = await db.execute(
            select(Employe).where(Employe.id == employee_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def update_employee(
        db: AsyncSession,
        employee_id: int,
        employee_data: Dict[str, Any]
    ) -> Optional[Employe]:
        """Update employee"""
        employee = await EmployeeService.get_employee_by_id(db, employee_id)
        if not employee:
            return None

        for key, value in employee_data.items():
            if value is not None and hasattr(employee, key):
                setattr(employee, key, value)

        await db.commit()
        await db.refresh(employee)
        return employee

    @staticmethod
    async def delete_employee(
        db: AsyncSession,
        employee_id: int
    ) -> bool:
        """Delete employee"""
        employee = await EmployeeService.get_employee_by_id(db, employee_id)
        if not employee:
            return False

        await db.delete(employee)
        await db.commit()
        return True


class UserService:
    """Service for managing user operations"""

    @staticmethod
    async def create_user(
        db: AsyncSession,
        user_data: UserCreate
    ) -> User:
        """Create a new user"""
        user = User(
            **user_data.model_dump(exclude={"password"}),
            password=get_password_hash(user_data.password)
        )
        db.add(user)

        try:
            await db.commit()
            await db.refresh(user)
            return user
        except IntegrityError:
            await db.rollback()
            raise ValueError(f"Un utilisateur avec l'email {user_data.email} existe déjà")

    @staticmethod
    async def get_user_by_email(
        db: AsyncSession,
        email: str
    ) -> Optional[User]:
        """Get user by email"""
        result = await db.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def assign_user_to_group(
        db: AsyncSession,
        user_id: int,
        group_id: int,
        assigned_by_id: Optional[int] = None
    ) -> UserGroup:
        """Assign user to a group"""
        # Validate user
        result = await db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise ValueError(f"Utilisateur avec l'ID {user_id} introuvable")

        # Validate group
        result = await db.execute(
            select(Group).where(Group.id == group_id, Group.is_active.is_(True))
        )
        group = result.scalar_one_or_none()
        if not group:
            raise ValueError(
                f"Groupe avec l'ID {group_id} introuvable ou inactif"
            )

        # Check if assignment already exists
        result = await db.execute(
            select(UserGroup).where(
                UserGroup.user_id == user_id,
                UserGroup.group_id == group_id
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            if existing.is_active:
                raise ValueError(
                    f"L'utilisateur est déjà assigné au groupe {group.code}"
                )
            # Reactivate existing assignment
            existing.is_active = True
            existing.assigned_by_id = assigned_by_id
            await db.commit()
            await db.refresh(existing)
            return existing

        # Create new assignment
        user_group = UserGroup(
            user_id=user_id,
            group_id=group_id,
            assigned_by_id=assigned_by_id,
            is_active=True
        )
        db.add(user_group)
        await db.commit()
        await db.refresh(user_group)
        return user_group


class GroupService:
    """Service for managing group operations"""

    @staticmethod
    async def create_with_services(
        db: AsyncSession,
        group_data: Dict[str, Any],
        service_ids: List[int]
    ) -> Tuple[Group, int]:
        """
        Create group with ServiceGroup associations

        Args:
            db: Database session
            group_data: Group creation data
            service_ids: List of service IDs to associate

        Returns:
            Tuple of (created group, number of ServiceGroups created)

        Raises:
            ValueError: If validation fails
        """
        # Validate unique code
        code = group_data.get('code', '').upper()
        if code:
            result = await db.execute(
                select(Group).where(func.upper(Group.code) == code)
            )
            if result.scalar_one_or_none():
                raise ValueError(f'Un groupe avec le code "{code}" existe déjà')

        # Validate service_ids if provided
        if service_ids:
            for service_id in service_ids:
                result = await db.execute(
                    select(Service).where(Service.id == service_id)
                )
                service = result.scalar_one_or_none()
                if not service:
                    raise ValueError(f'Service avec ID {service_id} introuvable')

        # Create group
        group = Group(**group_data)
        db.add(group)
        await db.flush()
        await db.refresh(group)

        # Create ServiceGroup associations
        created_count = 0
        if service_ids:
            for service_id in service_ids:
                # Check if association already exists
                result = await db.execute(
                    select(ServiceGroup).where(
                        ServiceGroup.service_id == service_id,
                        ServiceGroup.group_id == group.id
                    )
                )
                if not result.scalar_one_or_none():
                    service_group = ServiceGroup(
                        service_id=service_id,
                        group_id=group.id
                    )
                    db.add(service_group)
                    created_count += 1

        if created_count > 0:
            await db.flush()

        return group, created_count

    @staticmethod
    async def delete_with_validation(
        db: AsyncSession,
        group_id: int
    ) -> Dict[str, Any]:
        """
        Delete group with validation

        Args:
            db: Database session
            group_id: Group ID to delete

        Returns:
            Dictionary with deletion info

        Raises:
            ValueError: If group has active users or doesn't exist
        """
        # Get group
        result = await db.execute(
            select(Group)
            .options(selectinload(Group.user_groups))
            .where(Group.id == group_id)
        )
        group = result.scalar_one_or_none()

        if not group:
            raise ValueError(f'Groupe avec ID {group_id} introuvable')

        # Check if group has active users
        active_users_result = await db.execute(
            select(func.count(UserGroup.id))
            .where(
                UserGroup.group_id == group_id,
                UserGroup.is_active.is_(True)
            )
        )
        user_count = active_users_result.scalar() or 0

        if user_count > 0:
            raise ValueError(
                f'Impossible de supprimer le groupe "{group.code}". '
                f'Il contient {user_count} utilisateur(s) actif(s).'
            )

        # Count ServiceGroups to delete
        service_groups_result = await db.execute(
            select(func.count(ServiceGroup.id))
            .where(ServiceGroup.group_id == group_id)
        )
        service_groups_count = service_groups_result.scalar() or 0

        # Delete ServiceGroups (cascade)
        await db.execute(
            select(ServiceGroup)
            .where(ServiceGroup.group_id == group_id)
        )

        # Delete group
        await db.delete(group)
        await db.flush()

        return {
            'message': f'Groupe "{group.code}" supprimé avec succès',
            'service_groups_deleted': service_groups_count
        }

    @staticmethod
    async def list_with_meta(
        db: AsyncSession,
        is_active: Optional[bool] = None,
        expand: Optional[str] = None,
        skip: int = 0,
        limit: int = 100
    ) -> Tuple[List[Group], int, Dict[str, Any]]:
        """
        List groups with metadata

        Args:
            db: Database session
            is_active: Filter by active status
            expand: Relations to expand
            skip: Pagination offset
            limit: Pagination limit

        Returns:
            Tuple of (groups list, total count, metadata dict)
        """
        # Base query
        query = select(Group)

        # Apply filters
        if is_active is not None:
            query = query.where(Group.is_active == is_active)
        elif is_active is None:
            # Default: only active groups
            query = query.where(Group.is_active.is_(True))

        # Apply expansion
        if expand:
            expand_fields = parse_expand_param(expand)
            query = apply_expansion(query, Group, expand_fields)

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # Apply pagination and ordering
        query = query.order_by(Group.code).offset(skip).limit(limit)

        # Execute query
        result = await db.execute(query)
        groups = result.scalars().all()

        # Get metadata
        total_groups_result = await db.execute(select(func.count(Group.id)))
        total_groups = total_groups_result.scalar() or 0

        active_groups_result = await db.execute(
            select(func.count(Group.id)).where(Group.is_active.is_(True))
        )
        active_groups = active_groups_result.scalar() or 0

        meta = {
            'total_groups': total_groups,
            'active_groups': active_groups
        }

        return list(groups), total, meta



class PermissionService:
    """Service for managing permissions and authorization"""

    @staticmethod
    async def get_user_permissions(
        db: AsyncSession,
        user_id: int
    ) -> set[str]:
        """
        Get all permission codenames for a user based on their group memberships

        Args:
            db: Database session
            user_id: User ID

        Returns:
            Set of permission codenames (e.g., {'employe.view', 'user.create'})
        """
        # Get user's active groups
        result = await db.execute(
            select(UserGroup)
            .where(
                UserGroup.user_id == user_id,
                UserGroup.is_active.is_(True)
            )
            .options(selectinload(UserGroup.group))
        )
        user_groups = result.scalars().all()

        if not user_groups:
            return set()

        # Get group IDs
        group_ids = [ug.group_id for ug in user_groups if ug.group.is_active]

        if not group_ids:
            return set()

        # Get all granted permissions for these groups
        result = await db.execute(
            select(GroupPermission)
            .where(
                GroupPermission.group_id.in_(group_ids),
                GroupPermission.granted.is_(True)
            )
            .options(selectinload(GroupPermission.permission))
        )
        group_permissions = result.scalars().all()

        # Extract permission codenames
        permissions = {gp.permission.codename for gp in group_permissions}

        return permissions

    @staticmethod
    async def check_permission(
        db: AsyncSession,
        user: User,
        resource: str,
        action: str
    ) -> bool:
        """
        Check if a user has a specific permission

        Args:
            db: Database session
            user: User instance
            resource: Resource name (e.g., 'employe', 'user')
            action: Action name (e.g., 'view', 'create', 'update', 'delete')

        Returns:
            True if user has the permission, False otherwise
        """
        if not user or not user.is_active:
            return False

        # Superusers have all permissions
        if user.is_superuser:
            return True

        # Get user permissions
        user_permissions = await PermissionService.get_user_permissions(db, user.id)

        # Check for specific permission
        permission_codename = f"{resource}.{action}"
        return permission_codename in user_permissions

    @staticmethod
    async def get_effective_permissions(
        db: AsyncSession,
        user_id: int
    ) -> dict:
        """
        Get detailed information about user's effective permissions

        Args:
            db: Database session
            user_id: User ID

        Returns:
            Dictionary with groups, permissions, and counts
        """
        # Get user's active groups with details
        result = await db.execute(
            select(UserGroup)
            .where(
                UserGroup.user_id == user_id,
                UserGroup.is_active.is_(True)
            )
            .options(selectinload(UserGroup.group))
            .order_by(UserGroup.group_id)
        )
        user_groups = result.scalars().all()

        groups_data = []
        for ug in user_groups:
            if ug.group.is_active:
                groups_data.append({
                    'id': ug.group.id,
                    'code': ug.group.code,
                    'name': ug.group.name,
                    'description': ug.group.description,
                    'assigned_at': ug.assigned_at
                })

        # Get all permissions for these groups
        permissions_data = []
        if user_groups:
            group_ids = [ug.group_id for ug in user_groups if ug.group.is_active]

            if group_ids:
                result = await db.execute(
                    select(GroupPermission)
                    .where(
                        GroupPermission.group_id.in_(group_ids),
                        GroupPermission.granted.is_(True)
                    )
                    .options(
                        selectinload(GroupPermission.permission),
                        selectinload(GroupPermission.group)
                    )
                    .order_by(GroupPermission.permission_id)
                )
                group_permissions = result.scalars().all()

                for gp in group_permissions:
                    permissions_data.append({
                        'id': gp.permission.id,
                        'codename': gp.permission.codename,
                        'name': gp.permission.name,
                        'resource': gp.permission.resource,
                        'action': gp.permission.action,
                        'description': gp.permission.description,
                        'granted_by_group': gp.group.code
                    })

        return {
            'groups': groups_data,
            'permissions': permissions_data,
            'permission_count': len(permissions_data),
            'group_count': len(groups_data)
        }

    @staticmethod
    async def create_group_permission(
        db: AsyncSession,
        group_id: int,
        permission_id: int,
        granted: bool = True,
        created_by_id: Optional[int] = None
    ) -> GroupPermission:
        """
        Create a group permission assignment

        Args:
            db: Database session
            group_id: Group ID
            permission_id: Permission ID
            granted: Whether permission is granted or denied
            created_by_id: ID of user creating the assignment

        Returns:
            Created GroupPermission instance

        Raises:
            ValueError: If validation fails
        """
        # Validate group
        result = await db.execute(
            select(Group).where(Group.id == group_id, Group.is_active.is_(True))
        )
        group = result.scalar_one_or_none()
        if not group:
            raise ValueError(f"Groupe avec ID {group_id} introuvable ou inactif")

        # Validate permission
        result = await db.execute(
            select(Permission).where(Permission.id == permission_id)
        )
        permission = result.scalar_one_or_none()
        if not permission:
            raise ValueError(f"Permission avec ID {permission_id} introuvable")

        # Check for duplicate
        result = await db.execute(
            select(GroupPermission).where(
                GroupPermission.group_id == group_id,
                GroupPermission.permission_id == permission_id
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            raise ValueError(
                f"La permission {permission.codename} est déjà assignée au groupe {group.code}"
            )

        # Create group permission
        group_permission = GroupPermission(
            group_id=group_id,
            permission_id=permission_id,
            granted=granted,
            created_by_id=created_by_id
        )
        db.add(group_permission)
        await db.flush()
        await db.refresh(group_permission)

        return group_permission

    @staticmethod
    async def list_group_permissions(
        db: AsyncSession,
        group_id: Optional[int] = None,
        permission_id: Optional[int] = None,
        granted: Optional[bool] = None,
        skip: int = 0,
        limit: int = 100
    ) -> Tuple[List[GroupPermission], int]:
        """
        List group permissions with filters

        Args:
            db: Database session
            group_id: Filter by group ID
            permission_id: Filter by permission ID
            granted: Filter by granted status
            skip: Pagination offset
            limit: Pagination limit

        Returns:
            Tuple of (group permissions list, total count)
        """
        query = select(GroupPermission)

        # Apply filters
        if group_id is not None:
            query = query.where(GroupPermission.group_id == group_id)

        if permission_id is not None:
            query = query.where(GroupPermission.permission_id == permission_id)

        if granted is not None:
            query = query.where(GroupPermission.granted == granted)

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # Apply pagination
        query = query.offset(skip).limit(limit)

        # Execute query
        result = await db.execute(query)
        group_permissions = result.scalars().all()

        return list(group_permissions), total
