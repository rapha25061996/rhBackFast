"""Application configuration"""
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Application settings"""

    # Application
    APP_NAME: str = "RH Management System"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    DATABASE_URL: str = (
    "postgresql+asyncpg://neondb_owner:npg_gZ4eYlSdwr3o@ep-tiny-sound-agslibpd-pooler.c-2.eu-central-1.aws.neon.tech/rh_db?ssl=True"
)

    # Security
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS
    BACKEND_CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "https://hr-m-syst.vercel.app",

    ]

    # Permissions
    AUTO_CREATE_PERMISSIONS: bool = True

    # Security System
    # Enable/disable authentication (JWT token validation)
    # Set to False for testing/development without authentication
    AUTHENTICATION_ENABLED: bool = True

    # Enable/disable permission checks
    # Set to False for development to bypass permission requirements
    PERMISSION_CHECK_ENABLED: bool = False

    # Leave Management Configuration
    # Country used when querying the `holidays` Python library.
    CONGE_DEFAULT_COUNTRY_CODE: str = "BI"
    # Holiday names language ("fr" or "en" supported at the moment).
    CONGE_HOLIDAY_LANGUAGE: str = "fr"
    # Initialize default CONGE workflow (statuses, types, steps, actions) at startup.
    CONGE_INIT_DEFAULTS: bool = True

    # Paie Workflow Configuration
    # Initialize default PAIE workflow (statuses, steps, actions) at startup.
    PAIE_INIT_DEFAULTS: bool = True

    # Email/SMTP Configuration

    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = "sammynegalbert@gmail.com"
    SMTP_PASSWORD: str = "ofvmompziweobxsd"
    SMTP_FROM_EMAIL: str = "sammynegalbert@gmail.com"
    SMTP_TLS: bool = True
    NOTIFICATIONS_ENABLED: bool = True

    # Audit System
    AUDIT_ENABLED: bool = True  # Enable/disable audit logging
    AUDIT_RETENTION_DAYS: int = 90  # Days to keep audit logs
    AUDIT_SKIP_PATHS: list[str] = [
        "/docs",
        "/redoc",
        "/openapi.json",
        "/favicon.ico",
        "/health",
        "/metrics",
        "/static"
    ]  # Paths to skip from audit logging
    AUDIT_SENSITIVE_FIELDS: list[str] = [
        "password",
        "passwd",
        "pwd",
        "token",
        "access_token",
        "refresh_token",
        "secret",
        "secret_key",
        "api_key",
        "authorization",
        "csrf_token",
        "credit_card",
        "card_number",
        "cvv",
        "ssn",
        "social_security",
        "private_key",
        "encryption_key"
    ]  # Sensitive fields to mask in audit logs

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True
    )


# Global settings instances
settings = Settings()

def validate_configuration() -> None:
    """
    Validate configuration at startup.
    Raises ValueError if configuration is invalid.
    """
    try:

        # Additional validation for SECRET_KEY
        secret_key = settings.SECRET_KEY

        # In production (DEBUG=False), enforce strict SECRET_KEY validation
        if not settings.DEBUG:
            if not secret_key or secret_key == "your-secret-key-change-in-production":
                msg = "SECRET_KEY must be set to a secure value in production"
                raise ValueError(msg)

            if len(secret_key) < 32:
                raise ValueError("SECRET_KEY must be at least 32 characters long")
        else:
            # In development (DEBUG=True), just warn if using default key
            if secret_key == "your-secret-key-change-in-production":
                print("⚠️  Warning: Using default SECRET_KEY (OK for development)")

        print("✓ Configuration validation successful")

    except Exception as e:
        print(f"✗ Configuration validation failed: {e}")
        raise ValueError(f"Configuration validation failed: {e}") from e
