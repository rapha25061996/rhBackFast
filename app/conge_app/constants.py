"""Leave management constants and enumerations."""
from enum import Enum


class DemiJournee(str, Enum):
    """Demi-journée (matin / après-midi) pour le début ou la fin d'une demande."""
    MATIN = "matin"
    APRES_MIDI = "apres-midi"


class StatutAttribution(str, Enum):
    """Statut d'une ligne d'attribution de validation."""
    EN_ATTENTE = "en_attente"
    PRISE_EN_CHARGE = "prise_en_charge"
    TRAITEE = "traitee"


class CodeProcessus(str, Enum):
    """Codes de processus workflow supportés."""
    CONGE = "CONGE"


class CodeStatut(str, Enum):
    """Codes de statut globaux d'un processus (valeurs par défaut)."""
    EN_ATTENTE = "EN_ATTENTE"
    EN_COURS = "EN_COURS"
    VALIDE = "VALIDE"
    REJETE = "REJETE"
    ANNULE = "ANNULE"


# Langues supportées par la lib `holidays` (liste non-exhaustive, extensible).
SUPPORTED_HOLIDAY_LANGUAGES = ("fr", "en")

# Permissions applicatives du module congé (custom, non CRUD).
PERMISSIONS = {
    "conge.view": "Consulter les congés",
    "conge.create": "Créer une demande de congé",
    "conge.approve": "Valider / rejeter une demande de congé",
    "conge.manage_types": "Gérer les types de congé",
    "conge.manage_soldes": "Gérer les soldes de congé",
    "conge.manage_workflow": "Gérer le workflow (étapes, actions, statuts)",
}

# Valeurs par défaut
DEFAULT_HOLIDAY_LANGUAGE = "fr"
DEFAULT_COUNTRY_CODE = "BI"
