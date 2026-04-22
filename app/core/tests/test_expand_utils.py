"""Unit tests for the generic expand helpers in ``app.core.query_utils``.

These tests don't hit the DB — they only verify the parser and loader-option
builder behave as expected. Used across all modules that accept ``?expand=``.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Load

from app.conge_app.models import DemandeConge
from app.core.query_utils import (
    apply_expansion,
    build_expand_options,
    parse_expand_param,
)
from app.paie_app.models import Alert


def test_parse_expand_param_empty() -> None:
    assert parse_expand_param(None) == []
    assert parse_expand_param("") == []
    assert parse_expand_param("   ") == []


def test_parse_expand_param_list() -> None:
    assert parse_expand_param("a,b,c") == ["a", "b", "c"]
    assert parse_expand_param(" a , b , c ") == ["a", "b", "c"]
    assert parse_expand_param("a,,b") == ["a", "b"]


def test_build_expand_options_skips_unknown() -> None:
    opts = build_expand_options(Alert, ["definitely_not_a_relation"])
    assert opts == []


def test_build_expand_options_simple() -> None:
    opts = build_expand_options(DemandeConge, ["type_conge"])
    assert len(opts) == 1
    assert isinstance(opts[0], Load)


def test_build_expand_options_mixed_known_unknown() -> None:
    opts = build_expand_options(DemandeConge, ["type_conge", "__nope__"])
    assert len(opts) == 1


def test_apply_expansion_no_fields_returns_query() -> None:
    original = select(DemandeConge)
    result = apply_expansion(original, DemandeConge, [])
    assert result is original


def test_apply_expansion_adds_options() -> None:
    stmt = apply_expansion(select(DemandeConge), DemandeConge, ["type_conge"])
    # selectinload is post-load, the primary SQL shouldn't change — we only
    # verify the loader options list is populated.
    assert len(list(stmt._with_options)) == 1  # type: ignore[attr-defined]
