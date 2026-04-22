"""Audit service for logging all system actions"""
import logging
from typing import Optional, Any
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit_app.constants import (
    AuditAction,
    AuditRequestState,
    AuditResourceType,
)
from app.audit_app.models import AuditLog
from app.user_app.models import User

logger = logging.getLogger(__name__)


class AuditService:
    """
    Centralized audit service for logging all system actions.

    This service provides methods to log various types of actions
    (CRUD, authentication, exports, etc.) with complete context.

    All methods are designed to never raise exceptions that would
    affect the main application flow.
    """

    @staticmethod
    async def log_action(
        db: AsyncSession,
        user: Optional[User] = None,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        old_values: Optional[dict] = None,
        new_values: Optional[dict] = None,
        request: Optional[Request] = None,
        response_status: Optional[int] = None,
        execution_time: Optional[float] = None
    ) -> Optional[AuditLog]:
        """
        Log an action to the audit system.

        This is the main method for creating audit logs. It captures
        all relevant context and stores it in the database.

        Args:
            db: Database session
            user: User performing the action (None for anonymous)
            action: Action type (CREATE, UPDATE, DELETE, etc.)
            resource_type: Type of resource affected
            resource_id: ID of the resource (optional)
            old_values: Values before modification (for UPDATE/DELETE)
            new_values: Values after modification (for CREATE/UPDATE)
            request: FastAPI Request object (for context extraction)
            response_status: HTTP response status code
            execution_time: Time taken to execute the action (seconds)

        Returns:
            AuditLog instance if successful, None if failed

        Note:
            This method never raises exceptions. Audit failures are logged
            but do not affect the main application flow.
        """
        try:
            # Sanitize sensitive data
            old_values = AuditService._sanitize_data(old_values)
            new_values = AuditService._sanitize_data(new_values)

            # Extract request context
            ip_address = None
            user_agent = None
            request_method = None
            request_path = None

            if request:
                ip_address = AuditService._get_client_ip(request)
                user_agent = request.headers.get("user-agent", "")
                request_method = request.method
                request_path = str(request.url.path)
                # Signal to AuditMiddleware that this request has already
                # been audited manually, so it must skip its own background
                # log and avoid producing a duplicate entry.
                try:
                    setattr(request.state, AuditRequestState.AUDIT_LOGGED, True)
                except Exception:
                    pass

            # Create audit log entry
            audit_log = AuditLog(
                user_id=user.id if user else None,
                action=action or "UNKNOWN",
                resource_type=resource_type or AuditResourceType.UNKNOWN.value,
                resource_id=resource_id,
                old_values=old_values,
                new_values=new_values,
                ip_address=ip_address,
                user_agent=user_agent,
                request_method=request_method,
                request_path=request_path,
                response_status=response_status,
                execution_time=execution_time
            )

            db.add(audit_log)
            await db.commit()
            await db.refresh(audit_log)

            logger.info(
                f"✅ Audit log created: {action} on {resource_type} "
                f"by {user.email if user else 'anonymous'}"
            )
            return audit_log

        except Exception as e:
            logger.error(f"❌ Failed to create audit log: {e}")
            return None

    @staticmethod
    async def log_login(
        db: AsyncSession,
        user: Optional[User],
        request: Request,
        success: bool = True
    ) -> Optional[AuditLog]:
        """
        Log a login attempt.

        Args:
            db: Database session
            user: User attempting to login
            request: FastAPI Request object
            success: Whether the login was successful

        Returns:
            AuditLog instance if successful, None if failed
        """
        action = AuditAction.LOGIN.value if success else AuditAction.LOGIN_FAILED.value

        return await AuditService.log_action(
            db=db,
            user=user if success else None,
            action=action,
            resource_type=AuditResourceType.AUTHENTICATION.value,
            resource_id=str(user.id) if user else None,
            request=request,
            response_status=200 if success else 401
        )

    @staticmethod
    async def log_logout(
        db: AsyncSession,
        user: User,
        request: Request
    ) -> Optional[AuditLog]:
        """
        Log a logout.

        Args:
            db: Database session
            user: User logging out
            request: FastAPI Request object

        Returns:
            AuditLog instance if successful, None if failed
        """
        return await AuditService.log_action(
            db=db,
            user=user,
            action=AuditAction.LOGOUT.value,
            resource_type=AuditResourceType.AUTHENTICATION.value,
            resource_id=str(user.id),
            request=request,
            response_status=200
        )

    @staticmethod
    async def log_model_change(
        db: AsyncSession,
        user: User,
        instance: Any,
        action: str,
        old_values: Optional[dict] = None,
        request: Optional[Request] = None
    ) -> Optional[AuditLog]:
        """
        Log a model change (CREATE, UPDATE, DELETE).

        Args:
            db: Database session
            user: User performing the action
            instance: SQLAlchemy model instance
            action: Action type (CREATE, UPDATE, DELETE)
            old_values: Values before modification (for UPDATE/DELETE)
            request: FastAPI Request object (optional)

        Returns:
            AuditLog instance if successful, None if failed
        """
        # Extract new values from instance
        new_values = AuditService._extract_model_values(instance)

        # Get resource type from table name
        resource_type = AuditResourceType.UNKNOWN.value
        if hasattr(instance, '__tablename__'):
            resource_type = instance.__tablename__

        # Get resource ID
        resource_id = None
        if hasattr(instance, 'id'):
            resource_id = str(instance.id)

        return await AuditService.log_action(
            db=db,
            user=user,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            old_values=old_values,
            new_values=new_values,
            request=request
        )

    @staticmethod
    async def log_bulk_operation(
        db: AsyncSession,
        user: User,
        resource_type: str,
        count: int,
        action: str = AuditAction.BULK_OPERATION.value,
        request: Optional[Request] = None
    ) -> Optional[AuditLog]:
        """
        Log a bulk operation.

        Args:
            db: Database session
            user: User performing the operation
            resource_type: Type of resource affected
            count: Number of items affected
            action: Action type (default: BULK_OPERATION)
            request: FastAPI Request object (optional)

        Returns:
            AuditLog instance if successful, None if failed
        """
        return await AuditService.log_action(
            db=db,
            user=user,
            action=action,
            resource_type=resource_type,
            resource_id=f"bulk_{count}_items",
            new_values={"affected_count": count},
            request=request
        )

    @staticmethod
    async def log_export(
        db: AsyncSession,
        user: User,
        resource_type: str,
        format_type: str = "excel",
        count: Optional[int] = None,
        request: Optional[Request] = None
    ) -> Optional[AuditLog]:
        """
        Log a data export.

        Args:
            db: Database session
            user: User performing the export
            resource_type: Type of resource exported
            format_type: Export format (excel, csv, json, pdf)
            count: Number of items exported (optional)
            request: FastAPI Request object (optional)

        Returns:
            AuditLog instance if successful, None if failed
        """
        export_data = {
            "format": format_type,
            "exported_count": count
        }

        return await AuditService.log_action(
            db=db,
            user=user,
            action=AuditAction.EXPORT.value,
            resource_type=resource_type,
            resource_id=f"export_{format_type}",
            new_values=export_data,
            request=request
        )

    @staticmethod
    async def log_view(
        db: AsyncSession,
        user: User,
        resource_type: str,
        resource_id: Optional[str] = None,
        request: Optional[Request] = None
    ) -> Optional[AuditLog]:
        """
        Log a view/consultation of a resource.

        Useful for tracking access to sensitive data.

        Args:
            db: Database session
            user: User viewing the resource
            resource_type: Type of resource viewed
            resource_id: ID of the resource (optional)
            request: FastAPI Request object (optional)

        Returns:
            AuditLog instance if successful, None if failed
        """
        return await AuditService.log_action(
            db=db,
            user=user,
            action=AuditAction.VIEW.value,
            resource_type=resource_type,
            resource_id=resource_id,
            request=request
        )

    @staticmethod
    def _get_client_ip(request: Request) -> Optional[str]:
        """
        Extract the real client IP address.

        Checks X-Forwarded-For header first (for proxies/load balancers),
        then falls back to direct connection IP.

        Args:
            request: FastAPI Request object

        Returns:
            IP address as string, or None if not available
        """
        if not request:
            return None

        # Check X-Forwarded-For header (for proxies/load balancers)
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # Take the first IP in the chain
            return forwarded.split(",")[0].strip()

        # Fallback to direct connection
        if request.client:
            return request.client.host

        return None

    @staticmethod
    def _sanitize_data(data: Optional[dict]) -> Optional[dict]:
        """
        Remove or mask sensitive data from dictionaries.

        This prevents passwords, tokens, and other sensitive information
        from being stored in audit logs.

        Args:
            data: Dictionary to sanitize

        Returns:
            Sanitized dictionary with sensitive fields masked
        """
        if not data or not isinstance(data, dict):
            return data

        # Create a copy to avoid modifying the original
        sanitized = data.copy()

        # List of sensitive field names (case-insensitive matching)
        sensitive_fields = [
            'password', 'passwd', 'pwd',
            'token', 'access_token', 'refresh_token',
            'secret', 'secret_key', 'api_key',
            'authorization', 'csrf_token',
            'credit_card', 'card_number', 'cvv',
            'ssn', 'social_security',
            'private_key', 'encryption_key'
        ]

        # Mask sensitive fields
        for field in list(sanitized.keys()):
            field_lower = field.lower()
            if any(sensitive in field_lower for sensitive in sensitive_fields):
                sanitized[field] = "***MASKED***"

        return sanitized

    @staticmethod
    def _extract_model_values(instance: Any) -> dict:
        """
        Extract values from a SQLAlchemy model instance.

        Args:
            instance: SQLAlchemy model instance

        Returns:
            Dictionary of field names and values
        """
        if not hasattr(instance, '__table__'):
            return {}

        values = {}
        try:
            for column in instance.__table__.columns:
                # Skip internal fields
                if not column.name.endswith('_ptr'):
                    value = getattr(instance, column.name, None)
                    # Convert non-serializable types
                    if value is not None:
                        values[column.name] = str(value)
        except Exception as e:
            logger.warning(f"Failed to extract model values: {e}")

        return values
