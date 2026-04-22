"""Pydantic schemas for password reset OTP"""
import re
from pydantic import BaseModel, EmailStr, Field, field_validator


class ForgotPasswordRequest(BaseModel):
    """Schéma pour la demande de réinitialisation"""
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    """Réponse après demande d'OTP"""
    message: str
    email: str


class VerifyOTPRequest(BaseModel):
    """Schéma pour la vérification d'OTP"""
    email: EmailStr
    otp: str = Field(..., min_length=6, max_length=6, pattern=r'^\d{6}$')


class VerifyOTPResponse(BaseModel):
    """Réponse après vérification d'OTP"""
    message: str
    reset_token: str


class ResendOTPRequest(BaseModel):
    """Schéma pour le renvoi d'OTP"""
    email: EmailStr


class ResendOTPResponse(BaseModel):
    """Réponse après renvoi d'OTP"""
    message: str


class ResetPasswordRequest(BaseModel):
    """Schéma pour la réinitialisation du mot de passe"""
    email: EmailStr
    otp: str = Field(..., min_length=6, max_length=6, pattern=r'^\d{6}$')
    reset_token: str
    password: str = Field(..., min_length=8)

    @field_validator('password')
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """Valide la force du mot de passe"""
        if not re.search(r'[A-Za-z]', v):
            raise ValueError(
                "Le mot de passe doit contenir au moins une lettre"
            )
        if not re.search(r'\d', v):
            raise ValueError(
                "Le mot de passe doit contenir au moins un chiffre"
            )
        return v


class ResetPasswordResponse(BaseModel):
    """Réponse après réinitialisation"""
    message: str
