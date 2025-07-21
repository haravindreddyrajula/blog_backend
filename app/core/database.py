import logging
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import NullPool

from app.core.config import settings

logger = logging.getLogger(__name__)

# Prepare common engine arguments
engine_args = {
    "echo": settings.DB_ECHO,
    "future": True
}

# Adjust args based on database type
if settings.is_postgres:
    engine_args.update({
        "pool_size": settings.DB_POOL_SIZE,
        "max_overflow": settings.DB_MAX_OVERFLOW,
        "pool_timeout": settings.DB_POOL_TIMEOUT,
        "pool_recycle": settings.DB_POOL_RECYCLE,
        "pool_pre_ping": True,
        "connect_args": {
            "server_settings": {
                "application_name": "blog_app",
                "statement_timeout": "30000"
            }
        }
    })
elif settings.is_sqlite:
    engine_args["poolclass"] = NullPool  # Disable pooling for SQLite

# Create async engine
engine = create_async_engine(
    str(settings.DATABASE_URL),  # cast to string to avoid AnyUrl issues
    **engine_args
)

# Session Factory
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autoflush=False,
    expire_on_commit=False
)

# Declarative Base
Base = declarative_base()

# Init DB - for development only (SQLite)
async def init_db():
    """
    Initialize database (for dev/testing only).
    In production, use Alembic migrations.
    """
    if settings.is_sqlite:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            logger.info("SQLite tables created.")
    else:
        logger.warning("init_db() skipped: Non-SQLite DB detected.")
