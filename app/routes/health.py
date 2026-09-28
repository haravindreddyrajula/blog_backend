"""
Health check routes for load balancer probes and uptime monitoring.

Two endpoints with different purposes:
- /health: Liveness probe. No DB hit — just confirms the process is up and
  responsive. Safe for ALB/ECS to call every few seconds.
- /health/db: Readiness probe. Hits the database once and reports pool
  stats. Call this less frequently (e.g. every 30-60s) to avoid adding
  needless load to the connection pool.
"""

import logging

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.database import get_pool_status, is_database_healthy

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health", status_code=status.HTTP_200_OK, summary="Liveness probe")
async def health_check() -> dict:
    """
    Liveness probe — confirms the application process is running.

    Does not touch the database. Use this for high-frequency load balancer
    health checks where you only need to know the process didn't crash.

    Returns:
        Dict with service status and name.
    """
    return {"status": "ok", "service": settings.PROJECT_NAME}


@router.get("/health/db", summary="Database readiness probe")
async def health_check_db() -> JSONResponse:
    """
    Readiness probe — confirms the database is reachable and reports pool state.

    Returns HTTP 200 with pool metrics when the DB is reachable, or HTTP 503
    when it isn't. Logs an error on failure so it shows up in CloudWatch
    without needing to inspect the response body.

    Returns:
        JSONResponse containing status ("ok"/"unavailable") and pool metrics
        from `get_pool_status()`.
    """
    healthy = await is_database_healthy()
    pool_status = get_pool_status()

    payload = {
        "status": "ok" if healthy else "unavailable",
        "database": pool_status,
    }

    if not healthy:
        logger.error("Health check failed: database unreachable", extra=payload)
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=payload)

    return JSONResponse(status_code=status.HTTP_200_OK, content=payload)
