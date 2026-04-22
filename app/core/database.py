"""Database configuration and session management"""
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker
)
from sqlalchemy.orm import DeclarativeBase
import ssl

from app.core.config import settings


# Create SSL context for asyncpg (required for Neon and other cloud databases)
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

# Create async engine with SSL configuration
#
# pool_pre_ping tests each connection with a lightweight query before
# checkout, transparently reconnecting if the remote end has closed the
# socket (typical with Neon / managed Postgres idle timeouts).
# pool_recycle proactively recycles connections older than the threshold
# so we never rely on a TCP keepalive matching the provider's idle limit.
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True,
    pool_pre_ping=True,
    pool_recycle=300,
    connect_args={
        "ssl": ssl_context,
        "server_settings": {
            "application_name": "rhBackFast"
        }
    }
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)


class Base(DeclarativeBase):
    """Base class for all models"""
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting async database session"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
