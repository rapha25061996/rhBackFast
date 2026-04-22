"""OTP validation service for password reset"""
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.reset_password_app.models import PasswordResetOTP


class OTPValidationService:
    """Service pour valider les OTP"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def find_valid_otp(
        self,
        email: str,
        otp: str,
        require_verified: bool = False
    ) -> Optional[PasswordResetOTP]:
        """
        Recherche un OTP valide

        Args:
            email: Email de l'utilisateur
            otp: Code OTP à rechercher
            require_verified: Si True, cherche uniquement les OTP vérifiés

        Returns:
            PasswordResetOTP si trouvé, None sinon
        """
        query = select(PasswordResetOTP).where(
            PasswordResetOTP.email == email,
            PasswordResetOTP.otp == otp,
            PasswordResetOTP.is_used.is_(False)
        )

        if require_verified:
            query = query.where(PasswordResetOTP.is_verified.is_(True))
        else:
            query = query.where(PasswordResetOTP.is_verified.is_(False))

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def invalidate_user_otps(self, user_id: int) -> None:
        """
        Invalide tous les OTP non utilisés d'un utilisateur

        Args:
            user_id: ID de l'utilisateur
        """
        await self.db.execute(
            update(PasswordResetOTP)
            .where(
                PasswordResetOTP.user_id == user_id,
                PasswordResetOTP.is_used.is_(False)
            )
            .values(is_used=True)
        )
        await self.db.commit()

    async def check_recent_otp(self, user_id: int, minutes: int = 1) -> bool:
        """
        Vérifie si un OTP récent existe

        Args:
            user_id: ID de l'utilisateur
            minutes: Nombre de minutes pour définir "récent"

        Returns:
            True si un OTP récent existe, False sinon
        """
        threshold = datetime.utcnow() - timedelta(minutes=minutes)
        query = select(PasswordResetOTP).where(
            PasswordResetOTP.user_id == user_id,
            PasswordResetOTP.created_at >= threshold
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none() is not None
