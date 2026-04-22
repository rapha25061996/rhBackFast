"""Permission checking utilities for route protection"""
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.config import settings
from app.user_app.models import User
from app.user_app.services import PermissionService


def require_permission(resource: str, action: str):
    """
    Dependency factory to check if user has required permission
    
    Respects configuration settings:
    - If AUTHENTICATION_ENABLED=False: Returns mock superuser
    - If PERMISSION_CHECK_ENABLED=False: Returns authenticated user without permission check
    - If both enabled: Checks permissions normally

    Args:
        resource: Resource name (e.g., 'employe', 'user', 'payroll')
        action: Action name (e.g., 'CREATE', 'READ', 'UPDATE', 'DELETE')

    Returns:
        Dependency function that checks permission and returns current user

    Usage:
        @router.get("/employees")
        async def list_employees(
            db: AsyncSession = Depends(get_db),
            current_user: User = Depends(require_permission("employe", "READ"))
        ):
            # User has permission, proceed with logic
            ...

    Raises:
        HTTPException: 401 if authentication required but not provided
        HTTPException: 403 if permission check enabled and user lacks permission
    """
    async def permission_checker(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
    ) -> User:
        # If authentication is disabled, return mock superuser
        if not settings.AUTHENTICATION_ENABLED:
            mock_user = User(
                id=0,
                email="system@localhost",
                nom="System",
                prenom="User",
                is_active=True,
                is_superuser=True
            )
            return mock_user
        
        # If permission checks are disabled, return user without checking
        if not settings.PERMISSION_CHECK_ENABLED:
            return current_user
        
        # Superusers bypass all permission checks
        if current_user.is_superuser:
            return current_user

        # Check if user has the required permission
        has_permission = await PermissionService.check_permission(
            db, current_user, resource, action
        )

        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {resource}.{action}"
            )

        return current_user

    return permission_checker


async def check_permission_or_403(
    db: AsyncSession,
    user: User,
    resource: str,
    action: str
) -> None:
    """
    Helper function to check permission and raise 403 if denied
    
    Respects configuration settings:
    - If AUTHENTICATION_ENABLED=False: Always passes
    - If PERMISSION_CHECK_ENABLED=False: Always passes
    - If both enabled: Checks permissions normally

    Args:
        db: Database session
        user: Current user
        resource: Resource name
        action: Action name

    Raises:
        HTTPException: 403 Forbidden if permission check enabled and user lacks permission

    Usage:
        async def some_function(db: AsyncSession, user: User):
            # Check permission inline
            await check_permission_or_403(db, user, "employe", "DELETE")

            # Proceed with logic
            ...
    """
    # Skip if authentication or permission checks are disabled
    if not settings.AUTHENTICATION_ENABLED or not settings.PERMISSION_CHECK_ENABLED:
        return
    
    if user.is_superuser:
        return

    has_permission = await PermissionService.check_permission(
        db, user, resource, action
    )

    if not has_permission:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: {resource}.{action}"
        )
