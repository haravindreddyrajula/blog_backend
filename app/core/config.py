"""
Configuration management for the Private Blog API.

This module handles all environment-based configuration using Pydantic v2's
BaseSettings for type-safe environment variable loading. It validates settings
on instantiation and provides convenient property accessors for feature toggles.

Environment variables should be sourced from a `.env` file (development only)
or set directly in the deployment environment (production).
"""

import os
import logging
from functools import cached_property
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings


logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Attributes:
        ENVIRONMENT: Runtime environment (development or production)
        SECRET_KEY: JWT signing key (required, minimum 32 chars)
        DATABASE_URL: SQLAlchemy database connection string
        Various feature toggles and configuration parameters
    """

    # ============================================================================
    # ENVIRONMENT
    # ============================================================================
    ENVIRONMENT: Literal["development", "production"] = Field(
        default="development",
        env="ENVIRONMENT",
        description="Runtime environment"
    )

    DEBUG: bool = Field(
        default=False,
        env="DEBUG",
        description="Enable debug mode (never use in production)"
    )

    # ============================================================================
    # API METADATA
    # ============================================================================
    PROJECT_NAME: str = Field(
        default="Private Blog API",
        env="PROJECT_NAME",
        description="Application name for documentation"
    )

    PROJECT_DESCRIPTION: str = Field(
        default="A secure private blogging platform",
        env="PROJECT_DESCRIPTION",
        description="Application description for documentation"
    )

    VERSION: str = Field(
        default="1.0.0",
        env="VERSION",
        description="API version"
    )

    API_V1_STR: str = "/api/v1"

    # ============================================================================
    # SERVER
    # ============================================================================
    HOST: str = Field(
        default="0.0.0.0",
        env="HOST",
        description="Server host to bind to"
    )

    PORT: int = Field(
        default=8000,
        env="PORT",
        ge=1,
        le=65535,
        description="Server port"
    )

    RELOAD: bool = Field(
        default=False,
        env="RELOAD",
        description="Enable auto-reload on code changes"
    )

    LOG_LEVEL: Literal["debug", "info", "warning", "error", "critical"] = Field(
        default="info",
        env="LOG_LEVEL",
        description="Logging level"
    )

    # ============================================================================
    # SECURITY
    # ============================================================================
    SECRET_KEY: SecretStr = Field(
        ...,  # Required
        env="SECRET_KEY",
        description="JWT signing key (minimum 32 characters)"
    )

    ALGORITHM: str = Field(
        default="HS256",
        env="ALGORITHM",
        description="JWT algorithm"
    )

    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=30,
        env="ACCESS_TOKEN_EXPIRE_MINUTES",
        gt=0,
        description="Access token expiration in minutes"
    )

    REFRESH_TOKEN_EXPIRE_MINUTES: int = Field(
        default=1440,  # 24 hours
        env="REFRESH_TOKEN_EXPIRE_MINUTES",
        gt=0,
        description="Refresh token expiration in minutes"
    )

    JWT_ISSUER: str = Field(
        env="JWT_ISSUER",
        description="JWT issuer identifier (required in production)"
    )

    JWT_AUDIENCE: str = Field(
        env="JWT_AUDIENCE",
        description="JWT audience identifier (required in production)"
    )

    POSTGRES_STATEMENT_TIMEOUT_MS: int = Field(
        default=30000,  # 30 seconds
        env="POSTGRES_STATEMENT_TIMEOUT_MS",
        gt=0,
        description="PostgreSQL statement timeout in milliseconds"
    )

    # ============================================================================
    # CORS
    # ============================================================================
    CORS_ORIGINS: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"],
        env="CORS_ORIGINS",
        description="Allowed CORS origins (comma-separated)"
    )

    CORS_ALLOW_CREDENTIALS: bool = Field(
        default=True,
        env="CORS_ALLOW_CREDENTIALS",
        description="Allow credentials in CORS requests"
    )

    CORS_ALLOW_METHODS: list[str] = Field(
        default_factory=lambda: ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        env="CORS_ALLOW_METHODS",
        description="Allowed HTTP methods (comma-separated)"
    )

    CORS_ALLOW_HEADERS: list[str] = Field(
        default_factory=lambda: ["Content-Type", "Authorization"],
        env="CORS_ALLOW_HEADERS",
        description="Allowed request headers (comma-separated)"
    )

    # ============================================================================
    # DATABASE
    # ============================================================================
    DATABASE_URL: str = Field(
        default="sqlite+aiosqlite:///./blog.db",
        env="DATABASE_URL",
        description="SQLAlchemy database connection string"
    )

    DB_POOL_SIZE: int = Field(
        default=20,
        env="DB_POOL_SIZE",
        ge=1,
        description="Database connection pool size"
    )

    DB_MAX_OVERFLOW: int = Field(
        default=10,
        env="DB_MAX_OVERFLOW",
        ge=0,
        description="Maximum overflow connections"
    )

    DB_POOL_TIMEOUT: int = Field(
        default=30,
        env="DB_POOL_TIMEOUT",
        gt=0,
        description="Connection pool timeout in seconds"
    )

    DB_POOL_RECYCLE: int = Field(
        default=3600,
        env="DB_POOL_RECYCLE",
        gt=0,
        description="Recycle connections after N seconds (prevents stale connections)"
    )

    DB_ECHO: bool = Field(
        default=False,
        env="DB_ECHO",
        description="Enable SQL query logging"
    )

    DB_POOL_PRE_PING: bool = Field(
        default=True,
        env="DB_POOL_PRE_PING",
        description="Test connection health before using from pool"
    )

    # ============================================================================
    # FILE STORAGE
    # ============================================================================
    STATIC_FILES_DIR: str = Field(
        default="static",
        env="STATIC_FILES_DIR",
        description="Static files directory path"
    )

    UPLOADS_DIR: str = Field(
        default="uploads",
        env="UPLOADS_DIR",
        description="User uploads directory path (relative to STATIC_FILES_DIR)"
    )

    # ============================================================================
    # FEATURES
    # ============================================================================
    DOCS_ENABLED: bool = Field(
        default=True,
        env="DOCS_ENABLED",
        description="Enable Swagger/ReDoc documentation endpoints"
    )

    HEALTH_CHECK_ENABLED: bool = Field(
        default=True,
        env="HEALTH_CHECK_ENABLED",
        description="Enable health check endpoint"
    )

    SECURITY_HEADERS_ENABLED: bool = Field(
        default=True,
        env="SECURITY_HEADERS_ENABLED",
        description="Enable security headers middleware"
    )

    # ============================================================================
    # PYDANTIC CONFIGURATION
    # ============================================================================
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
    }

    # ============================================================================
    # VALIDATORS
    # ============================================================================

    @model_validator(mode="after")
    def validate_settings(self) -> "Settings":
        """
        Validate settings consistency after initialization.

        Raises:
            ValueError: If invalid configuration is detected
        """
        # Validate DEBUG mode
        if self.is_production and self.DEBUG:
            raise ValueError(
                "DEBUG mode must be False in production environment"
            )

        # Validate RELOAD mode
        if self.is_production and self.RELOAD:
            raise ValueError(
                "Auto-reload must be disabled in production environment"
            )

        # Validate SECRET_KEY strength
        if len(self.SECRET_KEY.get_secret_value()) < 32:
            raise ValueError(
                "SECRET_KEY must be at least 32 characters (256 bits)"
            )

        # Validate JWT configuration in production
        if self.is_production:
            if not self.JWT_ISSUER or self.JWT_ISSUER == "your-app-name":
                raise ValueError(
                    "JWT_ISSUER must be explicitly set in production"
                )
            if not self.JWT_AUDIENCE or self.JWT_AUDIENCE == "your-app-audience":
                raise ValueError(
                    "JWT_AUDIENCE must be explicitly set in production"
                )

        # Validate CORS configuration in production
        if self.is_production:
            if not self.CORS_ORIGINS or any(
                "localhost" in origin or "127.0.0.1" in origin
                for origin in self.CORS_ORIGINS
            ):
                raise ValueError(
                    "CORS_ORIGINS must not contain localhost addresses in production"
                )

        # Validate database pool size for SQLite
        if self.is_sqlite and self.DB_POOL_SIZE > 5:
            logger.warning(
                "Database pool size %d may be too high for SQLite; "
                "reducing to 5 for stability",
                self.DB_POOL_SIZE
            )
            self.DB_POOL_SIZE = 5

        # Validate file paths
        self._validate_file_paths()

        return self

    def _validate_file_paths(self) -> None:
        """
        Validate that file paths are safe and don't allow traversal.

        Raises:
            ValueError: If paths contain unsafe patterns
        """
        for path_name, path_value in [
            ("STATIC_FILES_DIR", self.STATIC_FILES_DIR),
            ("UPLOADS_DIR", self.UPLOADS_DIR),
        ]:
            # Prevent absolute paths
            if os.path.isabs(path_value):
                raise ValueError(
                    f"{path_name} must be a relative path, got: {path_value}"
                )
            # Prevent path traversal
            if ".." in path_value or path_value.startswith("/"):
                raise ValueError(
                    f"{path_name} contains unsafe path patterns: {path_value}"
                )

    # ============================================================================
    # CACHED PROPERTIES (computed once and cached)
    # ============================================================================
    @cached_property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.ENVIRONMENT == "production"

    @cached_property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.ENVIRONMENT == "development"

    @cached_property
    def is_sqlite(self) -> bool:
        """Check if using SQLite database."""
        return "sqlite" in self.DATABASE_URL.lower()

    @cached_property
    def is_postgres(self) -> bool:
        """Check if using PostgreSQL database."""
        return "postgresql" in self.DATABASE_URL.lower()

    @cached_property
    def should_reload(self) -> bool:
        """Determine if auto-reload should be enabled."""
        return self.RELOAD and self.is_development

    # ============================================================================
    # COMPUTED PROPERTIES
    # ============================================================================
    @property
    def static_uploads_dir(self) -> Path:
        """
        Get the full path to the uploads directory.

        Returns:
            Path object for the uploads directory
        """
        uploads_path = Path(self.STATIC_FILES_DIR) / self.UPLOADS_DIR
        return uploads_path

    @property
    def docs_config(self) -> dict:
        """
        Generate docs configuration for FastAPI app initialization.

        Returns:
            Dict with docs_url and redoc_url, or None if disabled
        """
        return {
            "docs_url": "/docs" if self.DOCS_ENABLED else None,
            "redoc_url": "/redoc" if self.DOCS_ENABLED else None,
        }

    @property
    def database_config(self) -> dict:
        """
        Generate SQLAlchemy engine configuration.

        Returns:
            Dict with connection pool and echo settings
        """
        return {
            "pool_size": self.DB_POOL_SIZE,
            "max_overflow": self.DB_MAX_OVERFLOW,
            "pool_timeout": self.DB_POOL_TIMEOUT,
            "pool_recycle": self.DB_POOL_RECYCLE,
            "echo": self.DB_ECHO,
            "pool_pre_ping": self.DB_POOL_PRE_PING,
        }


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================
# Load settings once at module import time
# Access via: from config import settings
try:
    settings = Settings()
    logger.info(
        "Configuration loaded: environment=%s, debug=%s",
        settings.ENVIRONMENT,
        settings.DEBUG
    )
except Exception as e:
    logger.critical("Failed to load configuration: %s", str(e))
    raise
