"""Security utilities for authentication and authorization"""
from datetime import datetime, timedelta
from typing import Any, Optional
from jose import jwt, JWTError
import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings


security = HTTPBearer()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash"""
    return bcrypt.checkpw(
        plain_password.encode('utf-8'),
        hashed_password.encode('utf-8')
    )


def get_password_hash(password: str) -> str:
    """Hash a password"""
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    return hashed.decode('utf-8')


def create_access_token(user_id: int, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token"""
    to_encode = {"user_id": user_id, "type": "access"}

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def create_refresh_token(user_id: int) -> str:
    """Create JWT refresh token"""
    to_encode = {"user_id": user_id, "type": "refresh"}
    expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def verify_token(token: str, token_type: str = "access") -> dict[str, Any]:
    """Verify and decode JWT token"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])

        if payload.get("type") != token_type:
            raise ValueError(f"Token invalide: type attendu '{token_type}'")

        return payload
    except JWTError as e:
        raise ValueError(f"Token invalide ou expiré: {str(e)}")


def decode_token(token: str) -> dict[str, Any]:
    """Decode and verify JWT token"""
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(lambda: None)  # Will be overridden
):
    """
    Dependency to get current authenticated user from JWT token
    
    Respects configuration settings:
    - If AUTHENTICATION_ENABLED=False: Returns mock superuser without checking token
    - If AUTHENTICATION_ENABLED=True: Validates token and returns authenticated user

    Usage:
        @router.get("/protected")
        async def protected_route(
            current_user: User = Depends(get_current_user),
            db: AsyncSession = Depends(get_db)
        ):
            return {"user_id": current_user.id}
    """
    from app.user_app.models import User
    from app.core.database import get_db
    from app.core.config import settings

    # If authentication is disabled, return mock superuser
    if not settings.AUTHENTICATION_ENABLED:
        mock_user = User(
            id=0,
            email="system@localhost",
            nom="System",
            prenom="User",
            is_active=True,
            is_superuser=True
        )
        return mock_user

    # Get database session
    async for session in get_db():
        db = session
        break

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        token = credentials.credentials
        payload = verify_token(token, "access")
        user_id: int = payload.get("user_id")

        if user_id is None:
            raise credentials_exception

    except ValueError:
        raise credentials_exception

    # Get user from database
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled"
        )

    return user

