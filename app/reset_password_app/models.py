"""Password reset OTP models"""
from datetime import datetime, timedelta
from typing import Optional, TYPE_CHECKING
import secrets
from sqlalchemy import (
    String, Integer, Boolean, DateTime,
    ForeignKey
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

if TYPE_CHECKING:
    pass


class PasswordResetOTP(Base):
    """Modèle pour stocker les OTP de réinitialisation de mot de passe"""
    __tablename__ = "password_reset_otp"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user_management_user.id", ondelete="CASCADE")
    )
    email: Mapped[str] = mapped_column(String(255), index=True)
    otp: Mapped[str] = mapped_column(String(6))
    reset_token: Mapped[str] = mapped_column(
        String(100), unique=True, index=True
    )
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime)

    # Relationship removed to avoid circular import issues
    # Can be added later if needed with proper lazy loading

    def __init__(self, **kwargs):
        """Initialize with automatictoken and expiry generation"""
        # Generate reset_token if not provided
        if 'reset_token' not in kwargs or kwargs['reset_token'] is None:
            kwargs['reset_token'] = secrets.token_urlsafe(32)

        # Calculate expires_at if not provided
        if 'expires_at' not in kwargs or kwargs['expires_at'] is None:
            kwargs['expires_at'] = (
                datetime.utcnow() + timedelta(minutes=15)
            )

        super().__init__(**kwargs)

    def is_expired(self) -> bool:
        """Vérifie si l'OTP est expiré"""
        return datetime.utcnow() > self.expires_at
