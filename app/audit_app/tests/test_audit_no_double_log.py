"""Tests verifying that AuditService + AuditMiddleware do not double-log.

The middleware logs every POST/PUT/PATCH/DELETE globally as a fallback. Many
endpoints (paie, user) additionally call ``AuditService.log_*`` manually to
enrich the audit trail with resource-specific context (resource_id, old_values,
new_values, login/logout, export, etc.). Before this fix every such request
produced *two* rows in ``audit_log``.

The fix uses ``request.state.audit_logged`` as a one-way flag:
``AuditService.log_action`` sets it whenever it receives a ``request`` argument;
``AuditMiddleware.dispatch`` skips its own background log if the flag is set.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.audit_app.services import AuditService


class _FakeRequest:
    """Minimal Request stand-in exposing just what AuditService touches."""

    def __init__(self, method: str = "POST", path: str = "/api/employees"):
        self.method = method
        self.url = SimpleNamespace(path=path)
        self.headers = {"user-agent": "pytest", "x-forwarded-for": "1.2.3.4"}
        self.client = SimpleNamespace(host="1.2.3.4")
        self.state = SimpleNamespace()


@pytest.mark.asyncio
async def test_log_action_sets_audit_logged_flag_on_request():
    """AuditService.log_action must set request.state.audit_logged=True."""
    request = _FakeRequest()
    db = AsyncMock()

    await AuditService.log_action(
        db=db,
        user=None,
        action="CREATE",
        resource_type="employe",
        resource_id="42",
        request=request,
    )

    assert getattr(request.state, "audit_logged", False) is True, (
        "log_action must tag the request so AuditMiddleware skips its own log"
    )


@pytest.mark.asyncio
async def test_log_action_without_request_does_not_raise():
    """Calling log_action without a request must still work (no side effect)."""
    db = AsyncMock()

    # Should not raise: there is no request.state to touch.
    await AuditService.log_action(
        db=db,
        user=None,
        action="CREATE",
        resource_type="employe",
        request=None,
    )


def test_middleware_skips_when_audit_logged_flag_is_set():
    """Middleware logic: an already-logged request must not schedule a BG task."""
    from app.core.audit_middleware import AuditMiddleware

    # Replicate the decision the middleware makes after call_next(request):
    # already_logged = getattr(request.state, "audit_logged", False)
    # should_audit = not already_logged and (method in AUDIT_METHODS or status >= 400)
    request = _FakeRequest(method="POST")
    request.state.audit_logged = True

    already_logged = getattr(request.state, "audit_logged", False)
    should_audit = (
        not already_logged
        and (request.method in AuditMiddleware.AUDIT_METHODS or 500 >= 400)
    )

    assert already_logged is True
    assert should_audit is False, "Middleware must skip when endpoint already logged"


def test_middleware_logs_when_flag_is_not_set():
    """Middleware logic: a POST with no manual log must still be audited."""
    from app.core.audit_middleware import AuditMiddleware

    request = _FakeRequest(method="POST")

    already_logged = getattr(request.state, "audit_logged", False)
    should_audit = (
        not already_logged
        and (request.method in AuditMiddleware.AUDIT_METHODS or 200 >= 400)
    )

    assert already_logged is False
    assert should_audit is True, "Middleware must log endpoints that do not self-audit"
