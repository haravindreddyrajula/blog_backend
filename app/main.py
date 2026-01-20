"""
Production-Ready FastAPI Application Entry Point

A secure, well-architected FastAPI application with:
- Proper async context management (lifespan events)
- Validated startup/shutdown procedures
- Security-first configuration (docs disabled in prod, CORS restricted)
- Comprehensive error handling and logging
- Database connection verification on startup
- Upload directory validation with permissions checking
- Static files serving with configurable paths
- Request/response middleware stack
- Production-grade dependency injection
- Graceful shutdown with cleanup

Author: Production Code Review Team
Status: Production-Ready
Last Updated: 2025-01-17
Assumptions:
  - FastAPI 0.100+
  - SQLAlchemy 2.0+ with async support
  - Python 3.10+
  - Environment variables: DATABASE_URL, SECRET_KEY, ENVIRONMENT
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import Base, engine
from app.core.deps import get_async_db
from app.routes import auth, blog, comment
from app.services import image
from app.services.logging_config import setup_logging

# ============================================================================
# CONFIGURATION & SETUP
# ============================================================================

# Configure logging first (before any logger usage)
setup_logging()
logger = logging.getLogger(__name__)

# Production security hardening: Force-disable risky settings
if settings.is_production:
    logger.info("Production mode detected - enforcing security constraints")
    settings.DB_ECHO = False
    settings.DOCS_ENABLED = False
    settings.RELOAD = False
    settings.DEBUG = False

# Validate debug mode (will raise if DEBUG=True in production)
#settings.validate_debug_mode()

# Constants
STARTUP_TIMEOUT = 30.0
SHUTDOWN_TIMEOUT = 30.0
MIN_UPLOAD_DIR_PERMISSIONS = 0o755


# ============================================================================
# STARTUP & SHUTDOWN HELPERS
# ============================================================================


async def _verify_upload_directory() -> None:
    """
    Verify upload directory exists and is writable.

    Creates directory with proper permissions, then validates write access
    by attempting to create and delete a test file. Fails fast if permissions
    are wrong, preventing silent failures in production.

    Raises:
        RuntimeError: If directory cannot be created or is not writable
        PermissionError: If insufficient permissions to write to directory
    """
    upload_path = Path(settings.static_uploads_dir)

    try:
        # Create directory with proper permissions
        upload_path.mkdir(parents=True, exist_ok=True, mode=MIN_UPLOAD_DIR_PERMISSIONS)
        logger.info(
            "Upload directory created or verified",
            extra={"path": str(upload_path), "permissions": oct(MIN_UPLOAD_DIR_PERMISSIONS)},
        )

        # Verify write permissions by creating/deleting test file
        test_file = upload_path / ".write_test"
        try:
            test_file.write_text("")
            test_file.unlink()
            logger.debug(
                "Upload directory write permissions verified",
                extra={"path": str(upload_path)},
            )
        except (IOError, OSError) as e:
            logger.critical(
                "Upload directory is not writable",
                exc_info=True,
                extra={"path": str(upload_path)},
            )
            raise PermissionError(
                f"Upload directory {upload_path} is not writable. Check permissions."
            ) from e

    except PermissionError:
        raise

    except Exception as e:
        logger.critical(
            "Failed to set up upload directory",
            exc_info=True,
            extra={"path": str(settings.static_uploads_dir)},
        )
        raise RuntimeError(
            f"Upload directory setup failed: {str(e)}"
        ) from e


async def _verify_database_connection() -> None:
    """
    Verify database connection is accessible on startup.

    Executes a simple SELECT 1 query to verify:
    - Database server is reachable
    - Credentials are valid
    - Connection pool can be established
    - Database is responsive

    Fails fast with clear error message if database is unavailable.

    Raises:
        RuntimeError: If database is unreachable or unresponsive
    """
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Database connection verified successfully")

    except SQLAlchemyError as e:
        logger.critical(
            "Database connection verification failed",
            exc_info=True,
            extra={"database_url_masked": "***"},
        )
        raise RuntimeError(
            "Database is unreachable. Check DATABASE_URL and server connectivity."
        ) from e

    except Exception as e:
        logger.critical(
            "Unexpected error during database verification",
            exc_info=True,
        )
        raise RuntimeError(
            "Database verification failed unexpectedly."
        ) from e


async def _initialize_database_schema() -> None:
    """
    Initialize database schema (development/testing only).

    In production, use Alembic migrations for schema management.
    This is useful for development and SQLite-based testing.

    Logs warnings if called in production or with non-SQLite databases.
    """
    if settings.is_production:
        logger.warning(
            "Schema initialization skipped in production. Use Alembic migrations."
        )
        return

    if not settings.is_sqlite:
        logger.warning(
            "Schema initialization skipped for non-SQLite database. Use Alembic migrations."
        )
        return

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all, checkfirst=True)
        logger.info(
            "Database schema initialized",
            extra={"environment": settings.ENVIRONMENT},
        )

    except Exception as e:
        logger.error(
            "Failed to initialize database schema",
            exc_info=True,
            extra={"environment": settings.ENVIRONMENT},
        )
        raise RuntimeError(
            "Database schema initialization failed."
        ) from e


async def _shutdown_database_engine() -> None:
    """
    Gracefully shutdown database engine with timeout.

    Disposes all database connections in the pool and cleans up resources.
    Uses timeout to prevent hanging if connections are stuck.

    Logs warnings if shutdown takes longer than expected.
    """
    try:
        # Dispose with timeout to prevent hanging
        await asyncio.wait_for(engine.dispose(), timeout=SHUTDOWN_TIMEOUT)
        logger.info("Database engine disposed successfully")

    except asyncio.TimeoutError:
        logger.warning(
            "Database shutdown timeout - forcing closure",
            extra={"timeout_seconds": SHUTDOWN_TIMEOUT},
        )
        # Force closure if timeout occurs
        await engine.dispose()

    except Exception as e:
        logger.error(
            "Error during database shutdown",
            exc_info=True,
        )


# ============================================================================
# LIFESPAN CONTEXT MANAGER
# ============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager.

    Handles all startup and shutdown procedures:
    - Startup: Validates configuration, verifies database, creates upload dir
    - Runtime: Application runs here (yield)
    - Shutdown: Cleanup database connections and resources

    FastAPI calls this on startup and shutdown automatically.

    Args:
        app: FastAPI application instance
    """
    # ========================================================================
    # STARTUP
    # ========================================================================
    logger.info(
        "Application startup initiated",
        extra={
            "environment": settings.ENVIRONMENT,
            "debug": settings.DEBUG,
            "version": settings.VERSION,
        },
    )

    try:
        # 1. Verify upload directory is writable
        logger.info("Verifying upload directory...")
        await _verify_upload_directory()

        # 2. Verify database is accessible
        logger.info("Verifying database connection...")
        await _verify_database_connection()

        # 3. Initialize schema if development
        if settings.ENVIRONMENT == "development":
            logger.info("Initializing database schema...")
            await _initialize_database_schema()

        logger.info(
            "Application startup completed successfully",
            extra={"environment": settings.ENVIRONMENT},
        )

    except Exception as startup_error:
        logger.critical(
            "Application startup failed - cannot continue",
            exc_info=True,
            extra={"error_type": type(startup_error).__name__},
        )
        raise

    # ========================================================================
    # APPLICATION RUNS HERE
    # ========================================================================
    yield

    # ========================================================================
    # SHUTDOWN
    # ========================================================================
    logger.info("Application shutdown initiated")

    try:
        # Cleanup database connections
        await _shutdown_database_engine()
        logger.info("Application shutdown completed successfully")

    except Exception as shutdown_error:
        logger.error(
            "Error during shutdown",
            exc_info=True,
            extra={"error_type": type(shutdown_error).__name__},
        )


# ============================================================================
# FASTAPI APPLICATION SETUP
# ============================================================================

app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.PROJECT_DESCRIPTION,
    version=settings.VERSION,
    lifespan=lifespan,
    # API docs configuration (disabled in production)
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
)

# ============================================================================
# MIDDLEWARE STACK
# ============================================================================

# CORS Middleware - restrict origins per environment
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)

# Compression Middleware - compress responses over 1KB
app.add_middleware(GZipMiddleware, minimum_size=1000)

# ============================================================================
# STATIC FILES
# ============================================================================

# Serve static files from configurable directory
try:
    static_path = Path(settings.STATIC_FILES_DIR)
    if static_path.exists():
        app.mount(
            "/static",
            StaticFiles(directory=str(static_path)),
            name="static",
        )
        logger.info(
            "Static files mounted",
            extra={"path": str(static_path)},
        )
    else:
        logger.warning(
            "Static files directory does not exist",
            extra={"path": str(static_path)},
        )

except Exception as e:
    logger.error(
        "Failed to mount static files",
        exc_info=True,
        extra={"path": settings.STATIC_FILES_DIR},
    )

# ============================================================================
# ROUTERS
# ============================================================================

app.include_router(
    auth.router,
    prefix=settings.API_V1_STR,
    tags=["Auth"],
)

app.include_router(
    blog.router,
    prefix=settings.API_V1_STR,
    tags=["Blog"],
)

app.include_router(
    comment.router,
    prefix=settings.API_V1_STR,
    tags=["Comments"],
)

app.include_router(
    image.router,
    prefix=settings.API_V1_STR,
    tags=["Images"],
)

# ============================================================================
# ENDPOINTS
# ============================================================================


@app.get(
    "/health",
    tags=["Health"],
    summary="Health check endpoint",
    description="Verify application and database are operational",
    responses={
        200: {
            "description": "Service is healthy",
            "content": {
                "application/json": {
                    "example": {
                        "status": "healthy",
                        "environment": "production",
                    }
                }
            },
        },
        500: {"description": "Service is unhealthy"},
    },
)
async def health_check(
    db: Annotated[AsyncSession, Depends(get_async_db)],
) -> dict:
    """
    Health check endpoint.

    Verifies:
    - Application is running
    - Database connection is healthy

    **Returns:**
    - 200: Service is healthy
    - 500: Database is unreachable or other error

    **Use for:**
    - Kubernetes liveness probes
    - Load balancer health checks
    - Monitoring/alerting systems

    **Note:** Logs at DEBUG level to avoid excessive log volume in production.
    """
    try:
        # Verify database is accessible (already tested by dependency)
        await db.execute(text("SELECT 1"))

        logger.debug(
            "Health check passed",
            extra={"timestamp": "current"},
        )

        return {
            "status": "healthy",
            "environment": settings.ENVIRONMENT,
        }

    except SQLAlchemyError as e:
        logger.error(
            "Health check failed - database error",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database connection failed",
        ) from e

    except Exception as e:
        logger.error(
            "Health check failed - unexpected error",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Health check failed",
        ) from e


@app.get(
    "/",
    include_in_schema=False,
    tags=["Root"],
    summary="Root endpoint",
    description="Welcome message and API information",
)
async def root() -> dict:
    """
    Root endpoint.

    Returns welcome message and API information.
    Not included in OpenAPI schema to keep docs clean.

    **Returns:**
    - Greeting message
    - API name and version
    """
    return {
        "message": f"Welcome to {settings.PROJECT_NAME}",
        "version": settings.VERSION,
        "docs": "/docs" if not settings.is_production else None,
        "health": "/health",
    }


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.RELOAD,
        log_level=settings.LOG_LEVEL.lower(),
    )