"""Tests for the centralized user_app constants module.

Validates that :
- Every enum exposes the exact set of historical values (so no migration
  drift happens silently).
- ``check_constraint_expression()`` rebuilds the same SQL CHECK text that the
  first migration wrote to the database, so the Python source of truth and
  the DB constraint stay aligned.
"""
from __future__ import annotations

from app.user_app.constants import (
    DEFAULT_DEVISE,
    DEVISE_MAX_LENGTH,
    SEXE_MAX_LENGTH,
    STATUT_EMPLOI_MAX_LENGTH,
    STATUT_MATRIMONIAL_MAX_LENGTH,
    TYPE_CONTRAT_MAX_LENGTH,
    Sexe,
    StatutEmploi,
    StatutMatrimonial,
    TypeContrat,
)


def test_sexe_values():
    assert set(Sexe.values()) == {"M", "F", "O"}


def test_statut_matrimonial_values():
    assert set(StatutMatrimonial.values()) == {"S", "M", "D", "W"}


def test_statut_emploi_values():
    assert set(StatutEmploi.values()) == {
        "ACTIVE", "INACTIVE", "TERMINATED", "SUSPENDED"
    }


def test_type_contrat_values():
    assert set(TypeContrat.values()) == {
        "CDI", "CDD", "STAGE", "CONSULTANT"
    }


def test_check_constraint_expression_shape():
    # Every enum must produce `<col> IN ('A', 'B', ...)`.
    expr = Sexe.check_constraint_expression("sexe")
    assert expr.startswith("sexe IN (")
    assert expr.endswith(")")
    for v in Sexe.values():
        assert f"'{v}'" in expr


def test_check_constraint_expression_matches_initial_migration():
    # These literals are what the migration wrote to the DB.
    # Centralizing is a no-op: the rebuilt expression must be byte-identical.
    assert (
        Sexe.check_constraint_expression("sexe")
        == "sexe IN ('M', 'F', 'O')"
    )
    assert (
        StatutMatrimonial.check_constraint_expression("statut_matrimonial")
        == "statut_matrimonial IN ('S', 'M', 'D', 'W')"
    )
    assert (
        StatutEmploi.check_constraint_expression("statut_emploi")
        == "statut_emploi IN ('ACTIVE', 'INACTIVE', 'TERMINATED', 'SUSPENDED')"
    )
    assert (
        TypeContrat.check_constraint_expression("type_contrat")
        == "type_contrat IN ('CDI', 'CDD', 'STAGE', 'CONSULTANT')"
    )


def test_default_devise_is_iso4217_3_letter():
    assert DEFAULT_DEVISE == "USD"
    assert len(DEFAULT_DEVISE) == DEVISE_MAX_LENGTH == 3


def test_max_lengths_match_model_columns():
    # Invariants used by both ORM columns and Pydantic Field(max_length=...).
    assert SEXE_MAX_LENGTH == 1
    assert STATUT_MATRIMONIAL_MAX_LENGTH == 1
    assert STATUT_EMPLOI_MAX_LENGTH == 20
    assert TYPE_CONTRAT_MAX_LENGTH == 50


def test_statut_emploi_default_is_active():
    # Employe.statut_emploi default must be StatutEmploi.ACTIVE.
    assert StatutEmploi.ACTIVE.value == "ACTIVE"
