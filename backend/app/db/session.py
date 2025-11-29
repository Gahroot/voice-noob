"""Database session management with async SQLAlchemy."""

import logging
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

logger = logging.getLogger(__name__)

# Create async engine
engine = create_async_engine(
    str(settings.DATABASE_URL),
    echo=False,  # Disable SQL query logging (too verbose even in debug mode)
    future=True,
    pool_pre_ping=True,
    pool_size=20,  # Production: increased from 10 for concurrent voice agents
    max_overflow=30,  # Production: increased from 20 (total max: 50 connections)
    pool_recycle=1800,  # Recycle every 30 min (faster than 1h for better connection health)
    pool_timeout=30,  # Timeout for getting connection from pool
    pool_use_lifo=True,  # Use LIFO for better connection reuse (keeps hot connections)
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting async database sessions."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("Database session error")
            raise
        finally:
            await session.close()
