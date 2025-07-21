from contextlib import asynccontextmanager
import logging
import os
from typing import Annotated, AsyncIterator
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import Base, engine
from app.core.deps import get_async_db
from app.routes import auth, blog, comment
from app.core.config import settings
from app.services import image
from app.services.logging_config import setup_logging

settings.validate_debug_mode()  # Will raise error if DEBUG=True in production

if settings.is_production:
    # Force-disable risky settings in production
    settings.DB_ECHO = False
    settings.DOCS_ENABLED = False
    settings.RELOAD = False
    settings.DEBUG = False  # Extra safety measure

# Configure logging
setup_logging()
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events."""
    logger.info("Starting application lifespan...")
    # Create uploads directory if it doesn't exist
    os.makedirs(f"{settings.STATIC_FILES_DIR}/{settings.UPLOADS_DIR}", exist_ok=True)
    logger.info("Upload directory verified")
    
    # Initialize database (for development only)
    if settings.ENVIRONMENT == "development" and settings.is_sqlite:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables created for development!!")
    
    yield  # App runs here
    
    # Clean up on shutdown
    logger.info("Shutting down...")
    await engine.dispose()
    logger.info("Database engine disposed")

app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.PROJECT_DESCRIPTION,
    version=settings.VERSION,
    lifespan=lifespan,
    docs_url="/docs" if settings.DOCS_ENABLED else None,
    redoc_url="/redoc" if settings.DOCS_ENABLED else None,
)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Serve files from the /static URL path
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include routers
app.include_router(auth.router, prefix=f"{settings.API_V1_STR}", tags=["Auth"])
app.include_router(blog.router, prefix=f"{settings.API_V1_STR}", tags=["Blog"])
app.include_router(comment.router, prefix=f"{settings.API_V1_STR}", tags=["Comments"])
app.include_router(image.router, prefix=f"{settings.API_V1_STR}", tags=["Images"])

# Health check endpoint
@app.get("/health", tags=["Health"])
async def health_check(db_provider: Annotated[AsyncIterator[AsyncSession], Depends(get_async_db)]):
    """Health check endpoint."""
    try:
        async with db_provider as session:  # This properly enters the async context manager
            await session.execute(text("SELECT 1"))
            logger.info("Health check request success!!")
            return {"status": "healthy", "environment": settings.ENVIRONMENT}
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Service unhealthy")

@app.get("/", include_in_schema=False)
async def root():
    """Root endpoint redirecting to docs."""
    return {"message": f"Welcome to {settings.PROJECT_NAME} API"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.RELOAD,
        log_level=settings.LOG_LEVEL.lower(),
    )

