"""Service for generating OTP codes and reset tokens"""

import random
import secrets
import string
from datetime import datetime, timedelta


class OTPGenerationService:
    """Service for generating OTP codes and reset tokens"""

    @staticmethod
    def generate_otp() -> str:
        """
        Génère un code OTP de 6 chiffres

        Returns:
            str: Code OTP de 6 chiffres (ex: "123456")
        """
        return ''.join(random.choices(string.digits, k=6))

    @staticmethod
    def generate_reset_token() -> str:
        """
        Génère un token de réinitialisation sécurisé

        Returns:
            str: Token URL-safe de 32 caractères
        """
        return secrets.token_urlsafe(32)

    @staticmethod
    def calculate_expiry() -> datetime:
        """
        Calcule la date d'expiration (15 minutes à partir de maintenant)

        Returns:
            datetime: Date d'expiration (UTC)
        """
        return datetime.utcnow() + timedelta(minutes=15)
