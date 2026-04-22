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


# Default work schedule applied when no per-user schedule is defined.
DEFAULT_START_TIME = "08:30:00"
DEFAULT_END_TIME = "17:30:00"