"""Centralized constants for the audit module.

Single source of truth for every magic string related to audit logging:
- ``AuditAction``    : every valid value of ``AuditLog.action`` (also used to
  build the DB CHECK constraint in :mod:`app.audit_app.models`).
- ``AuditResourceType`` : well-known values of ``AuditLog.resource_type``
  emitted by the codebase (routes, services, middleware).
- ``AuditRequestState`` : attribute names set on ``Request.state`` to
  coordinate between the middleware and manual ``AuditService`` calls.
- ``HTTP_METHOD_TO_ACTION`` / ``AUDITED_HTTP_METHODS`` / ``AUDIT_SKIP_PATHS``
  / ``AUDIT_SKIP_PATH_PREFIXES`` : configuration for :class:`AuditMiddleware`.
- ``FAILED_ACTION_SUFFIX`` / ``ANONYMOUS_USER_DISPLAY`` : display helpers.

Anything hard-coded as a string elsewhere in ``app/audit_app`` or
``app/core/audit_*`` should be imported from this module.
"""
from __future__ import annotations

from enum import Enum


class AuditAction(str, Enum):
    """Valid values of :attr:`AuditLog.action`.

    The DB CHECK constraint ``ck_audit_action`` is built from this enum, so
    adding a value here is the *only* place to touch when extending audit
    coverage (plus an Alembic migration if the constraint must follow).
    """

    # CRUD
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"

    # Authentication
    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"
    LOGIN_FAILED = "LOGIN_FAILED"

    # Read/consultation
    VIEW = "VIEW"
    VIEW_FAILED = "VIEW_FAILED"

    # Bulk / misc
    EXPORT = "EXPORT"
    BULK_OPERATION = "BULK_OPERATION"

    # Failed CRUD (captured by middleware when response >= 400)
    CREATE_FAILED = "CREATE_FAILED"
    UPDATE_FAILED = "UPDATE_FAILED"
    DELETE_FAILED = "DELETE_FAILED"

    @classmethod
    def values(cls) -> tuple[str, ...]:
        """Tuple of every enum value (order = declaration order)."""
        return tuple(member.value for member in cls)

    @classmethod
    def check_constraint_expression(cls) -> str:
        """SQL fragment for the CHECK constraint on ``audit_log.action``."""
        joined = ", ".join(f"'{v}'" for v in cls.values())
        return f"action IN ({joined})"


class AuditResourceType(str, Enum):
    """Well-known values of :attr:`AuditLog.resource_type`.

    New resource types can be added as strings directly; this enum simply
    documents the ones emitted by the existing codebase so they don't drift.
    """

    UNKNOWN = "unknown"
    AUTHENTICATION = "authentication"

    # user_app
    EMPLOYE = "employe"
    USER = "user_management_user"

    # paie_app
    ALERT = "alert"
    RETENUE = "retenue"
    RETENUES = "retenues"
    PERIODE_PAIE = "periode_paie"
    ENTREE_PAIE = "entree_paie"
    ALL_PERIODES = "all_periodes"
    PAYROLL = "payroll"
    PAYSLIP = "payslip"
    PAYSLIP_BULK = "payslip_bulk"


class AuditRequestState:
    """Attribute names set on ``Request.state`` by the audit layer.

    ``AUDIT_LOGGED`` is the one-way flag posed by
    :meth:`AuditService.log_action` so :class:`AuditMiddleware` can skip its
    background log and avoid producing a duplicate row.
    """

    AUDIT_LOGGED: str = "audit_logged"


# --- HTTP <-> audit mapping ------------------------------------------------

#: HTTP methods the middleware will audit automatically (read operations are
#: left to explicit ``AuditService.log_view`` calls).
AUDITED_HTTP_METHODS: tuple[str, ...] = ("POST", "PUT", "PATCH", "DELETE")

#: Default translation of an HTTP method to an audit action.
HTTP_METHOD_TO_ACTION: dict[str, str] = {
    "POST": AuditAction.CREATE.value,
    "PUT": AuditAction.UPDATE.value,
    "PATCH": AuditAction.UPDATE.value,
    "DELETE": AuditAction.DELETE.value,
    "GET": AuditAction.VIEW.value,
}


# --- Middleware skip rules -------------------------------------------------

#: Path prefixes the middleware skips outright (noisy infra endpoints).
AUDIT_SKIP_PATHS: tuple[str, ...] = (
    "/docs",
    "/redoc",
    "/openapi.json",
    "/favicon.ico",
    "/health",
    "/metrics",
    "/static",
)

#: Extra prefixes skipped to prevent recursion (the audit API itself).
AUDIT_SKIP_PATH_PREFIXES: tuple[str, ...] = ("/api/audit",)


# --- Display helpers -------------------------------------------------------

#: Suffix appended to any failure action (CREATE_FAILED, DELETE_FAILED, ...).
FAILED_ACTION_SUFFIX: str = "_FAILED"

#: Label used when the audit log has no associated user.
ANONYMOUS_USER_DISPLAY: str = "Anonymous"


__all__ = [
    "AuditAction",
    "AuditResourceType",
    "AuditRequestState",
    "AUDITED_HTTP_METHODS",
    "HTTP_METHOD_TO_ACTION",
    "AUDIT_SKIP_PATHS",
    "AUDIT_SKIP_PATH_PREFIXES",
    "FAILED_ACTION_SUFFIX",
    "ANONYMOUS_USER_DISPLAY",
]
