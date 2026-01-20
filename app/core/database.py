"""
Database configuration and session management for async SQLAlchemy.

This module handles:
- Async engine creation with environment-aware pooling
- Session factory and dependency injection
- Database initialization for development
- Graceful shutdown and connection cleanup

Production deployments should use Alembic for schema management
and rely on the async session factory for all queries.

Usage in FastAPI:
    from fastapi import FastAPI, Depends
    from database import get_db_session, engine
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup
        logger.info("Starting database engine")
        yield
        # Shutdown
        await engine.dispose()
        logger.info("Database engine disposed")

    app = FastAPI(lifespan=lifespan)

    @app.get("/items")
    async def get_items(session: AsyncSession = Depends(get_db_session)):
        result = await session.execute(select(Item))
        return result.scalars().all()
"""

import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import NullPool, QueuePool

from app.core.config import settings


logger = logging.getLogger(__name__)


# ============================================================================
# ENGINE CONFIGURATION
# ============================================================================

def _build_engine_args() -> dict:
    """
    Build SQLAlchemy engine arguments based on environment configuration.

    Returns:
        Dict with engine configuration for the detected database backend.

    Raises:
        ValueError: If database backend is unsupported.
    """
    base_args = {
        "echo": settings.DB_ECHO,
        "future": True,
    }

    # PostgreSQL: Use connection pooling for concurrency
    if settings.is_postgres:
        logger.info(
            "Configuring PostgreSQL with pool_size=%d, max_overflow=%d",
            settings.DB_POOL_SIZE,
            settings.DB_MAX_OVERFLOW
        )
        base_args.update({
            "poolclass": QueuePool,
            "pool_size": settings.DB_POOL_SIZE,
            "max_overflow": settings.DB_MAX_OVERFLOW,
            "pool_timeout": settings.DB_POOL_TIMEOUT,
            "pool_recycle": settings.DB_POOL_RECYCLE,
            "pool_pre_ping": settings.DB_POOL_PRE_PING,
            "connect_args": {
                "server_settings": {
                    "application_name": settings.PROJECT_NAME,
                    "statement_timeout": f"{settings.POSTGRES_STATEMENT_TIMEOUT_MS}ms",
                },
                "timeout": settings.DB_POOL_TIMEOUT,
            },
        })

    # SQLite: Disable pooling (SQLite doesn't support multi-threaded access)
    elif settings.is_sqlite:
        logger.info("Configuring SQLite with NullPool (no connection pooling)")
        base_args.update({
            "poolclass": NullPool,
            "connect_args": {"check_same_thread": False},
        })

    else:
        raise ValueError(
            f"Unsupported database backend: {settings.DATABASE_URL}. "
            "Supported: PostgreSQL, SQLite"
        )

    return base_args


def _create_engine() -> AsyncEngine:
    """
    Create async SQLAlchemy engine with error handling.

    Returns:
        Configured AsyncEngine instance.

    Raises:
        RuntimeError: If engine creation fails.
    """
    try:
        engine_args = _build_engine_args()
        logger.debug("Creating async engine with args: %s", engine_args)

        engine = create_async_engine(
            str(settings.DATABASE_URL),
            **engine_args
        )

        logger.info(
            "Async engine created successfully: %s",
            settings.DATABASE_URL
        )
        return engine

    except Exception as e:
        logger.critical(
            "Failed to create async engine: %s",
            str(e),
            exc_info=True
        )
        raise RuntimeError(
            f"Database engine initialization failed: {str(e)}"
        ) from e


# Create singleton engine instance
engine: AsyncEngine = _create_engine()


# ============================================================================
# SESSION FACTORY
# ============================================================================

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autoflush=False,
    expire_on_commit=True,  # ORM lazy loading enabled
    future=True,
)


# ============================================================================
# DECLARATIVE BASE
# ============================================================================

Base = declarative_base()


# ============================================================================
# DEPENDENCY INJECTION
# ============================================================================

async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Async generator dependency for FastAPI route handlers.

    Provides an AsyncSession that automatically closes after the request.

    Usage in routes:
        @app.get("/items")
        async def get_items(session: AsyncSession = Depends(get_db_session)):
            result = await session.execute(select(Item))
            return result.scalars().all()

    Yields:
        AsyncSession: Database session for query execution.

    Raises:
        Exception: Database errors are propagated to caller.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            await session.rollback()
            logger.error(
                "Database session error, rolling back transaction: %s",
                str(e),
                exc_info=True
            )
            raise
        finally:
            await session.close()


# ============================================================================
# DATABASE INITIALIZATION (Development/Testing Only)
# ============================================================================

async def init_db() -> None:
    """
    Initialize database by creating all tables from declarative models.

    IMPORTANT: This is for development and testing only.
    In production, use Alembic for schema management and migrations.

    Only runs for SQLite. PostgreSQL requires Alembic migrations.

    Raises:
        RuntimeError: If initialization fails.
    """
    if not settings.is_sqlite:
        logger.warning(
            "init_db() skipped: Non-SQLite database detected. "
            "Use Alembic migrations for schema management in production."
        )
        return

    try:
        logger.info("Initializing SQLite database tables...")

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        logger.info("Database tables created successfully")

    except Exception as e:
        logger.critical(
            "Failed to initialize database: %s",
            str(e),
            exc_info=True
        )
        raise RuntimeError(
            f"Database initialization failed: {str(e)}"
        ) from e


async def drop_db() -> None:
    """
    Drop all tables from database.

    WARNING: Destructive operation. Use only in testing.

    Raises:
        RuntimeError: If operation fails.
    """
    if settings.is_production:
        raise RuntimeError(
            "Cannot drop database tables in production environment"
        )

    try:
        logger.warning("Dropping all database tables...")

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

        logger.warning("Database tables dropped")

    except Exception as e:
        logger.critical(
            "Failed to drop database tables: %s",
            str(e),
            exc_info=True
        )
        raise RuntimeError(
            f"Database drop operation failed: {str(e)}"
        ) from e


# ============================================================================
# CONNECTION HEALTH CHECK
# ============================================================================

async def verify_db_connection() -> bool:
    """
    Verify database connectivity.

    Useful for health checks and startup validation.

    Returns:
        True if connection succeeds, False otherwise.

    Usage in startup event:
        @app.on_event("startup")
        async def startup():
            if not await verify_db_connection():
                raise RuntimeError("Database connection failed")
    """
    try:
        async with AsyncSessionLocal() as session:
            await session.execute("SELECT 1")

        logger.info("Database connection verified")
        return True

    except Exception as e:
        logger.error(
            "Database connection verification failed: %s",
            str(e),
            exc_info=True
        )
        return False


async def dispose_engine() -> None:
    """
    Gracefully dispose of all database connections.

    Call during application shutdown to clean up resources.

    Usage in shutdown event:
        @app.on_event("shutdown")
        async def shutdown():
            await dispose_engine()
    """
    try:
        logger.info("Disposing database engine and closing connections...")
        await engine.dispose()
        logger.info("Database engine disposed successfully")

    except Exception as e:
        logger.error(
            "Error disposing database engine: %s",
            str(e),
            exc_info=True
        )
