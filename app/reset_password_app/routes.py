"""FastAPI routes for password reset OTP functionality"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.reset_password_app import schemas
from app.reset_password_app.services import PasswordResetService


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/password-reset", tags=["Password Reset"])


@router.post("/request", response_model=schemas.ForgotPasswordResponse)
async def request_password_reset(
    request: schemas.ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Demande de réinitialisation de mot de passe

    Envoie un code OTP à l'adresse email fournie si elle existe dans
    le système.

    Args:
        request: Contient l'email de l'utilisateur
        db: Session de base de données

    Returns:
        Message de confirmation et email

    Raises:
        HTTPException 400: Email invalide ou utilisateur non trouvé
        HTTPException 500: Erreur lors de l'envoi de l'email
    """
    try:
        service = PasswordResetService(db)
        result = await service.request_password_reset(request.email)
        return result
    except ValueError as e:
        logger.warning(
            "Tentative de réinitialisation avec email invalide: %s",
            request.email
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except RuntimeError as e:
        logger.exception(
            "Échec d'envoi d'email OTP pour %s",
            request.email,
        )
        # DEBUG: exception réelle exposée dans la réponse HTTP
        # ⚠️ TODO revert avant prod (leak d'info interne)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"[DEBUG] {type(e).__name__}: {e}",
        )
    except Exception as e:
        logger.exception(
            "Erreur inattendue lors de la demande de réinitialisation pour %s",
            request.email,
        )
        # DEBUG: exception réelle exposée dans la réponse HTTP
        # ⚠️ TODO revert avant prod (leak d'info interne)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"[DEBUG] {type(e).__name__}: {e}",
        )


@router.post("/verify", response_model=schemas.VerifyOTPResponse)
async def verify_otp(
    request: schemas.VerifyOTPRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Vérification du code OTP

    Vérifie que le code OTP fourni est valide et non expiré.

    Args:
        request: Contient l'email et le code OTP
        db: Session de base de données

    Returns:
        Message de confirmation et reset_token pour l'étape suivante

    Raises:
        HTTPException 400: OTP invalide, expiré ou email non trouvé
    """
    try:
        service = PasswordResetService(db)
        result = await service.verify_otp(request.email, request.otp)
        return result
    except ValueError as e:
        logger.warning(
            "Tentative de vérification OTP échouée pour %s",
            request.email
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.exception(
            "Erreur inattendue lors de la vérification OTP pour %s",
            request.email,
        )
        # DEBUG: exception réelle exposée dans la réponse HTTP
        # ⚠️ TODO revert avant prod (leak d'info interne)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"[DEBUG] {type(e).__name__}: {e}",
        )


@router.post("/resend", response_model=schemas.ResendOTPResponse)
async def resend_otp(
    request: schemas.ResendOTPRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Renvoi d'un code OTP

    Génère et envoie un nouveau code OTP si la limite de temps est
    respectée.

    Args:
        request: Contient l'email de l'utilisateur
        db: Session de base de données

    Returns:
        Message de confirmation

    Raises:
        HTTPException 400: Email invalide ou utilisateur non trouvé
        HTTPException 429: Trop de tentatives (limite de débit)
        HTTPException 500: Erreur lors de l'envoi de l'email
    """
    try:
        service = PasswordResetService(db)
        result = await service.resend_otp(request.email)
        return result
    except ValueError as e:
        error_message = str(e)
        # Vérifier si c'est une erreur de limitation de débit
        if "attendre 1 minute" in error_message.lower():
            logger.warning(
                "Limitation de débit atteinte pour %s",
                request.email
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=error_message
            )
        else:
            logger.warning(
                "Tentative de renvoi OTP avec email invalide: %s",
                request.email
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_message
            )
    except RuntimeError as e:
        logger.exception(
            "Échec de renvoi d'email OTP pour %s",
            request.email,
        )
        # DEBUG: exception réelle exposée dans la réponse HTTP
        # ⚠️ TODO revert avant prod (leak d'info interne)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"[DEBUG] {type(e).__name__}: {e}",
        )
    except Exception as e:
        logger.exception(
            "Erreur inattendue lors du renvoi OTP pour %s",
            request.email,
        )
        # DEBUG: exception réelle exposée dans la réponse HTTP
        # ⚠️ TODO revert avant prod (leak d'info interne)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"[DEBUG] {type(e).__name__}: {e}",
        )


@router.post("/reset", response_model=schemas.ResetPasswordResponse)
async def reset_password(
    request: schemas.ResetPasswordRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Réinitialisation du mot de passe

    Réinitialise le mot de passe de l'utilisateur après vérification
    de l'OTP et du token de réinitialisation.

    Args:
        request: Contient l'email, l'OTP, le reset_token et le nouveau
                 mot de passe
        db: Session de base de données

    Returns:
        Message de confirmation

    Raises:
        HTTPException 400: Token invalide, OTP expiré, mot de passe
                          invalide
        HTTPException 500: Erreur lors de la mise à jour
    """
    try:
        service = PasswordResetService(db)
        result = await service.reset_password(
            request.email,
            request.otp,
            request.reset_token,
            request.password
        )
        return result
    except ValueError as e:
        logger.warning(
            "Tentative de réinitialisation échouée pour %s",
            request.email
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except RuntimeError as e:
        logger.exception(
            "Erreur lors de la réinitialisation du mot de passe pour %s",
            request.email,
        )
        # DEBUG: exception réelle exposée dans la réponse HTTP
        # ⚠️ TODO revert avant prod (leak d'info interne)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"[DEBUG] {type(e).__name__}: {e}",
        )
    except Exception as e:
        logger.exception(
            "Erreur inattendue lors de la réinitialisation pour %s",
            request.email,
        )
        # DEBUG: exception réelle exposée dans la réponse HTTP
        # ⚠️ TODO revert avant prod (leak d'info interne)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"[DEBUG] {type(e).__name__}: {e}",
        )

