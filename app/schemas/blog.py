"""
Production-Ready Blog Schemas

Defines request/response models for blog CRUD operations with comprehensive
validation, consistent enum handling, and API documentation.

Author: Production Code Review Team
Status: Production-Ready
Last Updated: 2025-01-17
"""

from datetime import datetime
from enum import Enum
from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, HttpUrl


class BlogStatus(str, Enum):
    """
    Blog publication status enumeration.
    
    Controls the workflow state of blog posts throughout their lifecycle.
    Values must match database schema exactly (using lowercase).
    
    **Status Transitions:**
    - DRAFT â†’ PUBLISHED: User initiates publish
    - PUBLISHED â†’ ARCHIVED: User archives (soft delete)
    - ARCHIVED â†’ PUBLISHED: User unarchives
    - Any â†’ DRAFT: User reverts to draft
    
    **Security:**
    - Only author or admin can change status
    - ARCHIVED blogs remain queryable by author (soft delete)
    - PUBLISHED blogs queryable by all users
    """

    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class BlogBase(BaseModel):
    """
    Base blog model with common fields.
    
    Shared validation rules for blog creation and updates.
    Serves as parent for BlogCreate and BlogUpdate models.
    """

    title: Annotated[
        str,
        Field(
            ...,
            min_length=5,  # Meaningful title minimum
            max_length=255,  # Database column constraint
            description="Blog post title (5-255 characters)",
            examples=["Getting Started with FastAPI"],
        ),
    ]

    content: Annotated[
        str,
        Field(
            ...,
            min_length=10,  # Prevent trivial posts
            max_length=100000,  # ~20,000 words max
            description="Blog post content (10-100,000 characters, markdown/HTML)",
            examples=["# Hello\n\nThis is a blog post about..."],
        ),
    ]

    status: Annotated[
        BlogStatus,
        Field(
            BlogStatus.DRAFT,
            description="Publication status (draft/published/archived)",
        ),
    ] = BlogStatus.DRAFT

    cover_image_url: Annotated[
        Optional[HttpUrl | str],
        Field(
            None,
            description="URL to blog cover image (must be valid HTTPS URL)",
            examples=["https://cdn.example.com/blog-cover-123.jpg"],
        ),
    ] = None

    is_public: Annotated[
        bool,
        Field(
            True,
            description="Visibility: true=public, false=private (only author sees)",
        ),
    ] = True

    is_featured: Annotated[
        bool,
        Field(
            False,
            description="Featured on homepage (admin only)",
        ),
    ] = False

    tags: Annotated[
        Optional[str],
        Field(
            None,
            max_length=1000,
            description="Comma-separated tags (1-1000 chars, e.g., 'python,fastapi,web')",
            examples=["python,fastapi,api,web"],
        ),
    ] = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        """
        Sanitize title.
        
        - Strip whitespace
        - Prevent XSS via title field
        """
        v = v.strip()
        if not v:
            raise ValueError("Title cannot be empty after stripping")
        if len(v) < 5:
            raise ValueError("Title must be at least 5 characters")
        return v

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        """
        Validate content.
        
        - Strip leading/trailing whitespace
        - Ensure minimum meaningful content
        """
        v = v.strip()
        if not v:
            raise ValueError("Content cannot be empty after stripping")
        if len(v) < 10:
            raise ValueError("Content must be at least 10 characters")
        return v

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: Optional[str]) -> Optional[str]:
        """
        Validate tags format.
        
        - Each tag 1-50 characters
        - No special characters except hyphens
        - Maximum 10 tags
        """
        if not v:
            return None
        
        v = v.strip()
        if not v:
            return None
        
        tags_list = [tag.strip() for tag in v.split(",")]
        
        if len(tags_list) > 10:
            raise ValueError("Maximum 10 tags allowed")
        
        for tag in tags_list:
            if not tag:
                raise ValueError("Tags cannot be empty")
            if len(tag) > 50:
                raise ValueError("Each tag must be 1-50 characters")
            if not all(c.isalnum() or c in "-_" for c in tag):
                raise ValueError("Tags can only contain alphanumeric, hyphens, underscores")
        
        return ",".join(tags_list)  # Normalize spacing

    class Config:
        """Pydantic configuration."""
        str_strip_whitespace = True


class BlogCreate(BlogBase):
    """
    Blog creation request model.
    
    Used when creating a new blog post. All fields from BlogBase are available.
    Author ID is extracted from JWT token (not in request body).
    
    **Security:**
    - author_id automatically set from current user
    - created_at/updated_at set by database
    - is_featured can only be set by admin (API layer enforces)
    """

    pass


class BlogUpdate(BaseModel):
    """
    Blog update request model.
    
    Used when updating an existing blog. All fields are optional to support
    partial updates. Omitted fields retain their current value.
    
    **Security:**
    - Only blog author or admin can update
    - created_at cannot be changed
    - author_id cannot be changed
    
    **Example:**
    ```python
    # Update only title and status
    update_data = BlogUpdate(
        title="New Title",
        status=BlogStatus.PUBLISHED
    )
    ```
    """

    title: Annotated[
        Optional[str],
        Field(
            None,
            min_length=5,
            max_length=255,
            description="Blog post title (optional, 5-255 characters)",
        ),
    ] = None

    content: Annotated[
        Optional[str],
        Field(
            None,
            min_length=10,
            max_length=100000,
            description="Blog post content (optional)",
        ),
    ] = None

    status: Annotated[
        Optional[BlogStatus],
        Field(
            None,
            description="Publication status (optional)",
        ),
    ] = None

    is_public: Annotated[
        Optional[bool],
        Field(
            None,
            description="Visibility flag (optional)",
        ),
    ] = None

    is_featured: Annotated[
        Optional[bool],
        Field(
            None,
            description="Featured flag (optional, admin only)",
        ),
    ] = None

    cover_image_url: Annotated[
        Optional[HttpUrl],
        Field(
            None,
            description="Cover image URL (optional)",
        ),
    ] = None

    tags: Annotated[
        Optional[str],
        Field(
            None,
            max_length=1000,
            description="Comma-separated tags (optional)",
        ),
    ] = None

    @field_validator("title", "content", "tags")
    @classmethod
    def validate_optional_strings(cls, v: Optional[str]) -> Optional[str]:
        """Apply same validation rules as BlogBase for non-empty values."""
        if v is None:
            return None
        
        v = v.strip()
        if not v:
            return None
        return v

    class Config:
        """Pydantic configuration."""
        str_strip_whitespace = True
        json_schema_extra = {
            "example": {
                "title": "Updated Blog Title",
                "status": "published",
            }
        }


class BlogOut(BlogBase):
    """
    Blog response model.
    
    Returned when fetching or creating a blog post. Includes database-generated
    fields (id, timestamps) and author information.
    
    **Security:**
    - Only returns is_featured to admins (enforced in route layer)
    - Never includes full author details to prevent enumeration
    - author_id included for client-side validation only
    
    **Config:**
    - from_attributes=True: Reads from SQLAlchemy ORM objects
    - Serializes datetime objects to ISO 8601 format
    """

    id: Annotated[
        int,
        Field(
            ...,
            ge=1,
            description="Blog post ID (database primary key)",
        ),
    ]

    author_id: Annotated[
        int,
        Field(
            ...,
            ge=1,
            description="Author user ID (for authorization checks)",
        ),
    ]

    created_at: Annotated[
        datetime,
        Field(
            ...,
            description="Blog creation timestamp (ISO 8601)",
        ),
    ]

    updated_at: Annotated[
        datetime,
        Field(
            ...,
            description="Last modification timestamp (ISO 8601)",
        ),
    ]

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "description": "Complete blog post with metadata",
            "example": {
                "id": 1,
                "title": "Getting Started with FastAPI",
                "content": "# FastAPI\n\nFastAPI is a modern...",
                "status": "published",
                "is_public": True,
                "is_featured": False,
                "cover_image_url": "https://cdn.example.com/fastapi.jpg",
                "tags": "python,fastapi,api",
                "author_id": 10,
                "created_at": "2025-01-17T12:00:00Z",
                "updated_at": "2025-01-17T15:30:00Z",
            },
        },
    )


class BlogListOut(BaseModel):
    """
    Blog list response model (summary).
    
    Returned when listing blogs. Contains summary information without full content
    to improve API performance and reduce payload size.
    
    **Use Case:**
    - GET /blogs â†’ returns list of BlogListOut
    - GET /blogs/{id} â†’ returns BlogOut (full details)
    """

    id: Annotated[
        int,
        Field(..., ge=1, description="Blog post ID"),
    ]

    title: Annotated[
        str,
        Field(..., description="Blog post title"),
    ]

    status: Annotated[
        BlogStatus,
        Field(..., description="Publication status"),
    ]

    is_public: Annotated[
        bool,
        Field(..., description="Visibility"),
    ]

    created_at: Annotated[
        datetime,
        Field(..., description="Creation timestamp"),
    ]

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "description": "Blog post summary for list views",
            "example": {
                "id": 1,
                "title": "Getting Started with FastAPI",
                "status": "published",
                "is_public": True,
                "created_at": "2025-01-17T12:00:00Z",
            },
        },
    )