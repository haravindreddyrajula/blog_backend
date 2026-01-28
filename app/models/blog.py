"""
Blog model definition.
Represents published or draft blog articles with metadata and content management.
Includes SEO optimization, engagement tracking, advanced categorization, and performance indexing.
Detailed documentation provided within the class and attribute docstrings.
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

# Import only for type hints, breaks circular dependency
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
    - SCHEDULED: Post scheduled for future publication
    """

    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"
    SCHEDULED = "scheduled"

class Blog(Base):
    """
    Blog post model.

    Represents a published or draft blog article with metadata, SEO optimization, engagement tracking, and content management.

    **Core Content Attributes:**
    - id: Primary key, auto-incremented
    - title: Blog post title (indexed for search, max 255 chars)
    - content: Main blog content (unlimited text)
    - excerpt: Short summary for listings & SEO (max 500 chars)
    - slug: URL-friendly identifier (indexed, unique, SEO critical)

    **SEO Attributes (NEW - ESSENTIAL):**
    - meta_description: Search result snippet (155-160 chars for optimal display)
    - meta_keywords: Keywords for search ranking (comma-separated)
    - og_image: Open Graph image for social sharing (priority: og_image > cover_image_url)

    **Metadata & Status:**
    - status: Publication status (draft/published/archived/scheduled)
    - is_public: Visibility flag (public vs private)
    - is_featured: Featured flag for homepage display
    - is_pinned: Pinned flag to highlight important posts
    - cover_image_url: URL to cover image
    - tags: Comma-separated tags for categorization

    **Engagement & Analytics (NEW - ROBUSTNESS):**
    - view_count: Total number of views (denormalized for performance)
    - reading_time_minutes: Estimated reading time (helps UX & SEO)
    - publish_date: Explicit publication date (supports scheduling)

    **Author & Relations:**
    - author_id: Foreign key to User (blog author)
    - author: Relationship to User
    - comments: Relationship to Comment posts

    **Timestamps:**
    - created_at: Record creation timestamp (indexed for date filtering)
    - updated_at: Last modification timestamp (for cache invalidation)
    - published_at: Actual publication timestamp (supports scheduled posts)

    **Constraints:**
    - title: NOT NULL, indexed for search/filtering (max 255 chars)
    - content: NOT NULL, supports large text (no limit)
    - slug: NOT NULL, unique, indexed (URL-friendly identifier)
    - meta_description: Optional, max 160 chars (Google's display limit)
    - excerpt: Optional, max 500 chars (used in listings & meta)
    - reading_time_minutes: NOT NULL, default 1 (calculated on save)
    - status: Enum, default DRAFT (prevents invalid states)
    - is_public: Bool, default TRUE
    - is_featured: Bool, default FALSE
    - is_pinned: Bool, default FALSE
    - view_count: Integer, default 0 (incremented on page views)
    - author_id: Foreign key, NOT NULL, indexed (must have author)
    - created_at: Auto-set on creation, indexed for date filtering
    - updated_at: Auto-set on creation and update
    - published_at: Set when status changes to PUBLISHED

    **Cascade Behavior:**
    - DELETE cascade on author delete: deletes all author's blogs
    - DELETE cascade on comments: deletes all comments when blog deleted
    - Ensures no orphaned records

    **Search & Filter:**
    - Indexed on title for text search operations
    - Indexed on slug for URL lookups (UNIQUE)
    - Indexed on author_id for author queries
    - Indexed on status for publication workflow
    - Indexed on is_public for visibility control
    - Indexed on is_featured for homepage queries
    - Indexed on created_at for date range queries
    - Indexed on published_at for chronological sorting

    **Performance Characteristics:**
    - Composite index on (author_id, status) for author blogs queries
    - Composite index on (status, published_at) for public blogs timeline
    - Single indexes on frequently filtered columns
    - Title & slug indexed for LIKE search patterns
    - View count denormalized (no separate table) for fast queries

    **Representation:**
    - __repr__: Returns string with id, slug, author_id, and status    
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
    # CONTENT (Core)
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

    excerpt: Mapped[str | None] = mapped_column(
        String(500),  # Short summary for listings
        nullable=True,
    )

    # ========================================================================
    # SEO FIELDS (NEW - CRITICAL FOR SEARCH VISIBILITY)
    # ========================================================================

    slug: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        unique=True,  # Prevent duplicate slugs
    )

    meta_description: Mapped[str | None] = mapped_column(
        String(160),  # Google's typical display limit (155-160 chars)
        nullable=True,
    )

    meta_keywords: Mapped[str | None] = mapped_column(
        String(500),  # Comma-separated keywords
        nullable=True,
    )

    og_image: Mapped[str | None] = mapped_column(
        String(2048),  # Open Graph image for social sharing
        nullable=True,
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

    is_pinned: Mapped[bool] = mapped_column(
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
    # ENGAGEMENT & ANALYTICS (NEW - ROBUSTNESS)
    # ========================================================================

    view_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        index=True,  # Indexed for "most viewed" queries
    )

    reading_time_minutes: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
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

    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,  # Indexed for chronological sorting of published posts
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
        Index("ix_blogs_author_status", "author_id", "status"),  # Composite
        Index("ix_blogs_status_published", "status", "published_at"),  # For timeline queries
    )

    # ========================================================================
    # REPRESENTATION
    # ========================================================================

    def __repr__(self) -> str:
        return (
           f"Blog(id={self.id}, slug={self.slug}, title={self.title!r}, "
           f"author_id={self.author_id}, status={self.status.value})"
        )
 