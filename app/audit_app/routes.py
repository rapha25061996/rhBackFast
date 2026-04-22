"""API routes for audit log management"""
from typing import Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.permissions import require_permission
from app.core.query_utils import apply_expansion, parse_expand_param
from app.user_app.models import User
from app.audit_app.models import AuditLog
from app.audit_app.schemas import (
    AuditLogResponse,
    PaginatedAuditLogs,
    AuditLogStats
)

router = APIRouter(prefix="/audit-logs", tags=["Audit"])


@router.get("", response_model=PaginatedAuditLogs)
async def list_audit_logs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("audit", "view")),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    user_id: Optional[int] = Query(None),
    action: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    resource_id: Optional[str] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    search: Optional[str] = Query(None),
    failed_only: bool = Query(False),
    expand: Optional[str] = Query(None, description="Relations supplémentaires (user)"),
):
    """
    List audit logs with filtering and pagination.

    Filters:
    - user_id: Filter by user ID
    - action: Filter by action type (CREATE, UPDATE, DELETE, etc.)
    - resource_type: Filter by resource type
    - resource_id: Filter by resource ID
    - start_date: Filter by start date
    - end_date: Filter by end date
    - search: Search in request_path and user_agent
    - failed_only: Show only failed actions (status >= 400)

    Requires permission: audit.view
    """
    # Build query (user is always eager-loaded for display)
    query = select(AuditLog).options(selectinload(AuditLog.user))
    if expand:
        query = apply_expansion(query, AuditLog, parse_expand_param(expand))

    # Apply filters
    filters = []

    if user_id:
        filters.append(AuditLog.user_id == user_id)

    if action:
        filters.append(AuditLog.action == action)

    if resource_type:
        filters.append(AuditLog.resource_type == resource_type)

    if resource_id:
        filters.append(AuditLog.resource_id == resource_id)

    if start_date:
        filters.append(AuditLog.timestamp >= start_date)

    if end_date:
        filters.append(AuditLog.timestamp <= end_date)

    if search:
        search_filter = or_(
            AuditLog.request_path.ilike(f"%{search}%"),
            AuditLog.user_agent.ilike(f"%{search}%")
        )
        filters.append(search_filter)

    if failed_only:
        filters.append(AuditLog.response_status >= 400)

    if filters:
        query = query.where(and_(*filters))

    # Get total count
    count_query = select(func.count()).select_from(AuditLog)
    if filters:
        count_query = count_query.where(and_(*filters))
    result = await db.execute(count_query)
    total = result.scalar()

    # Apply sorting and pagination
    query = query.order_by(AuditLog.timestamp.desc())
    query = query.offset(skip).limit(limit)

    # Execute query
    result = await db.execute(query)
    logs = result.scalars().all()

    return PaginatedAuditLogs(
        items=[AuditLogResponse.model_validate(log) for log in logs],
        total=total,
        skip=skip,
        limit=limit
    )


@router.get("/stats", response_model=AuditLogStats)
async def get_audit_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("audit", "view")),
    days: int = Query(7, ge=1, le=90)
):
    """
    Get audit statistics.

    Returns:
    - Total logs count
    - Actions by type
    - Top users
    - Failed actions count
    - Average execution time

    Requires permission: audit.view
    """
    # Calculate date range
    start_date = datetime.utcnow() - timedelta(days=days)

    # Total logs
    total_query = select(func.count()).select_from(AuditLog).where(
        AuditLog.timestamp >= start_date
    )
    result = await db.execute(total_query)
    total_logs = result.scalar()

    # Actions by type
    actions_query = select(
        AuditLog.action,
        func.count(AuditLog.id).label("count")
    ).where(
        AuditLog.timestamp >= start_date
    ).group_by(AuditLog.action)

    result = await db.execute(actions_query)
    actions_by_type = {row[0]: row[1] for row in result.all()}

    # Top users
    users_query = select(
        AuditLog.user_id,
        func.count(AuditLog.id).label("count")
    ).where(
        and_(
            AuditLog.timestamp >= start_date,
            AuditLog.user_id.isnot(None)
        )
    ).group_by(AuditLog.user_id).order_by(func.count(AuditLog.id).desc()).limit(10)

    result = await db.execute(users_query)
    top_users = {str(row[0]): row[1] for row in result.all()}

    # Failed actions
    failed_query = select(func.count()).select_from(AuditLog).where(
        and_(
            AuditLog.timestamp >= start_date,
            AuditLog.response_status >= 400
        )
    )
    result = await db.execute(failed_query)
    failed_actions = result.scalar()

    # Average execution time
    avg_time_query = select(func.avg(AuditLog.execution_time)).where(
        and_(
            AuditLog.timestamp >= start_date,
            AuditLog.execution_time.isnot(None)
        )
    )
    result = await db.execute(avg_time_query)
    avg_execution_time = result.scalar() or 0.0

    return AuditLogStats(
        total_logs=total_logs,
        actions_by_type=actions_by_type,
        top_users=top_users,
        failed_actions=failed_actions,
        avg_execution_time=float(avg_execution_time),
        period_days=days
    )


@router.get("/users/{user_id}", response_model=PaginatedAuditLogs)
async def get_user_audit_logs(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("audit", "view")),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    expand: Optional[str] = Query(None, description="Relations supplémentaires (user)"),
):
    """
    Get audit logs for a specific user.

    Requires permission: audit.view
    """
    # Build query
    query = select(AuditLog).options(selectinload(AuditLog.user)).where(
        AuditLog.user_id == user_id
    )
    if expand:
        query = apply_expansion(query, AuditLog, parse_expand_param(expand))

    # Get total count
    count_query = select(func.count()).select_from(AuditLog).where(
        AuditLog.user_id == user_id
    )
    result = await db.execute(count_query)
    total = result.scalar()

    # Apply sorting and pagination
    query = query.order_by(AuditLog.timestamp.desc())
    query = query.offset(skip).limit(limit)

    # Execute query
    result = await db.execute(query)
    logs = result.scalars().all()

    return PaginatedAuditLogs(
        items=[AuditLogResponse.model_validate(log) for log in logs],
        total=total,
        skip=skip,
        limit=limit
    )


@router.get("/resources/{resource_type}", response_model=PaginatedAuditLogs)
async def get_resource_audit_logs(
    resource_type: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("audit", "view")),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    expand: Optional[str] = Query(None, description="Relations supplémentaires (user)"),
):
    """
    Get audit logs for a specific resource type.

    Requires permission: audit.view
    """
    # Build query
    query = select(AuditLog).options(selectinload(AuditLog.user)).where(
        AuditLog.resource_type == resource_type
    )
    if expand:
        query = apply_expansion(query, AuditLog, parse_expand_param(expand))

    # Get total count
    count_query = select(func.count()).select_from(AuditLog).where(
        AuditLog.resource_type == resource_type
    )
    result = await db.execute(count_query)
    total = result.scalar()

    # Apply sorting and pagination
    query = query.order_by(AuditLog.timestamp.desc())
    query = query.offset(skip).limit(limit)

    # Execute query
    result = await db.execute(query)
    logs = result.scalars().all()

    return PaginatedAuditLogs(
        items=[AuditLogResponse.model_validate(log) for log in logs],
        total=total,
        skip=skip,
        limit=limit
    )


@router.get("/{log_id}", response_model=AuditLogResponse)
async def get_audit_log(
    log_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("audit", "view")),
    expand: Optional[str] = Query(None, description="Relations supplémentaires (user)"),
):
    """
    Get a specific audit log by ID.

    Requires permission: audit.view
    """
    query = select(AuditLog).options(selectinload(AuditLog.user)).where(
        AuditLog.id == log_id
    )
    if expand:
        query = apply_expansion(query, AuditLog, parse_expand_param(expand))
    result = await db.execute(query)
    log = result.scalar_one_or_none()

    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audit log not found"
        )

    return AuditLogResponse.model_validate(log)
