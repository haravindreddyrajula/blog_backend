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
import asyncio
import logging
import time

from sqlalchemy import event, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool, QueuePool

from app.core.config import settings

logger = logging.getLogger(__name__)

# Threshold for flagging slow queries. Add DB_SLOW_QUERY_THRESHOLD_MS to
# app/core/config.py Settings to make this configurable per environment;
# falls back to 500ms if not defined.
SLOW_QUERY_THRESHOLD_MS = getattr(settings, "DB_SLOW_QUERY_THRESHOLD_MS", 500)

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

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    autoflush=False, # Explicit flush for control
    expire_on_commit=False, # Keep objects after commit
)


# ============================================================================
# DECLARATIVE BASE
# ============================================================================

Base = declarative_base()

# ============================================================================
# POOL OBSERVABILITY
# ============================================================================

@event.listens_for(engine.sync_engine, "checkout")
def _on_pool_checkout(dbapi_connection, connection_record, connection_proxy) -> None:
    """
    Log every time a connection is checked out of the pool.

    Fires on the underlying sync engine (event hooks aren't natively async-aware
    in SQLAlchemy, so this must attach to `engine.sync_engine`, not `engine`).
    Useful for spotting pool exhaustion before it causes request timeouts.

    Args:
        dbapi_connection: Raw DBAPI connection being checked out.
        connection_record: SQLAlchemy pool bookkeeping record for the connection.
        connection_proxy: Proxy wrapping the checked-out connection.
    """
    pool = engine.sync_engine.pool
    logger.debug(
        "DB connection checked out",
        extra={
            "checked_out": getattr(pool, "checkedout", lambda: None)(),
            "checked_in": getattr(pool, "checkedin", lambda: None)(),
            "overflow": getattr(pool, "overflow", lambda: None)(),
        },
    )


@event.listens_for(engine.sync_engine, "checkin")
def _on_pool_checkin(dbapi_connection, connection_record) -> None:
    """
    Log every time a connection is returned to the pool.

    Args:
        dbapi_connection: Raw DBAPI connection being returned.
        connection_record: SQLAlchemy pool bookkeeping record for the connection.
    """
    logger.debug("DB connection checked in", extra={"pool_class": type(engine.sync_engine.pool).__name__})


def get_pool_status() -> dict:
    """
    Snapshot the current connection pool state.

    For QueuePool (PostgreSQL), returns live counts of in-use vs. available
    connections. For NullPool (SQLite), pool metrics aren't meaningful since
    connections aren't reused, so a simplified status is returned instead.

    Returns:
        Dict describing the pool class and, where applicable, size/checked_in/
        checked_out/overflow/max_overflow counts. Intended for the /health/db
        route and for ad-hoc debugging of connection exhaustion.
    """
    pool = engine.pool

    if isinstance(pool, QueuePool):
        return {
            "pool_class": "QueuePool",
            "pool_size": pool.size(),
            "checked_in": pool.checkedin(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
            "max_overflow": settings.DB_MAX_OVERFLOW,
        }

    return {
        "pool_class": type(pool).__name__,
        "note": "Detailed pool metrics not applicable for this pool class",
    }


# ============================================================================
# SLOW QUERY LOGGING
# ============================================================================

@event.listens_for(engine.sync_engine, "before_cursor_execute")
def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany) -> None:
    """
    Stamp the query start time on the execution context.

    Args:
        conn: Raw DBAPI connection executing the statement.
        cursor: DBAPI cursor executing the statement.
        statement: SQL text about to run.
        parameters: Bound parameters for the statement.
        context: SQLAlchemy execution context (used to stash the start time).
        executemany: True if this is a batch (executemany) call.
    """
    context._query_start_time = time.perf_counter()


@event.listens_for(engine.sync_engine, "after_cursor_execute")
def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany) -> None:
    """
    Compute query duration and log a warning if it exceeds the slow-query threshold.

    Truncates the logged statement to 500 chars to avoid flooding logs with
    huge bulk-insert statements.

    Args:
        conn: Raw DBAPI connection that executed the statement.
        cursor: DBAPI cursor that executed the statement.
        statement: SQL text that ran.
        parameters: Bound parameters used.
        context: SQLAlchemy execution context holding the start timestamp.
        executemany: True if this was a batch (executemany) call.
    """
    duration_ms = (time.perf_counter() - context._query_start_time) * 1000

    if duration_ms >= SLOW_QUERY_THRESHOLD_MS:
        logger.warning(
            "Slow query detected",
            extra={
                "duration_ms": round(duration_ms, 2),
                "threshold_ms": SLOW_QUERY_THRESHOLD_MS,
                "statement": statement[:500],
                "executemany": executemany,
            },
        )


# ============================================================================
# CONNECTION HEALTH CHECKS
# ============================================================================

async def check_database_connection(
    max_attempts: int = 5,
    initial_delay_seconds: float = 1.0,
    backoff_multiplier: float = 2.0,
) -> None:
    """
    Verify database connectivity on startup, retrying with exponential backoff.

    Intended for use in `main.py`'s `lifespan` startup phase. Transient
    unavailability (RDS failover, ECS task starting before the DB security
    group is ready, etc.) is common on deploy — this prevents a container
    crash loop by giving the DB a few seconds to become reachable instead of
    failing on the very first attempt.

    Args:
        max_attempts: Total number of attempts before giving up.
        initial_delay_seconds: Delay before the first retry.
        backoff_multiplier: Multiplier applied to the delay after each failed attempt.

    Raises:
        RuntimeError: If the database is still unreachable after `max_attempts`.
    """
    attempt = 1
    delay = initial_delay_seconds

    while True:
        try:
            async with engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            logger.info("Database connection verified", extra={"attempt": attempt})
            return

        except SQLAlchemyError as e:
            if attempt >= max_attempts:
                logger.critical(
                    "Database connection failed after all retry attempts",
                    exc_info=True,
                    extra={"attempts": attempt, "max_attempts": max_attempts},
                )
                raise RuntimeError(
                    f"Database unreachable after {attempt} attempts. "
                    "Check DATABASE_URL and network/security group configuration."
                ) from e

            logger.warning(
                "Database connection attempt failed, retrying",
                extra={
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "retry_in_seconds": delay,
                },
            )
            await asyncio.sleep(delay)
            attempt += 1
            delay *= backoff_multiplier


async def is_database_healthy() -> bool:
    """
    Single-attempt, non-raising connectivity check for the /health/db route.

    Unlike `check_database_connection`, this never retries and never raises —
    a health endpoint must respond fast and let the caller (load balancer,
    uptime monitor) decide how to react to a False result.

    Returns:
        True if a SELECT 1 succeeds, False otherwise.
    """
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        logger.exception("Database health check failed")
        return False


async def dispose_engine(timeout_seconds: float = 30.0) -> None:
    """
    Gracefully dispose of the engine's connection pool on shutdown.

    Wraps `engine.dispose()` in a timeout so a stuck connection can't hang
    the shutdown sequence indefinitely (important for ECS task stop timeouts).

    Args:
        timeout_seconds: Max time to wait for graceful disposal before forcing it.
    """
    try:
        await asyncio.wait_for(engine.dispose(), timeout=timeout_seconds)
        logger.info("Database engine disposed successfully")
    except asyncio.TimeoutError:
        logger.warning(
            "Database engine disposal timed out, forcing closure",
            extra={"timeout_seconds": timeout_seconds},
        )
        await engine.dispose()
    except Exception:
        logger.exception("Unexpected error during database engine disposal")


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
