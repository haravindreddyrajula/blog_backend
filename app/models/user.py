"""
User model definition.

Represents user accounts with authentication credentials and profile information.

Author: Haravind Rajula
Status: Production-Ready
Last Updated: 2025-01-17
"""

from datetime import datetime
from typing import TYPE_CHECKING, List

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

# ✅ TYPE_CHECKING: Import only for type hints, breaks circular dependency
if TYPE_CHECKING:
    from app.models.blog import Blog
    from app.models.comment import Comment


class User(Base):
    """
    User account model.

    Represents a user in the system with authentication credentials
    and profile information.

    **Attributes:**
    - id: Primary key, auto-incremented
    - email: Unique email address for login and contact
    - hashed_password: Bcrypt hashed password (never store plaintext)
    - is_active: Account status flag (soft delete alternative)
    - full_name: User's display name
    - created_at: Account creation timestamp
    - updated_at: Last modification timestamp
    - blogs: Relationship to Blog posts authored by this user
    - comments: Relationship to Comment posts authored by this user

    **Constraints:**
    - email: UNIQUE, NOT NULL, indexed for login queries (RFC 5321: 254 chars max)
    - hashed_password: NOT NULL, must be bcrypt hashed
    - is_active: Default TRUE (can deactivate without deleting)
    - created_at: Auto-set on creation, indexed for range queries
    - updated_at: Auto-set on creation and update

    **Cascade Behavior:**
    - DELETE cascade on blogs: deletes all authored blogs
    - DELETE cascade on comments: deletes all authored comments
    - Preserves referential integrity

    **Security Notes:**
    - Password must ALWAYS be hashed before storage
    - No plaintext passwords anywhere
    - Use is_active for soft deletes (preserves data integrity for GDPR)
    - Email validated at application layer; stored as-is

    **Performance:**
    - email indexed for login lookups
    - is_active indexed for active user queries
    - created_at indexed for date range queries

    **Example Usage:**

    ```python
    # Create user
    user = User(
        email="user@example.com",
        hashed_password="$2b$12$...",
        full_name="John Doe",
        is_active=True
    )

    session.add(user)
    await session.commit()

    # Query by email
    result = await session.execute(
        select(User).where(User.email == "user@example.com")
    )

    user = result.scalar_one_or_none()

    # Access relationships
    blogs = user.blogs # All blogs authored by user
    comments = user.comments # All comments by user
    ```
    """

    __tablename__ = "users"

    # ========================================================================
    # PRIMARY KEY
    # ========================================================================

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        index=True,
    )

    # ========================================================================
    # AUTHENTICATION
    # ========================================================================

    email: Mapped[str] = mapped_column(
        String(254),  # RFC 5321 max email length
        unique=True,
        nullable=False,
        index=True,
    )

    hashed_password: Mapped[str] = mapped_column(
        String(255),  # Bcrypt output is ~60 chars, padded for safety
        nullable=False,
    )

    # ========================================================================
    # PROFILE
    # ========================================================================

    full_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # ========================================================================
    # STATUS
    # ========================================================================

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
    )

    # ========================================================================
    # TIMESTAMPS
    # ========================================================================

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # ========================================================================
    # RELATIONSHIPS (with Mapped type hints)
    # ========================================================================

    blogs: Mapped[List["Blog"]] = relationship(
        "Blog",
        back_populates="author",
        cascade="all, delete-orphan",
        lazy="selectin",
        foreign_keys="Blog.author_id",
    )

    comments: Mapped[List["Comment"]] = relationship(
        "Comment",
        back_populates="author",
        cascade="all, delete-orphan",
        lazy="selectin",
        foreign_keys="Comment.author_id",
    )

    # ========================================================================
    # INDEXES
    # ========================================================================

    # __table_args__ = (
    #     Index("ix_users_email", "email", unique=True),
    #     Index("ix_users_is_active", "is_active"),
    #     Index("ix_users_created_at", "created_at"),
    # )

    # ========================================================================
    # REPRESENTATION
    # ========================================================================

    def __repr__(self) -> str:
        return (
            f"<User(id={self.id}, email={self.email}, "
            f"full_name={self.full_name}, is_active={self.is_active})>"
        )
