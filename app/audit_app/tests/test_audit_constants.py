"""Tests for the centralized audit constants module.

Validates that:
- Every action string emitted by AuditService / AuditMiddleware is declared
  in :class:`AuditAction`.
- The SQL CHECK constraint expression is rebuilt correctly from the enum and
  covers all historical values.
- The HTTP method map and skip-path lists are consistent with what the
  middleware actually references (no silent drift).
"""
from __future__ import annotations

from app.audit_app.constants import (
    ANONYMOUS_USER_DISPLAY,
    AUDIT_SKIP_PATH_PREFIXES,
    AUDIT_SKIP_PATHS,
    AUDITED_HTTP_METHODS,
    FAILED_ACTION_SUFFIX,
    HTTP_METHOD_TO_ACTION,
    AuditAction,
    AuditRequestState,
    AuditResourceType,
)


def test_audit_action_covers_every_historical_value():
    """Every action that has ever been written to audit_log must stay valid."""
    expected = {
        "CREATE", "UPDATE", "DELETE",
        "LOGIN", "LOGOUT", "LOGIN_FAILED",
        "VIEW", "VIEW_FAILED",
        "EXPORT", "BULK_OPERATION",
        "CREATE_FAILED", "UPDATE_FAILED", "DELETE_FAILED",
    }
    assert set(AuditAction.values()) == expected


def test_check_constraint_expression_lists_every_value():
    expr = AuditAction.check_constraint_expression()
    for value in AuditAction.values():
        assert f"'{value}'" in expr, f"{value} missing from CHECK constraint"
    assert expr.startswith("action IN (")
    assert expr.endswith(")")


def test_http_method_map_maps_to_valid_audit_actions():
    valid = set(AuditAction.values())
    for method, action in HTTP_METHOD_TO_ACTION.items():
        assert action in valid, (
            f"HTTP_METHOD_TO_ACTION[{method!r}] = {action!r} "
            "is not a valid AuditAction"
        )


def test_audited_http_methods_is_strict_subset_of_post_put_patch_delete():
    assert set(AUDITED_HTTP_METHODS).issubset(
        {"POST", "PUT", "PATCH", "DELETE"}
    )
    # GET must never be in AUDITED_HTTP_METHODS (handled by log_view instead)
    assert "GET" not in AUDITED_HTTP_METHODS


def test_skip_paths_block_infra_routes():
    # Sanity: the standard FastAPI infra routes are skipped.
    for required in ("/docs", "/redoc", "/openapi.json", "/health"):
        assert required in AUDIT_SKIP_PATHS


def test_audit_api_prefix_is_self_excluded_to_prevent_recursion():
    assert "/api/audit" in AUDIT_SKIP_PATH_PREFIXES


def test_failed_suffix_matches_every_failed_action():
    for value in AuditAction.values():
        if value.endswith(FAILED_ACTION_SUFFIX):
            # Every *_FAILED action has a non-failed base form
            base = value[: -len(FAILED_ACTION_SUFFIX)]
            assert base in AuditAction.values() or base == "VIEW" or base in {
                "LOGIN", "CREATE", "UPDATE", "DELETE"
            }


def test_audit_request_state_flag_name_is_stable():
    # The flag name is part of the public contract between AuditService and
    # AuditMiddleware — changing it without updating both ends is a bug.
    assert AuditRequestState.AUDIT_LOGGED == "audit_logged"


def test_anonymous_user_display_is_non_empty():
    assert ANONYMOUS_USER_DISPLAY and isinstance(ANONYMOUS_USER_DISPLAY, str)


def test_resource_type_enum_exposes_known_values():
    # Smoke test: the resource types emitted by existing routes are registered.
    expected = {
        "unknown", "authentication", "employe", "user_management_user",
        "alert", "retenue", "retenues", "periode_paie", "entree_paie",
        "all_periodes", "payroll", "payslip", "payslip_bulk",
    }
    declared = {member.value for member in AuditResourceType}
    missing = expected - declared
    assert not missing, f"Missing resource types in enum: {missing}"
