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
