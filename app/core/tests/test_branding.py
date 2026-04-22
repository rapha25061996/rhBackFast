"""Tests for the centralized branding module.

Validates that the primary brand colour is applied everywhere and that the
legacy palette is no longer referenced by the templates.
"""
from __future__ import annotations

from pathlib import Path

from app.core.branding import (
    COLOR_PRIMARY,
    COMPANY_NAME,
    apply_branding,
    template_context,
)


WELCOME_TEMPLATE = (
    Path(__file__).parent.parent.parent
    / "user_app" / "templates" / "welcome_email.html"
)
OTP_TEMPLATE = (
    Path(__file__).parent.parent.parent
    / "reset_password_app" / "templates" / "otp_email.html"
)


def test_primary_is_user_requested_brand_colour():
    # The brand colour requested by the product owner.
    assert COLOR_PRIMARY == "#012624"


def test_apply_branding_replaces_every_token():
    # Every key in the context must be substituted, so the output contains
    # none of the ``{{ COLOR_* }}`` / ``{{ COMPANY_NAME }}`` placeholders.
    rendered = apply_branding(
        "<p style=\"color: {{ COLOR_PRIMARY }};\">{{ COMPANY_NAME }}</p>"
    )
    assert COLOR_PRIMARY in rendered
    assert COMPANY_NAME in rendered
    assert "{{ COLOR_" not in rendered
    assert "{{ COMPANY_NAME }}" not in rendered


def test_template_context_keys_wrap_in_jinja_syntax():
    # The service layer relies on the keys being the literal placeholder text.
    for key in template_context().keys():
        assert key.startswith("{{ ")
        assert key.endswith(" }}")


def test_welcome_template_uses_primary_and_drops_legacy_colours():
    raw = WELCOME_TEMPLATE.read_text(encoding="utf-8")
    rendered = apply_branding(raw)

    # The requested brand colour must be present in the rendered HTML.
    assert COLOR_PRIMARY.lower() in rendered.lower()

    # Legacy palette from the previous design must be gone.
    for legacy in ("#667eea", "#764ba2", "#F0FFFF", "#e8f4f8"):
        assert legacy.lower() not in rendered.lower(), (
            f"Legacy colour {legacy} still present in welcome_email.html"
        )


def test_otp_template_uses_primary_and_drops_legacy_colours():
    raw = OTP_TEMPLATE.read_text(encoding="utf-8")
    rendered = apply_branding(raw)

    assert COLOR_PRIMARY.lower() in rendered.lower()

    # Legacy green palette from the previous OTP design must be gone.
    for legacy in ("#28a745", "#f8d7da", "#dc3545"):
        assert legacy.lower() not in rendered.lower(), (
            f"Legacy colour {legacy} still present in otp_email.html"
        )


def test_payslip_pdf_generator_imports_from_branding():
    # Quick guard — make sure the PDF generator pulls colours from branding.
    from app.paie_app.services import payslip_generator

    assert payslip_generator.COLOR_PRIMARY == COLOR_PRIMARY
    assert payslip_generator.COMPANY_NAME == COMPANY_NAME
