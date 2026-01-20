"""
SQLAlchemy Models Package

Modular model structure for production-grade blog application.

**Directory Structure:**
    models/
    â”œâ”€â”€ __init__.py           â† This file (exports all models)
    â”œâ”€â”€ user.py              â† User model
    â”œâ”€â”€ blog.py              â† Blog model (with BlogStatus enum)
    â”œâ”€â”€ comment.py           â† Comment model
    â””â”€â”€ revoked_token.py     â† RevokedToken model (with TokenType enum)

**Import All Models From Package:**
    ```python
    from app.models import User, Blog, Comment, RevokedToken
    from app.models import BlogStatus, TokenType
    ```

**Usage in Application:**
    ```python
    # In app/core/database.py
    from app.models import User, Blog, Comment, RevokedToken

    # All models inherit from Base and are registered with SQLAlchemy
    ```

**Database Initialization:**
    ```python
    from sqlalchemy.ext.asyncio import create_async_engine
    from app.core.database import Base

    engine = create_async_engine(DATABASE_URL)

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    ```

Author: Production Code Review Team
Status: Production-Ready
Last Updated: 2025-01-17
"""

from app.models.blog import Blog, BlogStatus
from app.models.comment import Comment
from app.models.revoked_tokens import RevokedToken, TokenType
from app.models.user import User

__all__ = [
    # Models
    "User",
    "Blog",
    "Comment",
    "RevokedToken",
    # Enums
    "BlogStatus",
    "TokenType",
]