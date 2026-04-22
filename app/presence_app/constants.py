"""Constants and enums for the presence/attendance module."""
from __future__ import annotations

from enum import Enum


class ScanType(str, Enum):
    """Type of a presence scan."""

    ENTRY = "ENTRY"
    EXIT = "EXIT"


class ScanMethod(str, Enum):
    """Method used by the employee to register a scan."""

    QR = "QR"
    MOBILE_BIOMETRIC = "MOBILE_BIOMETRIC"


class AbsenceType(str, Enum):
    """Reason category for an absence declaration."""

    MALADIE = "MALADIE"
    URGENCE_FAMILIALE = "URGENCE_FAMILIALE"
    DEUIL = "DEUIL"
    ENFANT_MALADE = "ENFANT_MALADE"
    RDV_MEDICAL = "RDV_MEDICAL"
    AUTRE = "AUTRE"


class LateReasonType(str, Enum):
    """Reason category for a late declaration."""

    TRANSPORT = "TRANSPORT"
    FAMILIAL = "FAMILIAL"
    MEDICAL = "MEDICAL"
    AUTRE = "AUTRE"


class DeclarationStatus(str, Enum):
    """Lifecycle status of an absence or late declaration."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


# Default work schedule applied when no per-user schedule is defined.
DEFAULT_START_TIME = "08:30:00"
DEFAULT_END_TIME = "17:30:00"