import os
from pydantic_settings import BaseSettings
from pydantic import Field, SecretStr
from typing import Literal

class Settings(BaseSettings):
    # Environment
    ENVIRONMENT: Literal["development", "production"] = Field(default="development", env="ENVIRONMENT")
    API_V1_STR: str = "/api/v1"
    
    # Database configuration
    DATABASE_URL: str = Field(default="sqlite+aiosqlite:///./blog.db", env="DATABASE_URL")
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 3600
    DB_ECHO: bool = False
    DB_POOL_PRE_PING: bool = Field( default=True, description="Check connection health before use")

    # Security
    SECRET_KEY: SecretStr = Field(..., env="SECRET_KEY")
    ALGORITHM: str = Field(default="HS256", env="ALGORITHM")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, env="ACCESS_TOKEN_EXPIRE_MINUTES")
    REFRESH_TOKEN_EXPIRE_MINUTES: int = Field(default=1440, env="REFRESH_TOKEN_EXPIRE_MINUTES")

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:5173","http://127.0.0.1:5173",] # for dev Env
    # CORS_ORIGINS: list[str] = ["https://your-production-domain.com", "https://www.your-production-domain.com",] # for production
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: list[str] = ["*"]
    CORS_ALLOW_HEADERS: list[str] = ["*"]

    # config.py
    JWT_ISSUER: str = Field(default="your-app-name", env="JWT_ISSUER")
    JWT_AUDIENCE: str = Field(default="your-app-audience", env="JWT_AUDIENCE")

    # Add these missing attributes:
    PROJECT_NAME: str = "Private Blog API"
    PROJECT_DESCRIPTION: str = "A secure private blogging platform"
    VERSION: str = "1.0.0"
    DOCS_ENABLED: bool = Field(default=True, env="DOCS_ENABLED")
    HOST: str = Field(default="0.0.0.0", env="HOST")
    PORT: int = Field(default=8000, env="PORT")
    RELOAD: bool = Field(default=False, env="RELOAD")
    LOG_LEVEL: str = Field(default="info", env="LOG_LEVEL")
    
    # For lifespan and static files
    STATIC_FILES_DIR: str = Field(default="static", env="STATIC_FILES_DIR")
    UPLOADS_DIR: str = Field(default="uploads", env="UPLOADS_DIR")
    
    # For health check
    HEALTH_CHECK_ENABLED: bool = Field(default=True, env="HEALTH_CHECK_ENABLED")

    # Security headers (recommended)
    SECURITY_HEADERS_ENABLED: bool = Field(default=True, env="SECURITY_HEADERS_ENABLED")

    # Debug configuration
    DEBUG: bool = Field(
        default=False,
        env="DEBUG",
        description="Enable debug mode (never use in production)"
    )

    class Config:
        env_file = ".env"
        extra = "ignore"
        env_file_encoding = 'utf-8'  # Add this for proper encoding
        case_sensitive = False  # Makes env vars case insensitive

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if "sqlite" in self.DATABASE_URL:
            self.DB_POOL_SIZE = 5  # Lower pool size for SQLite

    @property
    def is_sqlite(self) -> bool:
        return "sqlite" in self.DATABASE_URL

    @property
    def is_postgres(self) -> bool:
        return "postgresql" in self.DATABASE_URL

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"
    
    @property
    def static_uploads_dir(self) -> str:
        """Get full path to uploads directory."""
        return os.path.join(self.STATIC_FILES_DIR, self.UPLOADS_DIR)

    @property
    def docs_config(self) -> dict:
        """Return docs configuration."""
        return {
            "docs_url": "/docs" if self.DOCS_ENABLED else None,
            "redoc_url": "/redoc" if self.DOCS_ENABLED else None
        }
    
    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return not self.is_production or self.DEBUG

    @property
    def should_reload(self) -> bool:
        """Determine if auto-reload should be enabled."""
        return self.RELOAD or self.is_development

    def validate_debug_mode(self):
        if self.is_production and self.DEBUG:
            raise ValueError("DEBUG mode cannot be True in production environment")

settings = Settings()