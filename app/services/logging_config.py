# ============================================================================
# LOGGING CONFIGURATION - PRODUCTION-READY
# ============================================================================
#
# Configures Python logging for FastAPI application with:
# - Environment-based log levels (DEBUG/INFO/WARNING/ERROR)
# - Log rotation to prevent disk exhaustion
# - Structured logging support (JSON for log aggregation)
# - Suppressed noisy third-party loggers
# - Request ID context for distributed tracing
#
# Usage:
#     from app.core.logging_config import setup_logging
#     setup_logging()
#
# Environment Variables:
#     LOG_LEVEL: Root logger level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
#     LOG_DIR: Directory for log files (default: logs/)
#     ENABLE_JSON_LOGS: Use JSON format instead of text (default: False)
#     LOG_FILE_SIZE_MB: Max size before rotation (default: 50MB)
#     LOG_BACKUP_COUNT: Number of rotated log files to keep (default: 10)
#
# ============================================================================

import logging.config
import os
from pathlib import Path
from typing import Optional

# ============================================================================
# CONFIGURATION
# ============================================================================

# Read environment variables with defaults
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_DIR = Path(os.getenv("LOG_DIR", "logs")).resolve()
ENABLE_JSON_LOGS = os.getenv("ENABLE_JSON_LOGS", "False").lower() == "true"
LOG_FILE_SIZE_MB = int(os.getenv("LOG_FILE_SIZE_MB", "50"))
LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "10"))

# Validate log level
VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
if LOG_LEVEL not in VALID_LOG_LEVELS:
    LOG_LEVEL = "INFO"

logger = logging.getLogger(__name__)

# ============================================================================
# LOGGING CONFIGURATION DICTIONARY
# ============================================================================

def _get_logging_config() -> dict:
    """
    Build logging configuration dictionary.
    
    Returns:
        dictConfig-compatible configuration dictionary
    """
    
    # Use JSON formatter if enabled, otherwise standard text format
    if ENABLE_JSON_LOGS:
        formatter_config = {
            "json": {
                "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
                "format": "%(asctime)s %(name)s %(levelname)s %(message)s %(pathname)s %(lineno)d %(funcName)s",
                "timestamp": True,
                "renamed_fields": {"asctime": "timestamp"}
            }
        }
        default_formatter = "json"
    else:
        formatter_config = {
            "standard": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S"
            },
            "detailed": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(funcName)s - %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S"
            }
        }
        default_formatter = "standard"
    
    config = {
        "version": 1,
        "disable_existing_loggers": False,
        
        # Formatters
        "formatters": formatter_config,
        
        # Handlers
        "handlers": {
            # Console handler - shows INFO and above
            "console": {
                "class": "logging.StreamHandler",
                "formatter": default_formatter,
                "level": "INFO",
                "stream": "ext://sys.stdout"
            },
            
            # File handler - rotates based on size
            # Keeps all levels for debugging
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": "detailed" if not ENABLE_JSON_LOGS else "json",
                "level": "DEBUG",
                "filename": str(LOG_DIR / "app.log"),
                "mode": "a",
                "maxBytes": LOG_FILE_SIZE_MB * 1024 * 1024,
                "backupCount": LOG_BACKUP_COUNT,
                "encoding": "utf-8",
                "delay": False
            },
            
            # Error file handler - separate file for errors
            "error_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": "detailed" if not ENABLE_JSON_LOGS else "json",
                "level": "ERROR",
                "filename": str(LOG_DIR / "app.error.log"),
                "mode": "a",
                "maxBytes": 10 * 1024 * 1024,  # 10MB
                "backupCount": 5,
                "encoding": "utf-8",
                "delay": False
            },
            
            # Performance handler - logs slow operations
            "performance": {
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": "detailed" if not ENABLE_JSON_LOGS else "json",
                "level": "WARNING",
                "filename": str(LOG_DIR / "app.performance.log"),
                "mode": "a",
                "maxBytes": 5 * 1024 * 1024,
                "backupCount": 5,
                "encoding": "utf-8",
                "delay": False
            }
        },
        
        # Loggers configuration
        "loggers": {
            # Root logger - captures all loggers
            "": {
                "handlers": ["console", "file", "error_file"],
                "level": LOG_LEVEL,
                "propagate": True
            },
            
            # Application loggers
            "app": {
                "handlers": ["console", "file", "error_file"],
                "level": LOG_LEVEL,
                "propagate": False
            },
            
            # Uvicorn (ASGI server) - only INFO and above to reduce noise
            "uvicorn": {
                "handlers": ["console", "file"],
                "level": "INFO",
                "propagate": False
            },
            
            "uvicorn.access": {
                "handlers": ["console", "file"],
                "level": "INFO",
                "propagate": False
            },
            
            "uvicorn.error": {
                "handlers": ["console", "file", "error_file"],
                "level": "ERROR",
                "propagate": False
            },
            
            # Suppress noisy third-party loggers
            "sqlalchemy": {
                "level": "WARNING",
                "handlers": ["file"],
                "propagate": False
            },
            
            "sqlalchemy.engine": {
                "level": "WARNING",
                "handlers": ["file"],
                "propagate": False
            },
            
            "sqlalchemy.pool": {
                "level": "WARNING",
                "handlers": ["file"],
                "propagate": False
            },
            
            "urllib3": {
                "level": "WARNING",
                "handlers": ["file"],
                "propagate": False
            },
            
            "asyncio": {
                "level": "WARNING",
                "handlers": ["file"],
                "propagate": False
            },
            
            "aiofiles": {
                "level": "INFO",
                "handlers": ["file"],
                "propagate": False
            },
            
            "jose": {
                "level": "INFO",
                "handlers": ["file"],
                "propagate": False
            }
        }
    }
    
    return config


# ============================================================================
# SETUP FUNCTION
# ============================================================================

def setup_logging() -> None:
    """
    Initialize logging configuration globally.
    
    This function:
    1. Creates log directory if it doesn't exist
    2. Validates directory is writable
    3. Applies logging configuration
    4. Logs startup information
    
    Raises:
        RuntimeError: If log directory cannot be created or is not writable
    
    Usage:
        from app.core.logging_config import setup_logging
        
        setup_logging()  # Call during application startup
    """
    
    try:
        # ====================================================================
        # CREATE AND VALIDATE LOG DIRECTORY
        # ====================================================================
        
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise RuntimeError(
                f"Failed to create log directory {LOG_DIR}: {e}"
            ) from e
        
        # Verify directory is writable
        try:
            test_file = LOG_DIR / ".write_test"
            test_file.touch()
            test_file.unlink()
        except OSError as e:
            raise RuntimeError(
                f"Log directory is not writable {LOG_DIR}: {e}"
            ) from e
        
        # ====================================================================
        # APPLY LOGGING CONFIGURATION
        # ====================================================================
        
        config = _get_logging_config()
        logging.config.dictConfig(config)
        
        # Get logger after configuration is applied
        root_logger = logging.getLogger()
        
        # ====================================================================
        # LOG STARTUP INFORMATION
        # ====================================================================
        
        root_logger.info(
            "Logging initialized",
            extra={
                "log_level": LOG_LEVEL,
                "log_dir": str(LOG_DIR),
                "json_logs_enabled": ENABLE_JSON_LOGS,
                "log_file_size_mb": LOG_FILE_SIZE_MB,
                "log_backup_count": LOG_BACKUP_COUNT
            }
        )
        
        if ENABLE_JSON_LOGS:
            root_logger.info("JSON logging enabled - suitable for log aggregation")
        
        root_logger.debug(f"Application starting in {LOG_DIR}")
    
    except RuntimeError as e:
        # Log directory setup failed - print to stderr as fallback
        print(f"ERROR: Logging setup failed: {e}", file=__import__("sys").stderr)
        raise
    except Exception as e:
        # Unexpected error during setup
        print(
            f"ERROR: Unexpected error during logging setup: {e}",
            file=__import__("sys").stderr
        )
        raise RuntimeError(f"Logging setup failed: {e}") from e


# ============================================================================
# CONTEXT MANAGER FOR REQUEST-SCOPED LOGGING
# ============================================================================

class RequestContext:
    """
    Context manager for per-request logging context.
    
    Stores request ID, user ID, etc. for correlation in logs.
    
    Usage:
        with RequestContext(request_id="abc123", user_id=42):
            logger.info("Processing request")  # Will include context
    """
    
    _context: dict = {}
    
    def __init__(self, **kwargs):
        self.context = kwargs
    
    def __enter__(self):
        RequestContext._context.update(self.context)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        for key in self.context:
            RequestContext._context.pop(key, None)
    
    @classmethod
    def get_context(cls) -> dict:
        """Get current logging context."""
        return cls._context.copy()


# ============================================================================
# INITIALIZATION
# ============================================================================

# Call setup_logging() in main.py during startup:
#
#     from app.core.logging_config import setup_logging
#     from contextlib import asynccontextmanager
#     
#     @asynccontextmanager
#     async def lifespan(app: FastAPI):
#         # Startup
#         setup_logging()
#         yield
#         # Shutdown