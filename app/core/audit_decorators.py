"""Decorators for audit logging"""
import time
import logging
import functools
from typing import Callable, Optional
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit_app.services import AuditService
from app.user_app.models import User

logger = logging.getLogger(__name__)


def audit_action(
    action: str,
    resource_type: str,
    extract_resource_id: Optional[Callable] = None,
    extract_old_values: Optional[Callable] = None,
    extract_new_values: Optional[Callable] = None
):
    """
    Decorator to automatically audit an action.

    This decorator wraps a route handler and logs the action to the audit system.
    It captures:
    - User performing the action
    - Action type (CREATE, UPDATE, DELETE, etc.)
    - Resource type and ID
    - Old and new values (for UPDATE/DELETE)
    - Execution time
    - Request context

    Usage:
        @audit_action(
            action="CREATE",
            resource_type="employe",
            extract_resource_id=lambda result: str(result.id),
            extract_new_values=lambda result: {"nom": result.nom}
        )
        async def create_employee(
            db: AsyncSession,
            current_user: User,
            request: Request,
            data: EmployeeCreate
        ):
            # Your route logic here
            pass

    Args:
        action: Action type (CREATE, UPDATE, DELETE, etc.)
        resource_type: Type of resource being acted upon
        extract_resource_id: Function to extract resource ID from result
        extract_old_values: Function to extract old values (for UPDATE/DELETE)
        extract_new_values: Function to extract new values (for CREATE/UPDATE)

    Returns:
        Decorated function

    Note:
        The decorated function must have parameters named:
        - db: AsyncSession
        - current_user: User
        - request: Request (optional)
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract dependencies from kwargs
            db: Optional[AsyncSession] = kwargs.get("db")
            current_user: Optional[User] = kwargs.get("current_user")
            request: Optional[Request] = kwargs.get("request")

            # Start timing
            start_time = time.time()

            # Initialize values
            resource_id = None
            old_values = None
            new_values = None
            response_status = 200
            result = None

            try:
                # Execute the original function
                result = await func(*args, **kwargs)

                # Extract resource ID from result
                if extract_resource_id and result:
                    try:
                        resource_id = extract_resource_id(result)
                    except Exception as e:
                        logger.warning(f"Failed to extract resource_id: {e}")

                # Extract old values (for UPDATE/DELETE)
                if extract_old_values:
                    try:
                        old_values = extract_old_values(kwargs)
                    except Exception as e:
                        logger.warning(f"Failed to extract old_values: {e}")

                # Extract new values (for CREATE/UPDATE)
                if extract_new_values and result:
                    try:
                        new_values = extract_new_values(result)
                    except Exception as e:
                        logger.warning(f"Failed to extract new_values: {e}")

            except Exception as e:
                # Mark as failed action
                response_status = 500
                logger.error(f"Action failed: {e}")
                raise

            finally:
                # Calculate execution time
                execution_time = time.time() - start_time

                # Log the action (in background, never block)
                if db and current_user:
                    try:
                        await AuditService.log_action(
                            db=db,
                            user=current_user,
                            action=action,
                            resource_type=resource_type,
                            resource_id=resource_id,
                            old_values=old_values,
                            new_values=new_values,
                            request=request,
                            response_status=response_status,
                            execution_time=execution_time
                        )
                    except Exception as e:
                        # Never let audit failures affect the application
                        logger.error(f"❌ Failed to log action in decorator: {e}")

            return result

        return wrapper
    return decorator


def audit_login(func: Callable) -> Callable:
    """
    Decorator specifically for login actions.

    Usage:
        @audit_login
        async def login(
            db: AsyncSession,
            request: Request,
            credentials: LoginCredentials
        ):
            # Your login logic here
            pass

    Args:
        func: The function to decorate

    Returns:
        Decorated function
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        db: Optional[AsyncSession] = kwargs.get("db")
        request: Optional[Request] = kwargs.get("request")

        user = None
        success = False

        try:
            # Execute the original function
            result = await func(*args, **kwargs)

            # Extract user from result (assuming it returns user or token with user)
            if hasattr(result, "user"):
                user = result.user
            elif isinstance(result, dict) and "user" in result:
                user = result["user"]

            success = True

        except Exception as e:
            success = False
            logger.error(f"Login failed: {e}")
            raise

        finally:
            # Log the login attempt
            if db:
                try:
                    await AuditService.log_login(
                        db=db,
                        user=user,
                        request=request,
                        success=success
                    )
                except Exception as e:
                    logger.error(f"❌ Failed to log login: {e}")

        return result

    return wrapper


def audit_logout(func: Callable) -> Callable:
    """
    Decorator specifically for logout actions.

    Usage:
        @audit_logout
        async def logout(
            db: AsyncSession,
            current_user: User,
            request: Request
        ):
            # Your logout logic here
            pass

    Args:
        func: The function to decorate

    Returns:
        Decorated function
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        db: Optional[AsyncSession] = kwargs.get("db")
        current_user: Optional[User] = kwargs.get("current_user")
        request: Optional[Request] = kwargs.get("request")

        try:
            # Execute the original function
            result = await func(*args, **kwargs)

        finally:
            # Log the logout
            if db and current_user:
                try:
                    await AuditService.log_logout(
                        db=db,
                        user=current_user,
                        request=request
                    )
                except Exception as e:
                    logger.error(f"❌ Failed to log logout: {e}")

        return result

    return wrapper


def audit_export(
    resource_type: str,
    format_param: str = "format"
):
    """
    Decorator specifically for export actions.

    Usage:
        @audit_export(resource_type="employe", format_param="format")
        async def export_employees(
            db: AsyncSession,
            current_user: User,
            request: Request,
            format: str = "excel"
        ):
            # Your export logic here
            pass

    Args:
        resource_type: Type of resource being exported
        format_param: Name of the parameter containing the format

    Returns:
        Decorated function
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            db: Optional[AsyncSession] = kwargs.get("db")
            current_user: Optional[User] = kwargs.get("current_user")
            request: Optional[Request] = kwargs.get("request")

            # Extract format from kwargs
            format_type = kwargs.get(format_param, "excel")

            try:
                # Execute the original function
                result = await func(*args, **kwargs)

            finally:
                # Log the export
                if db and current_user:
                    try:
                        await AuditService.log_export(
                            db=db,
                            user=current_user,
                            resource_type=resource_type,
                            format_type=format_type,
                            request=request
                        )
                    except Exception as e:
                        logger.error(f"❌ Failed to log export: {e}")

            return result

        return wrapper
    return decorator
