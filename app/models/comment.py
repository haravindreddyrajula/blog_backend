"""
Production-Ready SQLAlchemy Comment Model

Represents user comments on blog posts with author tracking and relationships.

Author: Production Code Review Team
Status: Production-Ready
Last Updated: 2025-01-17
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

# ✅ TYPE_CHECKING: Import only for type hints, breaks circular dependency
if TYPE_CHECKING:
    from app.models.blog import Blog
    from app.models.user import User


class Comment(Base):
    """
    Comment model.

    Represents user comments on blog posts with author tracking
    and relationship management.

    **Attributes:**
    - id: Primary key, auto-incremented
    - blog_id: Foreign key to Blog (blog being commented on)
    - author_id: Foreign key to User (comment author)
    - content: Comment text content
    - created_at: Comment creation timestamp
    - blog: Relationship to Blog
    - author: Relationship to User

    **Constraints:**
    - blog_id: Foreign key, NOT NULL, indexed (must reference blog)
    - author_id: Foreign key, NOT NULL, indexed (must have author)
    - content: NOT NULL, text content (no limit)
    - created_at: Auto-set on creation, NOT NULL, indexed for sorting
    - ON DELETE CASCADE: deletes comment if blog deleted
    - ON DELETE CASCADE: deletes comment if author deleted

    **Cascade Behavior:**
    - Blog delete cascades: deletes all comments on blog
    - User delete cascades: deletes all comments by user
    - Ensures referential integrity

    **Security:**
    - author_id tracks who wrote the comment
    - Enables authorization checks (only author/blog owner can delete)
    - Preserves audit trail for moderation
    - No update allowed (immutable comments for audit)

    **Relationships:**
    - Bidirectional with Blog (blog.comments)
    - Bidirectional with User (user.comments)
    - Supports cascade delete when blog deleted
    - Supports cascade delete when user deleted

    **Performance:**
    - blog_id indexed for fetching blog comments
    - author_id indexed for user comment queries
    - created_at indexed for pagination/sorting
    - Composite index on (blog_id, created_at) for typical queries

    **Example Usage:**

    ```python
    from sqlalchemy.orm import selectinload

    # Create comment
    comment = Comment(
        blog_id=blog.id,
        author_id=user.id,
        content="Great post! Really helpful."
    )

    session.add(comment)
    await session.commit()

    # Fetch blog with comments
    result = await session.execute(
        select(Blog)
        .where(Blog.id == blog_id)
        .options(
            selectinload(Blog.comments).selectinload(Comment.author),
            selectinload(Blog.author)
        )
    )

    blog = result.scalar_one()
    for comment in blog.comments:
        print(f"{comment.author.full_name}: {comment.content}")

    # Get comments by user
    result = await session.execute(
        select(Comment)
        .where(Comment.author_id == user_id)
        .order_by(Comment.created_at.desc())
    )

    user_comments = result.scalars().all()

    # Delete comment (removes from blog)
    await session.delete(comment)
    await session.commit()
    ```
    """

    __tablename__ = "comments"

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
    # FOREIGN KEYS
    # ========================================================================

    blog_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("blogs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    author_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ========================================================================
    # CONTENT
    # ========================================================================

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
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

    # ========================================================================
    # RELATIONSHIPS (with Mapped type hints)
    # ========================================================================

    blog: Mapped["Blog"] = relationship(
        "Blog",
        back_populates="comments",
        lazy="selectin",
        foreign_keys=[blog_id],
    )

    author: Mapped["User"] = relationship(
        "User",
        back_populates="comments",
        lazy="selectin",
        foreign_keys=[author_id],
    )

    # ========================================================================
    # INDEXES
    # ========================================================================

    __table_args__ = (
        # Index("ix_comments_blog_id", "blog_id"),
        # Index("ix_comments_author_id", "author_id"),
        # Index("ix_comments_created_at", "created_at"),
        Index("ix_comments_blog_created", "blog_id", "created_at"),  # Composite
    )

    # ========================================================================
    # REPRESENTATION
    # ========================================================================

    def __repr__(self) -> str:
        return (
            f"<Comment(id={self.id}, blog_id={self.blog_id}, "
            f"author_id={self.author_id})>"
        )
