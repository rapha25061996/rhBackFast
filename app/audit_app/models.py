"""Audit models for tracking system actions"""
from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlalchemy import (
    String, Integer, Text, DateTime, Float,
    ForeignKey, CheckConstraint, Index
)
from sqlalchemy.dialects.postgresql import JSONB, INET
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.audit_app.constants import (
    ANONYMOUS_USER_DISPLAY,
    FAILED_ACTION_SUFFIX,
    AuditAction,
)
from app.core.database import Base

if TYPE_CHECKING:
    from app.user_app.models import User


class AuditLog(Base):
    """
    Audit log model for tracking all system actions.

    Captures who did what, when, where, and how for complete traceability.
    """
    __tablename__ = "audit_log"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Action information
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )

    # Values (before and after)
    old_values: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    new_values: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # User context
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("user_management_user.id", ondelete="SET NULL"),
        nullable=True
    )

    # Request context
    ip_address: Mapped[Optional[str]] = mapped_column(
        INET, nullable=True
    )
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    session_key: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True
    )
    request_method: Mapped[Optional[str]] = mapped_column(
        String(10), nullable=True
    )
    request_path: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )

    # Response context
    response_status: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    execution_time: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )

    # Timestamp
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    # Relationships
    user: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[user_id]
    )

    # Table constraints and indexes
    __table_args__ = (
        # CHECK constraint listing every valid AuditAction value.
        # The expression is built from the AuditAction enum so that the DB
        # constraint stays in sync with the Python-level source of truth.
        CheckConstraint(
            AuditAction.check_constraint_expression(),
            name="ck_audit_action"
        ),
        # Indexes for common queries
        Index('idx_audit_user_timestamp', 'user_id', 'timestamp'),
        Index('idx_audit_action_timestamp', 'action', 'timestamp'),
        Index(
            'idx_audit_resource_timestamp',
            'resource_type',
            'timestamp'
        ),
        Index('idx_audit_ip_timestamp', 'ip_address', 'timestamp'),
        Index('idx_audit_timestamp', 'timestamp'),
    )

    @property
    def is_failed_action(self) -> bool:
        """Check if the action failed"""
        return self.action.endswith(FAILED_ACTION_SUFFIX)

    @property
    def user_display(self) -> str:
        """Get formatted user display name"""
        if self.user:
            return f"{self.user.nom} {self.user.prenom} ({self.user.email})"
        return ANONYMOUS_USER_DISPLAY

    def __str__(self) -> str:
        user_str = self.user_display
        return (
            f"{user_str} - {self.action} - "
            f"{self.resource_type} - {self.timestamp}"
        )

    def __repr__(self) -> str:
        return (
            f"<AuditLog(id={self.id}, action={self.action}, "
            f"resource={self.resource_type}, user_id={self.user_id})>"
        )
