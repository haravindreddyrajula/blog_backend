"""
Production-Ready SQLAlchemy Blog Model

Represents published or draft blog articles with metadata and content management.

Author: Production Code Review Team
Status: Production-Ready
Last Updated: 2025-01-17
"""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, List

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

# ✅ TYPE_CHECKING: Import only for type hints, breaks circular dependency
if TYPE_CHECKING:
    from app.models.user import User
    from app.models.comment import Comment


class BlogStatus(str, Enum):
    """
    Blog publication status enumeration.

    Controls the workflow state of blog posts throughout their lifecycle.

    **Status Values:**
    - DRAFT: Post in progress, not visible to public
    - PUBLISHED: Post published, visible to all users
    - ARCHIVED: Post archived, hidden from lists but accessible via direct link
    """

    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class Blog(Base):
    """
    Blog post model.

    Represents a published or draft blog article with metadata,
    versioning support, and content management.

    **Attributes:**
    - id: Primary key, auto-incremented
    - title: Blog post title (indexed for search)
    - content: Main blog content (unlimited text)
    - status: Publication status (draft/published/archived)
    - is_public: Visibility flag (public vs private)
    - is_featured: Featured flag for homepage display
    - cover_image_url: URL to cover image
    - tags: Comma-separated tags for categorization
    - author_id: Foreign key to User (blog author)
    - author: Relationship to User
    - comments: Relationship to Comment posts
    - created_at: Publication timestamp
    - updated_at: Last modification timestamp

    **Constraints:**
    - title: NOT NULL, indexed for search/filtering (max 255 chars)
    - content: NOT NULL, supports large text (no limit)
    - status: Enum, default DRAFT (prevents invalid states)
    - is_public: Bool, default TRUE (all posts public unless marked private)
    - is_featured: Bool, default FALSE (only homepage-featured posts marked)
    - author_id: Foreign key, NOT NULL, indexed (must have author)
    - created_at: Auto-set on creation, indexed for date filtering
    - updated_at: Auto-set on creation and update

    **Cascade Behavior:**
    - DELETE cascade on author delete: deletes all author's blogs
    - DELETE cascade on comments: deletes all comments when blog deleted
    - Ensures no orphaned records

    **Search & Filter:**
    - Indexed on title for text search operations
    - Indexed on author_id for author queries
    - Indexed on status for publication workflow
    - Indexed on is_public for visibility control
    - Indexed on created_at for date range queries

    **Performance Characteristics:**
    - Composite index on (author_id, status) for author blogs queries
    - Single indexes on frequently filtered columns
    - Title indexed for LIKE search patterns

    **Example Usage:**

    ```python
    from sqlalchemy.orm import selectinload

    # Create blog
    blog = Blog(
        title="My First Post",
        content="This is my first blog post...",
        status=BlogStatus.DRAFT,
        is_public=True,
        author_id=user.id
    )

    session.add(blog)
    await session.commit()

    # Query published blogs by author
    result = await session.execute(
        select(Blog)
        .where(
            Blog.author_id == user_id,
            Blog.status == BlogStatus.PUBLISHED
        )
        .options(selectinload(Blog.author))
        .order_by(Blog.created_at.desc())
    )

    blogs = result.scalars().all()

    # Delete blog (auto-deletes comments)
    await session.delete(blog)
    await session.commit()
    ```
    """

    __tablename__ = "blogs"

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
    # CONTENT
    # ========================================================================

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # ========================================================================
    # METADATA & STATUS
    # ========================================================================

    status: Mapped[BlogStatus] = mapped_column(
        SQLEnum(BlogStatus),
        default=BlogStatus.DRAFT,
        nullable=False,
        index=True,
    )

    is_public: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
    )

    is_featured: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
    )

    cover_image_url: Mapped[str | None] = mapped_column(
        String(2048),  # URL max length
        nullable=True,
    )

    tags: Mapped[str | None] = mapped_column(
        String(1000),  # Comma-separated tags
        nullable=True,
    )

    # ========================================================================
    # FOREIGN KEYS
    # ========================================================================

    author_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
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

    author: Mapped["User"] = relationship(
        "User",
        back_populates="blogs",
        lazy="selectin",
        foreign_keys=[author_id],
    )

    comments: Mapped[List["Comment"]] = relationship(
        "Comment",
        back_populates="blog",
        cascade="all, delete-orphan",
        lazy="selectin",
        foreign_keys="Comment.blog_id",
    )

    # ========================================================================
    # INDEXES
    # ========================================================================

    __table_args__ = (
        # Index("ix_blogs_title", "title"),
        # Index("ix_blogs_author_id", "author_id"),
        # Index("ix_blogs_status", "status"),
        # Index("ix_blogs_is_public", "is_public"),
        # Index("ix_blogs_created_at", "created_at"),
        Index("ix_blogs_author_status", "author_id", "status"),  # Composite
    )

    # ========================================================================
    # REPRESENTATION
    # ========================================================================

    def __repr__(self) -> str:
        return (
            f"<Blog(id={self.id}, title={self.title}, "
            f"author_id={self.author_id}, status={self.status})>"
        )
