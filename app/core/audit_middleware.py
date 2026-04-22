"""Middleware for automatic audit logging of all requests"""
import time
import logging
from typing import Callable, Optional
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.background import BackgroundTask

from app.audit_app.constants import (
    AUDIT_SKIP_PATH_PREFIXES,
    AUDIT_SKIP_PATHS,
    AUDITED_HTTP_METHODS,
    HTTP_METHOD_TO_ACTION,
    AuditRequestState,
    AuditResourceType,
)
from app.core.database import get_db
from app.audit_app.services import AuditService
from app.user_app.models import User

logger = logging.getLogger(__name__)


class AuditMiddleware(BaseHTTPMiddleware):
    """
    Middleware that automatically logs all requests to the audit system.

    This middleware captures:
    - Request method, path, and headers
    - Response status code
    - Execution time
    - User information (if authenticated)
    - IP address and user agent

    The audit logging is done in the background to avoid blocking requests.
    """

    # Paths / prefixes to skip + HTTP methods to audit are declared in
    # app.audit_app.constants to keep a single source of truth shared with
    # AuditService and the ORM-level CHECK constraint. Class attributes are
    # preserved for backward compatibility with any external caller reading
    # them (e.g. tests).
    SKIP_PATHS: tuple[str, ...] = AUDIT_SKIP_PATHS
    AUDIT_METHODS: tuple[str, ...] = AUDITED_HTTP_METHODS

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """
        Process the request and log it to the audit system.

        Args:
            request: The incoming request
            call_next: The next middleware or route handler

        Returns:
            The response from the route handler
        """
        # Check if we should skip this path
        if self._should_skip_audit(request):
            return await call_next(request)

        # Start timing
        start_time = time.time()

        # Process the request
        response = await call_next(request)

        # Calculate execution time
        execution_time = time.time() - start_time

        # Skip if the endpoint already logged the action manually
        # (via AuditService.log_action / log_model_change / log_export /
        # log_login / log_logout / log_view / audit_action decorator).
        # AuditService sets request.state.<AUDIT_LOGGED> = True whenever a
        # request is passed to it, so we can rely on it here to avoid
        # producing a duplicate audit entry.
        already_logged = getattr(
            request.state, AuditRequestState.AUDIT_LOGGED, False
        )

        # Only audit certain methods or failed requests, and never double-log
        should_audit = (
            not already_logged and (
                request.method in self.AUDIT_METHODS or
                response.status_code >= 400
            )
        )

        if should_audit:
            # Add background task to log the request
            response.background = BackgroundTask(
                self._log_request,
                request=request,
                response_status=response.status_code,
                execution_time=execution_time
            )

        return response

    def _should_skip_audit(self, request: Request) -> bool:
        """
        Check if the request should be skipped from audit.

        Args:
            request: The incoming request

        Returns:
            True if the request should be skipped, False otherwise
        """
        path = request.url.path

        # Skip paths in the skip list
        for skip_path in self.SKIP_PATHS:
            if path.startswith(skip_path):
                return True

        # Skip audit endpoints themselves (to avoid recursion)
        for prefix in AUDIT_SKIP_PATH_PREFIXES:
            if path.startswith(prefix):
                return True

        return False

    def _method_to_action(self, method: str) -> str:
        """
        Convert HTTP method to audit action.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE, etc.)

        Returns:
            Audit action string
        """
        return HTTP_METHOD_TO_ACTION.get(method, method)

    def _extract_resource_type(self, path: str) -> str:
        """
        Extract resource type from the request path.

        Args:
            path: Request path (e.g., /api/employees/123)

        Returns:
            Resource type (e.g., "employees")
        """
        # Remove /api prefix if present
        if path.startswith("/api/"):
            path = path[5:]

        # Split by / and get the first segment
        parts = path.strip("/").split("/")
        if parts and parts[0]:
            return parts[0]

        return AuditResourceType.UNKNOWN.value

    async def _log_request(
        self,
        request: Request,
        response_status: int,
        execution_time: float
    ) -> None:
        """
        Log the request to the audit system (background task).

        This method is executed in the background after the response
        has been sent to the client.

        Args:
            request: The request object
            response_status: HTTP response status code
            execution_time: Time taken to process the request (seconds)
        """
        try:
            # Get database session
            async for db in get_db():
                # Extract user from request state (set by auth middleware)
                user: Optional[User] = getattr(request.state, "user", None)

                # Extract resource information
                action = self._method_to_action(request.method)
                resource_type = self._extract_resource_type(request.url.path)

                # Log the action
                await AuditService.log_action(
                    db=db,
                    user=user,
                    action=action,
                    resource_type=resource_type,
                    request=request,
                    response_status=response_status,
                    execution_time=execution_time
                )

                break  # Only use the first session

        except Exception as e:
            # Never let audit failures affect the application
            logger.error(f"❌ Failed to log request in middleware: {e}")
