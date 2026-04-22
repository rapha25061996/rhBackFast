"""Query utilities for filtering, searching, and expanding relations"""
from typing import List, Optional, Any
from sqlalchemy import Select, or_, func
from sqlalchemy.orm import selectinload


def apply_filters(query: Select, filters: dict) -> Select:
    """
    Apply filters to query dynamically

    Args:
        query: SQLAlchemy select query
        filters: Dictionary of field: value filters

    Returns:
        Modified query with filters applied
    """
    for field, value in filters.items():
        if value is not None and hasattr(query.column_descriptions[0]['entity'], field):
            model = query.column_descriptions[0]['entity']
            query = query.where(getattr(model, field) == value)

    return query


def apply_search(
    query: Select,
    model: Any,
    search_fields: List[str],
    search_term: Optional[str]
) -> Select:
    """
    Apply text search across multiple fields

    Args:
        query: SQLAlchemy select query
        model: SQLAlchemy model class
        search_fields: List of field names to search in
        search_term: Search term

    Returns:
        Modified query with search applied
    """
    if not search_term:
        return query

    search_conditions = []
    for field in search_fields:
        if hasattr(model, field):
            search_conditions.append(
                func.lower(getattr(model, field)).contains(search_term.lower())
            )

    if search_conditions:
        query = query.where(or_(*search_conditions))

    return query


def apply_ordering(query: Select, model: Any, ordering: Optional[str]) -> Select:
    """
    Apply ordering to query

    Args:
        query: SQLAlchemy select query
        model: SQLAlchemy model class
        ordering: Ordering string (e.g., '-created_at' for descending)

    Returns:
        Modified query with ordering applied
    """
    if not ordering:
        return query

    # Handle descending order (prefix with -)
    if ordering.startswith('-'):
        field_name = ordering[1:]
        descending = True
    else:
        field_name = ordering
        descending = False

    if hasattr(model, field_name):
        field = getattr(model, field_name)
        query = query.order_by(field.desc() if descending else field.asc())

    return query


def build_expand_options(model: Any, expand_fields: List[str]) -> List[Any]:
    """Build `selectinload` option chains for the given model and expand paths.

    Returns a list of SQLAlchemy loader options that can be passed directly to
    ``select(...).options(*opts)`` or ``query.options(*opts)``. Unknown paths
    are silently skipped (consistent with :func:`apply_expansion`).
    """
    options: List[Any] = []
    if not expand_fields:
        return options

    for field in expand_fields:
        if '.' not in field:
            if hasattr(model, field):
                options.append(selectinload(getattr(model, field)))
            continue
        parts = field.split('.')
        current_model = model
        loader = None
        for i, part in enumerate(parts):
            if not hasattr(current_model, part):
                loader = None
                break
            attr = getattr(current_model, part)
            loader = selectinload(attr) if i == 0 else loader.selectinload(attr)
            if hasattr(attr.property, 'mapper'):
                current_model = attr.property.mapper.class_
        if loader is not None:
            options.append(loader)
    return options


def apply_expansion(
    query: Select,
    model: Any,
    expand_fields: List[str]
) -> Select:
    """
    Apply eager loading for specified relationships

    Args:
        query: SQLAlchemy select query
        model: SQLAlchemy model class
        expand_fields: List of relationship names to expand

    Returns:
        Modified query with eager loading applied

    Examples:
        expand_fields = ['poste', 'user_account']
        expand_fields = ['poste.service', 'poste.group']
        expand_fields = ['user.employe.poste']
    """
    options = build_expand_options(model, expand_fields)
    if options:
        query = query.options(*options)
    return query


def parse_expand_param(expand: Optional[str]) -> List[str]:
    """
    Parse expand query parameter into list of fields

    Args:
        expand: Comma-separated string of fields to expand

    Returns:
        List of field names

    Example:
        'poste_id,user_account' -> ['poste_id', 'user_account']
    """
    if not expand:
        return []

    return [field.strip() for field in expand.split(',') if field.strip()]
