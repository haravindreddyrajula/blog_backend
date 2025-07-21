import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional
from fastapi import HTTPException, status
from sqlalchemy.exc import SQLAlchemyError, DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.config import settings

logger = logging.getLogger(__name__)

# @asynccontextmanager
async def get_async_db() -> AsyncIterator[AsyncSession]:

    """
    Production-grade async DB session dependency with:
    - Automatic commit/rollback
    - Granular error handling
    - Comprehensive logging
    - Connection health checking
    """

    session: Optional[AsyncSession] = None

    try:
        session = AsyncSessionLocal()
        
        # Verify connection is alive #TODO
        if settings.DB_POOL_PRE_PING:  
            await session.connection()
        
        logger.debug("Database session established", extra={"session_id": id(session)})
        yield session
        
        # Only commit if we're not in a nested transaction
        if not session.in_nested_transaction():
            await session.commit()
            logger.debug("Transaction committed")
        else:
            logger.debug("Skipping commit for nested transaction")

    except DBAPIError as e:
        logger.error("Database connection error", exc_info=True)
        await _safe_rollback(session)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable"
        )
    except SQLAlchemyError as e:
        logger.error("Database operation failed", exc_info=True)
        await _safe_rollback(session)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid database operation"
        )
    except Exception as e:
        logger.critical("Unexpected database error", exc_info=True)
        await _safe_rollback(session)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )
    finally:
        await _safe_close(session)

async def _safe_rollback(session: Optional[AsyncSession]) -> None:
    """Safely rollback session if it exists."""
    if session is not None:
        try:
            await session.rollback()
            logger.debug("Transaction rolled back")
        except Exception as rollback_error:
            logger.error("Rollback failed", exc_info=True)

async def _safe_close(session: Optional[AsyncSession]) -> None:
    """Safely close session if it exists."""
    if session is not None:
        try:
            await session.close()
            logger.debug("Session closed")
        except Exception as close_error:
            logger.warning("Session close failed", exc_info=True)
            
