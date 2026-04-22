"""Centralized constants for the user_app module.

Single source of truth for every magic string describing an employee or a
contract:
- :class:`Sexe` — value of ``rh_employe.sexe`` (``'M'``, ``'F'``, ``'O'``).
- :class:`StatutMatrimonial` — value of ``rh_employe.statut_matrimonial``
  (``'S'``, ``'M'``, ``'D'``, ``'W'``).
- :class:`StatutEmploi` — value of ``rh_employe.statut_emploi``
  (``'ACTIVE'``, ``'INACTIVE'``, ``'TERMINATED'``, ``'SUSPENDED'``).
- :class:`TypeContrat` — value of ``rh_contrat.type_contrat``
  (``'CDI'``, ``'CDD'``, ``'STAGE'``, ``'CONSULTANT'``).
- :data:`DEFAULT_DEVISE` — ISO-4217 code used by default on new contracts.

Every CHECK constraint in :mod:`app.user_app.models` is rebuilt from these
enums via :meth:`_EnumCheckMixin.check_constraint_expression`, so a new value
added here automatically flows to the database — as long as the matching
Alembic migration is created.
"""
from __future__ import annotations

from enum import Enum


class _EnumCheckMixin:
    """Helpers shared by every ``str`` Enum used to build CHECK constraints."""

    @classmethod
    def values(cls) -> tuple[str, ...]:
        """Tuple of every enum value (order = declaration order)."""
        return tuple(member.value for member in cls)  # type: ignore[attr-defined]

    @classmethod
    def check_constraint_expression(cls, column: str) -> str:
        """Build ``<column> IN ('A', 'B', ...)`` from the enum values."""
        joined = ", ".join(f"'{v}'" for v in cls.values())
        return f"{column} IN ({joined})"


class Sexe(_EnumCheckMixin, str, Enum):
    """Valid values of :attr:`Employe.sexe`."""

    MASCULIN = "M"
    FEMININ = "F"
    AUTRE = "O"


class StatutMatrimonial(_EnumCheckMixin, str, Enum):
    """Valid values of :attr:`Employe.statut_matrimonial`.

    Letters follow the French convention:
    - ``S`` : Célibataire (Single)
    - ``M`` : Marié(e)
    - ``D`` : Divorcé(e)
    - ``W`` : Veuf/veuve (Widow)
    """

    CELIBATAIRE = "S"
    MARIE = "M"
    DIVORCE = "D"
    VEUF = "W"


class StatutEmploi(_EnumCheckMixin, str, Enum):
    """Valid values of :attr:`Employe.statut_emploi`."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    TERMINATED = "TERMINATED"
    SUSPENDED = "SUSPENDED"


class TypeContrat(_EnumCheckMixin, str, Enum):
    """Valid values of :attr:`Contrat.type_contrat`."""

    CDI = "CDI"
    CDD = "CDD"
    STAGE = "STAGE"
    CONSULTANT = "CONSULTANT"


# Default ISO-4217 currency code applied to a new contract when not provided.
DEFAULT_DEVISE: str = "USD"

# Max length kept in sync with the DB columns.
SEXE_MAX_LENGTH: int = 1
STATUT_MATRIMONIAL_MAX_LENGTH: int = 1
STATUT_EMPLOI_MAX_LENGTH: int = 20
TYPE_CONTRAT_MAX_LENGTH: int = 50
DEVISE_MAX_LENGTH: int = 3


__all__ = [
    "Sexe",
    "StatutMatrimonial",
    "StatutEmploi",
    "TypeContrat",
    "DEFAULT_DEVISE",
    "SEXE_MAX_LENGTH",
    "STATUT_MATRIMONIAL_MAX_LENGTH",
    "STATUT_EMPLOI_MAX_LENGTH",
    "TYPE_CONTRAT_MAX_LENGTH",
    "DEVISE_MAX_LENGTH",
]
