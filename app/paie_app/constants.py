"""Constantes centralisées du module paie.

Tous les énumérés, taux, plafonds et constantes du workflow sont regroupés
ici pour éviter les chaînes magiques éparpillées dans le code.

Trois grandes catégories :
- **Workflow** (statuts, étapes, actions, permissions) — réutilise les tables
  génériques du module ``conge_app``.
- **Statuts texte rétro-compat** de ``PeriodePaie.statut`` (alertes, retenues,
  périodes) — pour les anciens endpoints et les enregistrements existants.
- **Paramètres de calcul** (INSS, IRE, allocations familiales).
"""
from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Dict, List

# Réutilisation du statut d'attribution partagé avec conge_app.
from app.conge_app.constants import StatutAttribution

__all__ = [
    # Attribution (re-export)
    "StatutAttribution",
    # Workflow paie
    "CodeProcessusPaie",
    "DemandeTypePaie",
    "CodeStatutPaie",
    "NomActionPaie",
    "STATUT_TEXTUEL_PAR_CODE",
    "WORKFLOW_PERMISSIONS",
    # Statut texte période
    "PeriodeStatutTexte",
    "PERIOD_STATUS",
    # Alertes
    "AlertType",
    "AlertSeverity",
    "AlertStatus",
    "ALERT_TYPES",
    "ALERT_SEVERITY",
    "ALERT_STATUS",
    "SEVERITY_COLORS",
    # Retenues
    "DeductionType",
    "DEDUCTION_TYPES",
    # Taux de calcul
    "INSS_PENSION_RATE",
    "INSS_PENSION_CAP",
    "INSS_RISK_RATE",
    "INSS_RISK_CAP",
    "INSS_EMPLOYEE_RATE",
    "INSS_EMPLOYEE_CAP",
    "IRE_BRACKETS",
    "FAMILY_ALLOWANCE_SCALE",
    "FAMILY_ALLOWANCE_ADDITIONAL",
    # Utilitaires
    "calculate_ire",
    "calculate_family_allowance",
    "calculate_inss_employer",
    "calculate_inss_employee",
    "validate_period_status_transition",
]


# ============================================================================
# Workflow paie — identifiants polymorphiques
# ============================================================================


class CodeProcessusPaie(str, Enum):
    """Code de processus workflow pour la paie (``cg_etape_processus``)."""

    PAIE = "PAIE"


class DemandeTypePaie(str, Enum):
    """Type polymorphique pour ``cg_demande_attribution`` / ``cg_historique_demande``."""

    PERIODE_PAIE = "PERIODE_PAIE"


class CodeStatutPaie(str, Enum):
    """Statuts globaux du workflow paie (``cg_statut_processus.code_statut``)."""

    EN_ATTENTE = "EN_ATTENTE"
    EN_COURS = "EN_COURS"
    VALIDE = "VALIDE"
    REJETE = "REJETE"
    ANNULE = "ANNULE"
    EN_MODIFICATION = "EN_MODIFICATION"
    PAYE = "PAYE"


class NomActionPaie(str, Enum):
    """Actions applicables sur les étapes du workflow paie."""

    APPROUVER = "APPROUVER"
    REJETER = "REJETER"
    DEMANDER_MODIF = "DEMANDER_MODIF"
    PRET_A_VALIDER = "PRET_A_VALIDER"
    MARQUER_PAYE = "MARQUER_PAYE"


# Permissions applicatives du workflow paie.
WORKFLOW_PERMISSIONS: Dict[str, str] = {
    "paie_workflow.submit": "Soumettre une période de paie au workflow",
    "paie_workflow.approve": "Valider / rejeter une étape du workflow paie",
    "paie_workflow.manage": "Gérer la configuration du workflow paie",
}


# ============================================================================
# Statut texte historique de PeriodePaie.statut
# ============================================================================


class PeriodeStatutTexte(str, Enum):
    """Statuts texte historiques de ``PeriodePaie.statut``.

    Le workflow dynamique reste l'unique source de vérité : ce champ texte est
    synchronisé automatiquement par :class:`PaieWorkflowService` lors des
    transitions. Il est conservé pour la rétro-compatibilité des anciens
    endpoints (``process``, ``finalize``, ``approve``).
    """

    DRAFT = "DRAFT"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FINALIZED = "FINALIZED"
    APPROVED = "APPROVED"
    PAID = "PAID"
    ARCHIVED = "ARCHIVED"


# Liste rétro-compatible (ancien export).
PERIOD_STATUS: List[str] = [s.value for s in PeriodeStatutTexte]


# Mapping statut workflow → statut texte rétro-compat.
STATUT_TEXTUEL_PAR_CODE: Dict[str, str] = {
    CodeStatutPaie.EN_ATTENTE.value: PeriodeStatutTexte.PROCESSING.value,
    CodeStatutPaie.EN_COURS.value: PeriodeStatutTexte.PROCESSING.value,
    CodeStatutPaie.EN_MODIFICATION.value: PeriodeStatutTexte.PROCESSING.value,
    CodeStatutPaie.VALIDE.value: PeriodeStatutTexte.APPROVED.value,
    CodeStatutPaie.REJETE.value: PeriodeStatutTexte.DRAFT.value,
    CodeStatutPaie.ANNULE.value: PeriodeStatutTexte.DRAFT.value,
    CodeStatutPaie.PAYE.value: PeriodeStatutTexte.PAID.value,
}


# Transitions autorisées pour l'ancien champ ``statut`` texte (conservé pour
# rétro-compatibilité ; la vérité fonctionnelle est désormais portée par le
# workflow dynamique).
_ALLOWED_STATUS_TRANSITIONS: Dict[str, List[str]] = {
    PeriodeStatutTexte.DRAFT.value: [PeriodeStatutTexte.PROCESSING.value],
    PeriodeStatutTexte.PROCESSING.value: [
        PeriodeStatutTexte.COMPLETED.value,
        PeriodeStatutTexte.DRAFT.value,
    ],
    PeriodeStatutTexte.COMPLETED.value: [
        PeriodeStatutTexte.FINALIZED.value,
        PeriodeStatutTexte.PROCESSING.value,
    ],
    PeriodeStatutTexte.FINALIZED.value: [
        PeriodeStatutTexte.APPROVED.value,
        PeriodeStatutTexte.COMPLETED.value,
    ],
    PeriodeStatutTexte.APPROVED.value: [PeriodeStatutTexte.PAID.value],
    PeriodeStatutTexte.PAID.value: [PeriodeStatutTexte.ARCHIVED.value],
    PeriodeStatutTexte.ARCHIVED.value: [],
}


def validate_period_status_transition(current_status: str, new_status: str) -> bool:
    """Valide qu'une transition de statut texte est autorisée."""
    return new_status in _ALLOWED_STATUS_TRANSITIONS.get(current_status, [])


# ============================================================================
# Alertes
# ============================================================================


class AlertType(str, Enum):
    """Types d'alertes système paie."""

    MISSING_CONTRACT = "MISSING_CONTRACT"
    NEGATIVE_SALARY = "NEGATIVE_SALARY"
    HIGH_DEDUCTION = "HIGH_DEDUCTION"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    CALCULATION_ERROR = "CALCULATION_ERROR"
    MISSING_DATA = "MISSING_DATA"
    OTHER = "OTHER"


class AlertSeverity(str, Enum):
    """Sévérité d'une alerte."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AlertStatus(str, Enum):
    """Statut d'une alerte."""

    ACTIVE = "ACTIVE"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"
    DISMISSED = "DISMISSED"


# Listes rétro-compatibles (anciens exports).
ALERT_TYPES: List[str] = [a.value for a in AlertType]
ALERT_SEVERITY: List[str] = [s.value for s in AlertSeverity]
ALERT_STATUS: List[str] = [s.value for s in AlertStatus]


# Couleurs HTML associées à la sévérité (utilisé par
# ``services.notification_service``).
SEVERITY_COLORS: Dict[str, str] = {
    AlertSeverity.LOW.value: "#28a745",
    AlertSeverity.MEDIUM.value: "#ffc107",
    AlertSeverity.HIGH.value: "#fd7e14",
    AlertSeverity.CRITICAL.value: "#dc3545",
}


# ============================================================================
# Retenues salariales
# ============================================================================


class DeductionType(str, Enum):
    """Types de retenues sur salaire."""

    AVANCE_SALAIRE = "AVANCE_SALAIRE"
    PRET = "PRET"
    ASSURANCE = "ASSURANCE"
    SYNDICAT = "SYNDICAT"
    AUTRE = "AUTRE"


DEDUCTION_TYPES: List[str] = [d.value for d in DeductionType]


# ============================================================================
# INSS (Institut National de Sécurité Sociale)
# ============================================================================

# Contributions patronales.
INSS_PENSION_RATE = Decimal("0.06")  # 6 % pour la pension
INSS_PENSION_CAP = Decimal("27000")  # Plafond 27 000 FC

INSS_RISK_RATE = Decimal("0.06")  # 6 % pour les risques professionnels
INSS_RISK_CAP = Decimal("2400")  # Plafond 2 400 FC

# Contribution salariale.
INSS_EMPLOYEE_RATE = Decimal("0.04")  # 4 % à la charge du salarié
INSS_EMPLOYEE_CAP = Decimal("18000")  # Plafond 18 000 FC


# ============================================================================
# IRE (Impôt sur le Revenu des Employés)
# ============================================================================

IRE_BRACKETS: List[Dict[str, Decimal]] = [
    {
        "min": Decimal("0"),
        "max": Decimal("150000"),
        "rate": Decimal("0.0"),
        "base_tax": Decimal("0"),
    },
    {
        "min": Decimal("150000"),
        "max": Decimal("300000"),
        "rate": Decimal("0.2"),
        "base_tax": Decimal("0"),
    },
    {
        "min": Decimal("300000"),
        "max": Decimal("999999999"),
        "rate": Decimal("0.3"),
        "base_tax": Decimal("30000"),  # 150 000 * 0.2
    },
]


# ============================================================================
# Allocations familiales
# ============================================================================

FAMILY_ALLOWANCE_SCALE: Dict[int, Decimal] = {
    0: Decimal("0"),
    1: Decimal("5000"),
    2: Decimal("10000"),
    3: Decimal("15000"),
}

# Montant additionnel par enfant au-delà de 3.
FAMILY_ALLOWANCE_ADDITIONAL = Decimal("3000")


# ============================================================================
# Fonctions utilitaires de calcul
# ============================================================================


def calculate_ire(base_imposable: Decimal) -> Decimal:
    """Calcule l'IRE par tranches progressives.

    Example:
        >>> calculate_ire(Decimal("100000"))
        Decimal('0')
        >>> calculate_ire(Decimal("200000"))
        Decimal('10000')
        >>> calculate_ire(Decimal("400000"))
        Decimal('60000')
    """
    if base_imposable <= Decimal("150000"):
        return Decimal("0")
    if base_imposable <= Decimal("300000"):
        return (base_imposable - Decimal("150000")) * Decimal("0.2")
    return Decimal("30000") + (base_imposable - Decimal("300000")) * Decimal("0.3")


def calculate_family_allowance(nombre_enfants: int) -> Decimal:
    """Calcule l'allocation familiale selon le barème progressif."""
    if nombre_enfants <= 0:
        return Decimal("0")

    if nombre_enfants in FAMILY_ALLOWANCE_SCALE:
        return FAMILY_ALLOWANCE_SCALE[nombre_enfants]

    base_amount = FAMILY_ALLOWANCE_SCALE[3]
    additional_children = nombre_enfants - 3
    additional_amount = FAMILY_ALLOWANCE_ADDITIONAL * additional_children
    return base_amount + additional_amount


def calculate_inss_employer(gross_salary: Decimal) -> Dict[str, Decimal]:
    """Calcule les contributions patronales INSS (pension + risques)."""
    pension = min(gross_salary * INSS_PENSION_RATE, INSS_PENSION_CAP)
    risk = min(gross_salary * INSS_RISK_RATE, INSS_RISK_CAP)
    return {
        "pension": pension,
        "risk": risk,
        "total": pension + risk,
    }


def calculate_inss_employee(gross_salary: Decimal) -> Decimal:
    """Calcule la contribution salariale INSS."""
    return min(gross_salary * INSS_EMPLOYEE_RATE, INSS_EMPLOYEE_CAP)
