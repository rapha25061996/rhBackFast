"""Centralized branding for every user-facing document and email.

This module is the **single source of truth** for the visual identity of the
application — every colour, label and asset used by:

- HTML email templates (welcome, OTP, notifications, ...).
- PDF documents (payslips, exports, ...).
- Any future generated document.

When the brand palette changes, update this file only — templates and
generators pull their values from here.

The primary colour is a deep teal ``#012624`` (the brand colour). All the
other tokens are derived around it so the palette is internally consistent.
"""
from __future__ import annotations

from typing import Dict

from app.core.config import settings


# --------------------------------------------------------------------------- #
# Palette (hex)                                                               #
# --------------------------------------------------------------------------- #
#: Primary brand colour — deep teal.
COLOR_PRIMARY: str = "#012624"
#: Darker shade of the primary — used for deep footers and borders.
COLOR_PRIMARY_DARK: str = "#001816"
#: Slightly lighter shade — used for hovers and secondary headers.
COLOR_PRIMARY_600: str = "#023C38"
#: Light shade — used for the gradient's bright end on headers.
COLOR_PRIMARY_500: str = "#024B46"
#: Very light tint — used as surface / card background.
COLOR_PRIMARY_SURFACE: str = "#E8F2F0"
#: Foreground colour guaranteed to be readable on ``COLOR_PRIMARY``.
COLOR_ON_PRIMARY: str = "#FFFFFF"

#: Warm accent to highlight key numbers / CTAs without stealing focus.
COLOR_ACCENT: str = "#C9A248"

#: Page / email background.
COLOR_BG_PAGE: str = "#F5F7F7"
#: Card background when nested in a coloured page.
COLOR_BG_CARD: str = "#FFFFFF"
#: Main body text.
COLOR_TEXT_BODY: str = "#102624"
#: Muted / secondary text.
COLOR_TEXT_MUTED: str = "#5A6968"
#: Subtle divider lines.
COLOR_BORDER: str = "#D8DFDE"

#: Semantic — success (validated, paid, ...).
COLOR_SUCCESS: str = "#15803D"
#: Semantic — warning banner (expiry, reminder, ...).
COLOR_WARNING: str = "#B45309"
#: Semantic — warning banner surface.
COLOR_WARNING_SURFACE: str = "#FEF3C7"
#: Semantic — warning banner text colour.
COLOR_WARNING_TEXT: str = "#78350F"
#: Semantic — danger (rejection, critical alert, ...).
COLOR_DANGER: str = "#B91C1C"
#: Semantic — danger banner surface.
COLOR_DANGER_SURFACE: str = "#FEE2E2"
#: Semantic — danger banner text colour.
COLOR_DANGER_TEXT: str = "#7F1D1D"


# --------------------------------------------------------------------------- #
# Identity                                                                    #
# --------------------------------------------------------------------------- #
#: Display name — pulled from the application configuration so that renaming
#: the app in :mod:`app.core.config` automatically flows into every document.
COMPANY_NAME: str = settings.APP_NAME
#: Footer copyright line (year kept static intentionally — easy to find and
#: review during annual audits).
COPYRIGHT_LINE: str = f"© 2024 {COMPANY_NAME}. Tous droits réservés."


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #
def template_context() -> Dict[str, str]:
    """Return every branding token as ``{{ TOKEN_NAME }}`` → value.

    Used by the email services to substitute branding placeholders in the
    HTML templates — one dictionary, one pass of ``str.replace``.
    """
    return {
        "{{ COLOR_PRIMARY }}": COLOR_PRIMARY,
        "{{ COLOR_PRIMARY_DARK }}": COLOR_PRIMARY_DARK,
        "{{ COLOR_PRIMARY_600 }}": COLOR_PRIMARY_600,
        "{{ COLOR_PRIMARY_500 }}": COLOR_PRIMARY_500,
        "{{ COLOR_PRIMARY_SURFACE }}": COLOR_PRIMARY_SURFACE,
        "{{ COLOR_ON_PRIMARY }}": COLOR_ON_PRIMARY,
        "{{ COLOR_ACCENT }}": COLOR_ACCENT,
        "{{ COLOR_BG_PAGE }}": COLOR_BG_PAGE,
        "{{ COLOR_BG_CARD }}": COLOR_BG_CARD,
        "{{ COLOR_TEXT_BODY }}": COLOR_TEXT_BODY,
        "{{ COLOR_TEXT_MUTED }}": COLOR_TEXT_MUTED,
        "{{ COLOR_BORDER }}": COLOR_BORDER,
        "{{ COLOR_SUCCESS }}": COLOR_SUCCESS,
        "{{ COLOR_WARNING }}": COLOR_WARNING,
        "{{ COLOR_WARNING_SURFACE }}": COLOR_WARNING_SURFACE,
        "{{ COLOR_WARNING_TEXT }}": COLOR_WARNING_TEXT,
        "{{ COLOR_DANGER }}": COLOR_DANGER,
        "{{ COLOR_DANGER_SURFACE }}": COLOR_DANGER_SURFACE,
        "{{ COLOR_DANGER_TEXT }}": COLOR_DANGER_TEXT,
        "{{ COMPANY_NAME }}": COMPANY_NAME,
        "{{ COPYRIGHT_LINE }}": COPYRIGHT_LINE,
    }


def apply_branding(template: str) -> str:
    """Apply every branding token to ``template`` (an HTML email template).

    The substitution is a simple ``str.replace`` loop — no shell injection,
    no template engine overhead — consistent with the existing rendering
    pattern of ``{{ user_name }}`` / ``{{ otp_code }}`` placeholders.
    """
    for token, value in template_context().items():
        template = template.replace(token, value)
    return template


__all__ = [
    "COLOR_PRIMARY",
    "COLOR_PRIMARY_DARK",
    "COLOR_PRIMARY_600",
    "COLOR_PRIMARY_500",
    "COLOR_PRIMARY_SURFACE",
    "COLOR_ON_PRIMARY",
    "COLOR_ACCENT",
    "COLOR_BG_PAGE",
    "COLOR_BG_CARD",
    "COLOR_TEXT_BODY",
    "COLOR_TEXT_MUTED",
    "COLOR_BORDER",
    "COLOR_SUCCESS",
    "COLOR_WARNING",
    "COLOR_WARNING_SURFACE",
    "COLOR_WARNING_TEXT",
    "COLOR_DANGER",
    "COLOR_DANGER_SURFACE",
    "COLOR_DANGER_TEXT",
    "COMPANY_NAME",
    "COPYRIGHT_LINE",
    "template_context",
    "apply_branding",
]
