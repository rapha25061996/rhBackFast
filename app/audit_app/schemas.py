"""Pydantic schemas for audit system"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class AuditLogBase(BaseModel):
    """Base schema for audit log"""
    action: str = Field(..., description="Action type")
    resource_type: str = Field(..., description="Type of resource affected")
    resource_id: Optional[str] = Field(None, description="ID of the resource")
    old_values: Optional[Dict[str, Any]] = Field(
        None, description="Values before modification"
    )
    new_values: Optional[Dict[str, Any]] = Field(
        None, description="Values after modification"
    )
    ip_address: Optional[str] = Field(None, description="Client IP address")
    user_agent: Optional[str] = Field(None, description="User agent string")
    request_method: Optional[str] = Field(None, description="HTTP method")
    request_path: Optional[str] = Field(None, description="Request path")
    response_status: Optional[int] = Field(
        None, description="HTTP response status"
    )
    execution_time: Optional[float] = Field(
        None, description="Execution time in seconds"
    )


class AuditLogResponse(AuditLogBase):
    """Response schema for audit log"""
    id: int
    user_id: Optional[int] = None
    timestamp: datetime

    # Computed fields
    is_failed_action: bool = Field(
        description="Whether the action failed"
    )
    user_display: str = Field(
        description="Formatted user display name"
    )

    model_config = ConfigDict(from_attributes=True)


class AuditLogFilter(BaseModel):
    """Filter schema for audit log queries"""
    user_id: Optional[int] = Field(None, description="Filter by user ID")
    action: Optional[str] = Field(None, description="Filter by action type")
    resource_type: Optional[str] = Field(
        None, description="Filter by resource type"
    )
    resource_id: Optional[str] = Field(
        None, description="Filter by resource ID"
    )
    date_from: Optional[datetime] = Field(
        None, description="Filter from this date"
    )
    date_to: Optional[datetime] = Field(
        None, description="Filter until this date"
    )
    ip_address: Optional[str] = Field(
        None, description="Filter by IP address"
    )
    search: Optional[str] = Field(
        None, description="Search in resource_type, action, or user"
    )
    failed_only: Optional[bool] = Field(
        False, description="Show only failed actions"
    )


class AuditLogStats(BaseModel):
    """Statistics schema for audit logs"""
    total_logs: int = Field(description="Total number of logs")
    actions_by_type: Dict[str, int] = Field(
        description="Count of logs by action type"
    )
    top_users: List[Dict[str, Any]] = Field(
        description="Top users by activity"
    )
    failed_actions: int = Field(
        description="Number of failed actions"
    )
    average_execution_time: float = Field(
        description="Average execution time in seconds"
    )
    logs_by_resource: Dict[str, int] = Field(
        description="Count of logs by resource type"
    )
    recent_activity: List[Dict[str, Any]] = Field(
        description="Recent activity summary"
    )


class PaginatedAuditLogs(BaseModel):
    """Paginated response for audit logs"""
    items: List[AuditLogResponse] = Field(description="List of audit logs")
    total: int = Field(description="Total number of logs")
    skip: int = Field(description="Number of logs skipped")
    limit: int = Field(description="Maximum number of logs returned")
    has_more: bool = Field(description="Whether there are more logs")


class AuditLogExportRequest(BaseModel):
    """Request schema for exporting audit logs"""
    format: str = Field(
        "excel",
        description="Export format (excel, csv, json)"
    )
    filters: Optional[AuditLogFilter] = Field(
        None, description="Filters to apply"
    )
    include_fields: Optional[List[str]] = Field(
        None, description="Fields to include in export"
    )


class AuditLogCreate(BaseModel):
    """Schema for creating audit log (internal use)"""
    user_id: Optional[int] = None
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    old_values: Optional[Dict[str, Any]] = None
    new_values: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    session_key: Optional[str] = None
    request_method: Optional[str] = None
    request_path: Optional[str] = None
    response_status: Optional[int] = None
    execution_time: Optional[float] = None
