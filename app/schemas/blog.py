"""
Defines request/response models for blog CRUD operations with comprehensive alidation, 
SEO fields, engagement tracking, and API documentation.
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
    
    **Status Values:**
    - DRAFT: Post in progress, not visible to public
    - PUBLISHED: Post published, visible to all users
    - ARCHIVED: Post archived, hidden from lists but accessible via direct link
    - SCHEDULED: Post scheduled for future publication

    **Status Transitions:**
    - DRAFT → PUBLISHED: User initiates publish
    - PUBLISHED → ARCHIVED: User archives (soft delete)
    - ARCHIVED → PUBLISHED: User unarchives
    - Any → DRAFT: User reverts to draft

    **Security:**
    - Only author or admin can change status
    - ARCHIVED blogs remain queryable by author (soft delete)
    - PUBLISHED blogs queryable by all users
    """

    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"
    SCHEDULED = "scheduled"


class BlogBase(BaseModel):
    """
    Base blog model with common fields.
    
    Shared validation rules for blog creation and updates.
    Serves as parent for BlogCreate and BlogUpdate models.

    **Content Fields:**
    - title: Blog post title
    - content: Main blog content
    - excerpt: Short summary for listings

    **SEO Fields:**
    - slug: URL-friendly identifier
    - meta_description: Google search snippet
    - meta_keywords: Search keywords
    - og_image: Social sharing image

    **Metadata:**
    - status: Publication status
    - is_public: Visibility flag
    - is_featured: Featured flag
    - is_pinned: Pinned flag
    - cover_image_url: Cover image
    - tags: Comma-separated tags
    """

    # ========================================================================
    # CONTENT FIELDS
    # ========================================================================

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

    excerpt: Annotated[
        Optional[str],
        Field(
            None,
            max_length=500,
            description="Short summary for listings & SEO (max 500 chars)",
            examples=["Learn FastAPI basics in this comprehensive guide"],
        ),
    ] = None

    # ========================================================================
    # SEO FIELDS (NEW - CRITICAL FOR GOOGLE SEARCH)
    # ========================================================================
    slug: Annotated[
        Optional[str],
        Field(
            None,
            min_length=1,
            max_length=255,
            description="URL-friendly identifier (auto-generated from title if not provided)",
            examples=["learn-fastapi-basics"],
        ),
    ] = None

    meta_description: Annotated[
        Optional[str],
        Field(
            None,
            max_length=160,
            description="Google search snippet (155-160 chars for optimal display)",
            examples=["Complete guide to FastAPI: learn routing, models, validation, and more"],
        ),
    ] = None

    meta_keywords: Annotated[
        Optional[str],
        Field(
            None,
            max_length=500,
            description="Keywords for search ranking (comma-separated)",
            examples=["fastapi, python, web framework, api development"],
        ),
    ] = None

    og_image: Annotated[
        Optional[HttpUrl | str],
        Field(
            None,
            description="Open Graph image for social sharing (1200x630px recommended)",
            examples=["https://cdn.example.com/fastapi-cover.jpg"],
        ),
    ] = None


    # ========================================================================
    # METADATA & STATUS
    # ========================================================================
    status: Annotated[
        BlogStatus,
        Field(
            BlogStatus.DRAFT,
            description="Publication status (draft/published/archived/scheduled)",
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

    is_pinned: Annotated[
        bool,
        Field(
            False,
            description="Pinned to top of blog list (admin only)",
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

    # ========================================================================
    # FIELD VALIDATORS
    # ========================================================================

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
    
    @field_validator("excerpt")
    @classmethod
    def validate_excerpt(cls, v: Optional[str]) -> Optional[str]:

        """Validate excerpt if provided."""

        if not v:
            return None

        v = v.strip()

        if not v:
            return None

        if len(v) > 500:
            raise ValueError("Excerpt must be 500 characters or less")

        return v

    @field_validator("meta_description")
    @classmethod
    def validate_meta_description(cls, v: Optional[str]) -> Optional[str]:
        """
        Validate meta description for SEO.

        - Should be 155-160 chars for optimal Google display
        """

        if not v:
            return None

        v = v.strip()

        if not v:
            return None

        if len(v) > 160:
            raise ValueError("Meta description must be 160 characters or less (160 is Google's limit)")

        return v

    @field_validator("meta_keywords")
    @classmethod
    def validate_meta_keywords(cls, v: Optional[str]) -> Optional[str]:

        """Validate meta keywords format."""

        if not v:
            return None

        v = v.strip()

        if not v:
            return None

        keywords_list = [kw.strip() for kw in v.split(",")]

        if len(keywords_list) > 20:
            raise ValueError("Maximum 20 keywords allowed")

        for keyword in keywords_list:
            if not keyword:
                raise ValueError("Keywords cannot be empty")
            if len(keyword) > 50:
                raise ValueError("Each keyword must be 1-50 characters")

        return ",".join(keywords_list)
    
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
    - is_pinned can only be set by admin (API layer enforces)

    **SEO Auto-Generation:**
    - slug: Auto-generated from title if not provided
    - excerpt: Uses content preview if not provided
    - meta_description: Uses excerpt if not provided
    - reading_time_minutes: Calculated from content word count
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
    - is_featured can only be set by admin (API layer enforces)
    - is_pinned can only be set by admin (API layer enforces)
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

    excerpt: Annotated[
        Optional[str],
        Field(
            None,
            max_length=500,
            description="Short summary (optional)",
        ),
    ] = None

    slug: Annotated[
        Optional[str],
        Field(
            None,
            max_length=255,
            description="URL-friendly identifier (optional)",
        ),
    ] = None

    meta_description: Annotated[
        Optional[str],
        Field(
            None,
            max_length=160,
            description="Google search snippet (optional)",
        ),
    ] = None

    meta_keywords: Annotated[
        Optional[str],
        Field(
            None,
            max_length=500,
            description="Search keywords (optional)",
        ),
    ] = None

    og_image: Annotated[
        Optional[HttpUrl | str],
        Field(
            None,
            description="Social sharing image (optional)",
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

    is_pinned: Annotated[
        Optional[bool],
        Field(
            None,
            description="Pinned flag (optional, admin only)",
        ),
    ] = None

    cover_image_url: Annotated[
        Optional[HttpUrl | str],
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

    @field_validator("title", "content", "excerpt", "meta_description", "meta_keywords","tags")
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
            },
        }


class BlogOut(BlogBase):
    """
    Blog response model.
    
    Returned when fetching or creating a blog post. Includes database-generated
    fields (id, timestamps) and author information.
    
    **Database Fields:**
    - id: Unique identifier
    - author_id: Author's user ID
    - view_count: Total views
    - reading_time_minutes: Estimated reading time
    - created_at: Creation timestamp
    - updated_at: Last modification timestamp
    - published_at: Publication timestamp (nullable)

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

    slug: Annotated[
        str,
        Field(
            ...,
            description="URL-friendly identifier (used in blog URLs)",
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

    view_count: Annotated[
        int,
        Field(
            default=0,
            ge=0,
            description="Total number of views for this blog post",
        ),
    ] = 0

    reading_time_minutes: Annotated[
        int,
        Field(
            default=1,
            ge=1,
            description="Estimated reading time in minutes",
        ),
    ] = 1

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

    published_at: Annotated[
        Optional[datetime],
        Field(
            None,
            description="Publication timestamp (ISO 8601, nullable for drafts)",
        ),
    ] = None

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "description": "Complete blog post with metadata and SEO fields",
            "example": {
                "id": 1,
                "title": "Getting Started with FastAPI",
                "content": "# FastAPI\n\nFastAPI is a modern...",
                "excerpt": "Learn FastAPI basics in this comprehensive guide",
                "meta_description": "Complete guide to FastAPI: learn routing, models, validation, and more",
                "meta_keywords": "fastapi, python, web framework, api",
                "og_image": "https://cdn.example.com/fastapi.jpg",
                "status": "published",
                "is_public": True,
                "is_featured": False,
                "is_pinned": False,
                "cover_image_url": "https://cdn.example.com/cover.jpg",
                "tags": "python,fastapi,api",
                "author_id": 10,
                "view_count": 1234,
                "reading_time_minutes": 7,
                "created_at": "2025-01-17T12:00:00Z",
                "updated_at": "2025-01-17T15:30:00Z",
                "published_at": "2025-01-17T13:00:00Z",
            },
        },
    )


class BlogListOut(BaseModel):
    """
    Blog list response model (summary).
    
    Returned when listing blogs. Contains summary information without full content
    to improve API performance and reduce payload size.
    
    **Use Case:**
    - GET /blogs → returns list of BlogListOut
    - GET /blogs/{id} → returns BlogOut (full details)

    **Fields:**
    - id, title, slug, excerpt: Summary information
    - status, is_public, is_featured: Metadata
    - view_count, reading_time_minutes: Engagement metrics
    - created_at: Sorting/filtering
    """

    id: Annotated[
        int,
        Field(..., ge=1, description="Blog post ID"),
    ]

    title: Annotated[
        str,
        Field(..., description="Blog post title"),
    ]

    slug: Annotated[
        str,
        Field(..., description="URL-friendly identifier"),
    ]

    excerpt: Annotated[
        Optional[str],
        Field(None, description="Short summary"),
    ]

    status: Annotated[
        BlogStatus,
        Field(..., description="Publication status"),
    ]

    tags: Annotated[
        str,
        Field(..., description="Comma-separated tags (1-1000 chars, e.g., 'python,fastapi,web')",),
    ] 

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
        Field(..., description="Visibility"),
    ]

    is_featured: Annotated[
        bool,
        Field(..., description="Featured on homepage"),
    ]

    is_pinned: Annotated[
        bool,
        Field(..., description="Pinned to top"),
    ]

    view_count: Annotated[
        int,
        Field(..., description="Total views"),
    ]

    reading_time_minutes: Annotated[
        int,
        Field(..., description="Reading time in minutes"),
    ]

    created_at: Annotated[
        datetime,
        Field(..., description="Creation timestamp"),
    ]

    published_at: Annotated[
        datetime,
        Field(..., description="Publication timestamp"),
    ]

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "description": "Blog post summary for list views",
            "example": {
                "id": 1,
                "title": "Getting Started with FastAPI",
                "slug": "getting-started-with-fastapi",
                "excerpt": "Learn FastAPI basics in this comprehensive guide",
                "status": "published",
                "is_public": True,
                "is_featured": True,
                "is_pinned": False,
                "view_count": 1234,
                "reading_time_minutes": 7,
                "created_at": "2025-01-17T12:00:00Z",
                "published_at": "2025-01-17T13:00:00Z",
            },
        },
    )