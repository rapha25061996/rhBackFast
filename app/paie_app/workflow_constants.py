"""Ré-exports du workflow paie.

.. deprecated::
    Ce module est conservé pour la rétro-compatibilité. Les constantes du
    workflow paie sont désormais définies dans :mod:`app.paie_app.constants`.
    Nouveaux imports : ``from app.paie_app.constants import ...``.
"""
from __future__ import annotations

from app.paie_app.constants import (  # noqa: F401
    STATUT_TEXTUEL_PAR_CODE,
    WORKFLOW_PERMISSIONS,
    CodeProcessusPaie,
    CodeStatutPaie,
    DemandeTypePaie,
    NomActionPaie,
)

__all__ = [
    "CodeProcessusPaie",
    "DemandeTypePaie",
    "CodeStatutPaie",
    "NomActionPaie",
    "STATUT_TEXTUEL_PAR_CODE",
    "WORKFLOW_PERMISSIONS",
]
