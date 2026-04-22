"""Main password reset service orchestrating the OTP process"""
import logging
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.reset_password_app.models import PasswordResetOTP
from app.reset_password_app.services.otp_generation_service import (
    OTPGenerationService
)
from app.reset_password_app.services.email_service import EmailService
from app.reset_password_app.services.otp_validation_service import (
    OTPValidationService
)
from app.user_app.models import User
from app.core.security import get_password_hash
from datetime import datetime


logger = logging.getLogger(__name__)


class PasswordResetService:
    """Service principal pour orchestrer le processus de réinitialisation"""

    def __init__(self, db: AsyncSession):
        """
        Initialize the password reset service

        Args:
            db: Async database session
        """
        self.db = db
        self.otp_gen = OTPGenerationService()
        self.email_service = EmailService()
        self.otp_validation = OTPValidationService(db)

    async def request_password_reset(self, email: str) -> Dict[str, Any]:
        """
        Étape 1: Demande de réinitialisation de mot de passe

        Args:
            email: Email de l'utilisateur

        Returns:
            Dict contenant le message de succès et l'email

        Raises:
            ValueError: Si l'utilisateur n'existe pas
            RuntimeError: Si l'envoi d'email échoue
        """
        # Rechercher l'utilisateur
        user = await self._find_user_by_email(email)
        if not user:
            raise ValueError("Aucun compte associé à cette adresse email")

        # Invalider les anciens OTP
        await self.otp_validation.invalidate_user_otps(user.id)

        # Générer un nouveau OTP
        otp_code = self.otp_gen.generate_otp()
        reset_token = self.otp_gen.generate_reset_token()
        expires_at = self.otp_gen.calculate_expiry()

        # Créer l'enregistrement
        otp_record = PasswordResetOTP(
            user_id=user.id,
            email=email,
            otp=otp_code,
            reset_token=reset_token,
            expires_at=expires_at
        )
        self.db.add(otp_record)
        await self.db.commit()
        await self.db.refresh(otp_record)

        # Envoyer l'email
        user_name = f"{user.nom} {user.prenom}".strip()
        email_sent = await self.email_service.send_otp_email(
            email, otp_code, user_name
        )

        if not email_sent:
            # Supprimer l'enregistrement si l'envoi échoue
            await self.db.delete(otp_record)
            await self.db.commit()
            raise RuntimeError("Erreur lors de l'envoi de l'email")

        logger.info(
            "OTP créé avec succès pour l'utilisateur %s",
            user.id
        )

        return {
            "message": "Code OTP envoyé avec succès",
            "email": email
        }

    async def verify_otp(self, email: str, otp: str) -> Dict[str, Any]:
        """
        Étape 2: Vérification du code OTP

        Args:
            email: Email de l'utilisateur
            otp: Code OTP à vérifier

        Returns:
            Dict contenant le message de succès et le reset_token

        Raises:
            ValueError: Si l'utilisateur n'existe pas, l'OTP est invalide
                       ou expiré
        """
        # Rechercher l'utilisateur
        user = await self._find_user_by_email(email)
        if not user:
            raise ValueError("Aucun compte associé à cette adresse email")

        # Rechercher l'OTP
        otp_record = await self.otp_validation.find_valid_otp(
            email, otp, require_verified=False
        )

        if not otp_record:
            raise ValueError("Code OTP invalide ou expiré")

        # Vérifier l'expiration
        if otp_record.is_expired():
            raise ValueError(
                "CodeOTP expiré. Veuillez demander un nouveau code."
            )

        # Marquer comme vérifié
        otp_record.is_verified = True
        otp_record.verified_at = datetime.utcnow()
        await self.db.commit()

        logger.info(
            "OTP vérifié avec succès pour l'utilisateur %s",
            user.id
        )

        return {
            "message": "Code OTP vérifié avec succès",
            "reset_token": otp_record.reset_token
        }

    async def resend_otp(self, email: str) -> Dict[str, Any]:
        """
        Renvoi d'un code OTP

        Args:
            email: Email de l'utilisateur

        Returns:
            Dict contenant le message de succès

        Raises:
            ValueError: Si l'utilisateur n'existe pas ou si la limite
                       de temps n'est pas respectée
            RuntimeError: Si l'envoi d'email échoue
        """
        # Rechercher l'utilisateur
        user = await self._find_user_by_email(email)
        if not user:
            raise ValueError("Aucun compte associé à cette adresse email")

        # Vérifier la limite de temps
        has_recent = await self.otp_validation.check_recent_otp(
            user.id, minutes=1
        )
        if has_recent:
            raise ValueError(
                "Veuillez attendre 1 minute avant de demander un nouveau code"
            )

        # Utiliser la même logique que request_password_reset
        return await self.request_password_reset(email)

    async def reset_password(
        self,
        email: str,
        otp: str,
        reset_token: str,
        new_password: str
    ) -> Dict[str, Any]:
        """
        Étape 3: Réinitialisation du mot de passe

        Args:
            email: Email de l'utilisateur
            otp: Code OTP
            reset_token: Token de réinitialisation
            new_password: Nouveau mot de passe

        Returns:
            Dict contenant le message de succès

        Raises:
            ValueError: Si l'utilisateur n'existe pas, le token est
                       invalide ou l'OTP est expiré
        """
        # Rechercher l'utilisateur
        user = await self._find_user_by_email(email)
        if not user:
            raise ValueError("Aucun compte associé à cette adresse email")

        # Rechercher l'OTP vérifié
        otp_record = await self.otp_validation.find_valid_otp(
            email, otp, require_verified=True
        )

        if not otp_record or otp_record.reset_token != reset_token:
            raise ValueError("Token de réinitialisation invalide ou expiré")

        if otp_record.is_expired():
            raise ValueError(
                "Session expirée. Veuillez recommencer le processus."
            )

        # Mettre à jour le mot de passe dans une transaction
        try:
            # Hasher le nouveau mot de passe
            user.password = get_password_hash(new_password)

            # Marquer l'OTP comme utilisé
            otp_record.is_used = True

            # Invalider tous les autres OTP
            await self.otp_validation.invalidate_user_otps(user.id)

            # Commit de la transaction
            await self.db.commit()

            logger.info(
                "Mot de passe réinitialisé avec succès pour l'utilisateur %s",
                user.id
            )

            # Notifier par email — best-effort. Le mot de passe est
            # déjà persisté à ce stade; un échec d'envoi ne doit pas
            # rollback la transaction.
            user_name = f"{user.nom} {user.prenom}".strip() or None
            try:
                await self.email_service.send_password_changed_email(
                    email=email,
                    user_name=user_name,
                )
            except Exception:
                logger.exception(
                    "Envoi de l'email de confirmation de changement de "
                    "mot de passe échoué pour %s (réinitialisation DB "
                    "déjà effectuée, on continue)",
                    email,
                )

            return {"message": "Mot de passe réinitialisé avec succès"}

        except Exception as e:
            # Rollback en cas d'erreur
            await self.db.rollback()
            logger.error(
                "Erreur lors de la réinitialisation du mot de passe: %s",
                str(e)
            )
            raise RuntimeError(
                "Une erreur est survenue lors de la réinitialisation"
            ) from e

    async def _find_user_by_email(self, email: str) -> Optional[User]:
        """
        Recherche un utilisateur par email

        Args:
            email: Email de l'utilisateur

        Returns:
            User si trouvé, None sinon
        """
        query = select(User).where(User.email == email)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
