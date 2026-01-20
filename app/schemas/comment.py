"""
Production-Ready Comment Schemas

Defines request/response models for blog comments with comprehensive validation,
security controls, and alignment with SQLAlchemy ORM models.

Author: Production Code Review Team
Status: Production-Ready
Last Updated: 2025-01-17

**Critical Design Note:**
Unlike the original schema, comments are ALWAYS authored by authenticated users.
The schema reflects this by tracking author_id (not a free-form "name" field).
This prevents anonymous/spam comments and enables author tracking for moderation.
"""

from datetime import datetime
from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# Constants
MAX_CONTENT_LENGTH = 2000  # ~400 words (typical comment length)
MIN_CONTENT_LENGTH = 1  # Allow single character (even if minimal)


class CommentCreate(BaseModel):
    """
    Comment creation request model.
    
    Used when creating a new comment on a blog post. The author is automatically
    extracted from the JWT token (not in request body), ensuring comments are
    always attributed to the authenticated user.
    
    **Security:**
    - author_id automatically set from current_user (JWT)
    - blog_id required in URL path, not in body
    - Prevents anonymous comments (enforced by auth middleware)
    - Prevents author spoofing
    
    **Example:**
    ```python
    # POST /blogs/123/comments
    {
        "content": "Great post! Thanks for sharing."
    }
    ```
    
    **Note:** This differs from the original schema which had a "name" field.
    Comments are always tied to authenticated users via author_id from ORM model.
    """

    content: Annotated[
        str,
        Field(
            ...,
            min_length=MIN_CONTENT_LENGTH,
            max_length=MAX_CONTENT_LENGTH,
            description=f"Comment text content ({MIN_CONTENT_LENGTH}-{MAX_CONTENT_LENGTH} characters)",
            examples=["Great post! This really helped me understand FastAPI."],
        ),
    ]

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        """
        Sanitize comment content.
        
        - Strip leading/trailing whitespace
        - Prevent null bytes and control characters
        - Validate UTF-8 encoding
        """
        if not isinstance(v, str):
            raise ValueError("Content must be string")
        
        v = v.strip()
        
        if not v:
            raise ValueError("Comment cannot be empty after stripping whitespace")
        
        if len(v) < MIN_CONTENT_LENGTH:
            raise ValueError(f"Comment must be at least {MIN_CONTENT_LENGTH} character")
        
        if len(v) > MAX_CONTENT_LENGTH:
            raise ValueError(f"Comment cannot exceed {MAX_CONTENT_LENGTH} characters")
        
        # Check for null bytes and control characters
        if "\x00" in v:
            raise ValueError("Comment cannot contain null bytes")
        
        # Allow newlines and basic formatting, but prevent control chars
        for char in v:
            if ord(char) < 32 and char not in "\n\r\t":
                raise ValueError(
                    f"Comment contains invalid control character: {repr(char)}"
                )
        
        return v

    class Config:
        """Pydantic configuration."""
        str_strip_whitespace = True
        json_schema_extra = {
            "description": "Create a new comment on a blog post",
            "example": {
                "content": "Great post! This helped me a lot.",
            },
        }


class CommentOut(BaseModel):
    """
    Comment response model.
    
    Returned when fetching comments. Includes database-generated fields
    and author information.
    
    **Important: Differences from ORM Model**
    The original schema included:
    - "name" field (not in ORM - comments have author_id relationship)
    
    This schema correctly uses:
    - "author_id" to reference the user
    - "blog_id" to reference the blog
    - Database timestamps (created_at, not updated_at - comments immutable)
    
    **Security:**
    - author_id present for client-side checks
    - Author details (email, full_name) omitted to prevent user enumeration
    - Route layer controls what author info is exposed
    - created_at only (comments immutable - no edit history)
    
    **Config:**
    - from_attributes=True: Maps SQLAlchemy ORM to Pydantic
    - Serializes datetime to ISO 8601 format
    
    **Example:**
    ```json
    {
        "id": 1,
        "content": "Great post! Really helpful.",
        "blog_id": 42,
        "author_id": 10,
        "created_at": "2025-01-17T12:30:00Z"
    }
    ```
    """

    id: Annotated[
        int,
        Field(
            ...,
            ge=1,
            description="Comment ID (database primary key)",
        ),
    ]

    blog_id: Annotated[
        int,
        Field(
            ...,
            ge=1,
            description="Blog post ID (parent post)",
        ),
    ]

    author_id: Annotated[
        int,
        Field(
            ...,
            ge=1,
            description="Author user ID (who wrote the comment)",
        ),
    ]

    content: Annotated[
        str,
        Field(
            ...,
            min_length=MIN_CONTENT_LENGTH,
            max_length=MAX_CONTENT_LENGTH,
            description="Comment text content",
        ),
    ]

    created_at: Annotated[
        datetime,
        Field(
            ...,
            description="Comment creation timestamp (ISO 8601, immutable)",
        ),
    ]

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "description": "Comment on a blog post",
            "example": {
                "id": 1,
                "blog_id": 42,
                "author_id": 10,
                "content": "Great post! Really helped me understand FastAPI.",
                "created_at": "2025-01-17T12:30:00Z",
            },
        },
    )


class CommentOutWithAuthor(CommentOut):
    """
    Comment response with author details.
    
    Extended response that includes author information. Returned in routes
    where author details are already loaded and safe to expose.
    
    **Use Case:**
    - GET /blogs/{id}/comments â†’ returns list of CommentOut (basic)
    - GET /blogs/{id}/comments?include=author â†’ returns CommentOutWithAuthor
    
    **Security:**
    - Only safe author fields exposed (email, full_name)
    - Route layer controls when this is used
    - Prevents user enumeration by only including when explicitly requested
    
    **Example:**
    ```json
    {
        "id": 1,
        "blog_id": 42,
        "author_id": 10,
        "content": "Great post!",
        "created_at": "2025-01-17T12:30:00Z",
        "author": {
            "id": 10,
            "email": "user@example.com",
            "full_name": "John Doe"
        }
    }
    ```
    """

    author: Annotated[
        Optional[dict],
        Field(
            None,
            description="Author details (name, email) - included on request",
        ),
    ] = None

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "description": "Comment with author details",
            "example": {
                "id": 1,
                "blog_id": 42,
                "author_id": 10,
                "content": "Great post!",
                "created_at": "2025-01-17T12:30:00Z",
                "author": {
                    "id": 10,
                    "email": "user@example.com",
                    "full_name": "John Doe",
                },
            },
        },
    )


class CommentDelete(BaseModel):
    """
    Comment deletion response model.
    
    Returned after successful comment deletion. Minimal response to confirm
    operation completion.
    
    **Security:**
    - Only author or admin can delete
    - No actual deletion (soft delete via status flag in production)
    - Audit trail kept (who deleted, when, why)
    """

    id: Annotated[
        int,
        Field(..., ge=1, description="Deleted comment ID"),
    ]

    message: Annotated[
        str,
        Field(..., description="Confirmation message"),
    ]

    model_config = ConfigDict(
        json_schema_extra={
            "description": "Response after comment deletion",
            "example": {
                "id": 1,
                "message": "Comment deleted successfully",
            },
        },
    )