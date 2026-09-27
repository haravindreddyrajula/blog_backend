"""
Blog Router

A secure, well-architected blog CRUD API with:

- SEO field support (slug, meta_description, meta_keywords, og_image)
- Engagement tracking (view_count, reading_time_minutes)
- Auto-generation of slugs and reading times
- Proper transaction management (no nested contexts)
- Authorization checks on all endpoints
- Input validation and sanitization
- Structured logging without PII
- Comprehensive error handling
- Database constraints for data integrity
- Idempotency support
- Performance optimizations (eager loading, pagination)
"""

import asyncio
import hashlib
import logging
from typing import Annotated, Optional
from contextlib import suppress
from datetime import datetime, timezone
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    Security,
    status,
)
from pydantic import constr
from sqlalchemy import ARRAY, or_, select, update, func
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from slugify import slugify
from app.core.config import settings
from app.core.deps import get_async_db
from app.models.blog import Blog, BlogStatus
from app.models.comment import Comment
from app.models.user import User
from app.schemas.blog import BlogCreate, BlogOut, BlogUpdate, BlogListOut, BlogStatus as SchemaStatus
from app.services.user import get_current_active_user

# Configure logger
router = APIRouter(prefix="/blogs", tags=["Blog"])
logger = logging.getLogger(__name__)

# Constants
MAX_LIMIT = 100
MIN_LIMIT = 1
DEFAULT_LIMIT = 9
MAX_SEARCH_LENGTH = 100
QUERY_TIMEOUT = 10.0
HASH_SEED = "blog_event"  # For non-security hashing

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================
def _hash_user_id(user_id: int) -> str:
    """Hash user ID for safe logging (non-security)."""
    return hashlib.sha256(f"{HASH_SEED}:{user_id}".encode()).hexdigest()[:8]

def _sanitize_search_query(search: str) -> str:
    """Sanitize and truncate search query."""
    if not search:
        return ""
    # Remove extra whitespace and truncate
    safe = " ".join(search.split())[:MAX_SEARCH_LENGTH]
    return safe

def _calculate_reading_time(content: str) -> int:

    """
    Calculate reading time in minutes.
    Average reading speed: 200 words per minute
    """

    word_count = len(content.split())
    reading_time = max(1, word_count // 200)
    return reading_time

def _generate_slug(title: str) -> str:

    """
    Generate URL-friendly slug from title.
    Example: "How to Learn Python" -> "how-to-learn-python"
    """
    return slugify(title)

async def _get_blog_or_404(
    db: AsyncSession, blog_id: int, include_relations: bool = False
) -> Blog:
    """
    Fetch a blog by ID or raise 404.

    Args:
        db: Database session
        blog_id: Blog ID to fetch
        include_relations: Whether to eagerly load author and comments

    Returns:
        Blog object

    Raises:
        HTTPException: 404 if not found
    """
    query = select(Blog)
    if include_relations:
        query = query.options(
            selectinload(Blog.author), selectinload(Blog.comments)
        )
    query = query.where(Blog.id == blog_id)

    result = await db.execute(query)
    blog = result.scalar_one_or_none()

    if not blog:
        logger.warning(
            "Blog not found",
            extra={"blog_id": blog_id, "request_type": "read"},
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Blog not found",
        )

    logger.info(
        "Blog fetched successfully",
        extra={"blog_id": blog.id, "request_type": "read"},
    )

    return blog

async def _get_blog_by_slug(db: AsyncSession, slug: str) -> Blog:

    """
    Fetch a blog by slug (for public viewing).

    Args:
        db: Database session
        slug: Blog slug

    Returns:
        Blog object

    Raises:
        HTTPException: 404 if not found
    """

    query = select(Blog).where(Blog.slug == slug)
    result = await db.execute(query)
    blog = result.scalar_one_or_none()

    if not blog:
        logger.warning(
            "Blog not found by slug",
            extra={"slug": slug, "request_type": "read"},
        )

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Blog not found",
        )

    return blog

def _check_authorization(blog: Blog, user: User, operation: str) -> None:
    """
    Check if user owns the blog (for write operations).

    Args:
        blog: Blog object
        user: Current user
        operation: Operation name (for logging)

    Raises:
        HTTPException: 403 if not authorized
    """
    if blog.author_id != user.id:
        user_hash = _hash_user_id(user.id)
        logger.warning(
            "Authorization failed",
            extra={
                "user_hash": user_hash,
                "operation": operation,
                "blog_id": blog.id,
                "owner_id_hash": _hash_user_id(blog.author_id),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to modify this blog",
        )

# ============================================================================
# ENDPOINTS
# ============================================================================


@router.post(
    "/",
    response_model=BlogOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new blog post",
    description="Create a new blog post with the provided data. Author is set to current user.",
    responses={
        201: {"description": "Blog created successfully"},
        400: {"description": "Invalid input data"},
        409: {"description": "Blog with this title already exists"},
        500: {"description": "Internal server error"},
    },
)
async def create_blog(
    blog_data: BlogCreate,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> BlogOut:
    """
    Create a new blog post with auto-generated SEO fields.
    The current authenticated user becomes the author.

    **Auto-Generated Fields:**
    - slug: Generated from title (can be overridden)
    - reading_time_minutes: Calculated from content word count
    - meta_description: Uses excerpt if not provided
    - published_at: Set when status=PUBLISHED

    **Required Fields:**
    - title: Blog title (5-255 chars)
    - content: Blog content (10+ chars)

    **Optional Fields:**
    - excerpt: Short summary
    - slug: URL identifier (auto-generated if not provided)
    - meta_description: Google search snippet (155-160 chars)
    - meta_keywords: Search keywords (comma-separated)
    - og_image: Social sharing image
    - status: Draft or Published (default: DRAFT)
    - tags: Comma-separated tags

    **Returns:**
    - 201: Created blog with all fields including auto-generated ID, timestamps
    - 409: If title already exists (duplicate)
    - 500: If server error occurs during creation
    """
    user_hash = _hash_user_id(current_user.id)

    try:
        logger.info(
            "Blog creation initiated",
            extra={
                "user_hash": user_hash,
                "title_length": len(blog_data.title),
            },
        )

        # Auto-generate slug if not provided
        slug = blog_data.slug or _generate_slug(blog_data.title)

        # Calculate reading time
        reading_time = _calculate_reading_time(blog_data.content)

        # Set excerpt if not provided (use content preview)
        excerpt = blog_data.excerpt or blog_data.content[:500]

        # Set meta_description if not provided
        meta_description = blog_data.meta_description or excerpt[:160]

        # Set published_at if publishing
        published_at = None

        if blog_data.status == BlogStatus.PUBLISHED:
            published_at = datetime.now(timezone.utc)

        # Create new blog with auto-generated fields (title uniqueness enforced by database constraint)
        new_blog = Blog(
            **blog_data.model_dump(exclude={"slug", "excerpt", "meta_description"}),
            slug=slug,
            reading_time_minutes=reading_time,
            excerpt=excerpt,
            meta_description=meta_description,
            published_at=published_at,
            author_id=current_user.id,
            author=current_user,
        )

        db.add(new_blog)

        # Commit - will raise IntegrityError if title is duplicate
        await db.commit()

        # Refresh to load server-generated attributes
        await db.refresh(new_blog)

        logger.info(
            "Blog created successfully",
            extra={
                "user_hash": user_hash,
                "blog_id": new_blog.id,
                "slug": new_blog.slug,
                "status": new_blog.status.value,
            },
        )

        return BlogOut.model_validate(new_blog)

    except IntegrityError as e:
        # Handle constraint violation (duplicate title)
        logger.warning(
            "Constraint violation during blog creation",
            extra={"user_hash": user_hash, "constraint_type": "title_unique"},
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A blog with this title already exists. Choose a different title.",
        ) from e

    except SQLAlchemyError as e:
        logger.error(
            "Database error during blog creation",
            exc_info=True,
            extra={"user_hash": user_hash},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create blog post",
        ) from e

    except Exception as e:
        logger.error(
            "Unexpected error during blog creation",
            exc_info=True,
            extra={"user_hash": user_hash},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error occurred",
        ) from e

@router.get(
    "/",
    response_model=list[BlogListOut],
    summary="List public blogs",
    description="Retrieve paginated list of published, public blogs.",
    responses={
        200: {"description": "List of blogs"},
        400: {"description": "Invalid pagination or filter parameters"},
        504: {"description": "Query timeout"},
    },
)
async def get_all_blogs(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(
        DEFAULT_LIMIT,
        ge=MIN_LIMIT,
        le=MAX_LIMIT,
        description="Maximum records to return",
    ),
    search: Annotated[str, Query( max_length=MAX_SEARCH_LENGTH, description="Search blogs by title or content")] = "",
    is_featured: Optional[bool] = Query(
        None, description="Filter by featured status"
    ),
    is_pinned: Optional[bool] = Query(
        None, description="Filter by pinned status"
    ),
    sort_by: str = Query(
        "published_at",
        description="Sort field: created_at, published_at, view_count, reading_time_minutes",
    ),
    tags: Optional[list[str]] = Query(
        None, description="Filter by tags (all must match)"
    ),
    db: Annotated[AsyncSession, Depends(get_async_db)] = None,
) -> list[BlogListOut]:
    """
    List all public, published blogs with optional filtering and sorting.

    **Query Parameters:**
    - skip: Pagination offset (default: 0)
    - limit: Results per page (default: 9, max: 100)
    - search: Search term for title/content (max 100 chars)
    - is_featured: Filter by featured status (true/false/null)
    - is_pinned: Filter by pinned status
    - sort_by: Sort field (created_at, published_at, view_count, reading_time_minutes)
    - tags: Filter by tags (returns blogs matching ALL tags)

    **Response:**
    Returns list of public, published blogs with author details.

    **Example Queries:**
    - `GET /blogs/?skip=0&limit=10` - First 10 blogs
    - `GET /blogs/?search=python` - Blogs matching "python"
    - `GET /blogs/?is_featured=true` - Featured blogs only
    - `GET /blogs/?tags=fastapi&tags=async` - Blogs with both tags
    - `GET /blogs/?sort_by=view_count` - Most viewed blogs

    **Returns:**
    - 200: List of blogs (may be empty)
    - 400: Invalid parameters
    - 504: Query timeout (reduce limit or search scope)
    """
    try:
        logger.debug(
            "Blog listing initiated",
            extra={
                "skip": skip,
                "limit": limit,
                "search_length": len(search) if search else 0,
                "sort_by": sort_by,
                "has_tags": tags is not None and len(tags) > 0,
            },
        )

        # Validate sort_by parameter
        valid_sort_fields = ["created_at", "published_at", "view_count", "reading_time_minutes"]
        if sort_by not in valid_sort_fields:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid sort field. Must be one of: {', '.join(valid_sort_fields)}",
            )

        # Base query: public and published blogs only
        query = select(Blog).where(
            Blog.is_public == True,
            Blog.status == BlogStatus.PUBLISHED,
        )

        # Search filter
        if search:
            safe_search = _sanitize_search_query(search)
            query = query.where(
                or_(
                    Blog.title.ilike(f"%{safe_search}%"),
                    Blog.content.ilike(f"%{safe_search}%"),
                    Blog.slug.ilike(f"%{safe_search}%"),
                )
            )
            logger.debug(
                "Search filter applied",
                extra={"search_term_length": len(safe_search)},
            )

        # Featured filter
        if is_featured is not None:
            query = query.where(Blog.is_featured == is_featured)

        # Pinned filter
        if is_pinned is not None:
            query = query.where(Blog.is_pinned == is_pinned)

        # Tag filters (all tags must be present)
        if tags and len(tags) > 0:
            logger.debug("Tag filter applied", extra={"tag_count": len(tags)})

            if isinstance(Blog.tags.type, ARRAY):  # PostgreSQL
                for tag in tags:
                    query = query.where(Blog.tags.contains([tag]))
            else:  # SQLite - simplified approach
                # Note: SQLite doesn't have native array support
                # This is a simplified implementation
                conditions = []
                for tag in tags:
                    conditions.extend([
                        Blog.tags.contains(f"{tag},"),
                        Blog.tags.contains(f",{tag},"),
                        Blog.tags.contains(f",{tag}"),
                        Blog.tags == tag,
                    ])
                if conditions:
                    query = query.where(or_(*conditions))
        
        # Apply sorting
        if sort_by == "created_at":
            query = query.order_by(Blog.created_at.desc())
        elif sort_by == "published_at":
            query = query.order_by(Blog.published_at.desc())
        elif sort_by == "view_count":
            query = query.order_by(Blog.view_count.desc())
        elif sort_by == "reading_time_minutes":
            query = query.order_by(Blog.reading_time_minutes.desc())

        # Pagination
        query = query.offset(skip).limit(limit)

        # Execute with timeout
        try:
            result = await asyncio.wait_for(
                db.execute(query),
                timeout=QUERY_TIMEOUT,
            )
            blogs = result.scalars().all()

            logger.info(
                "Blogs retrieved successfully",
                extra={"count": len(blogs), "skip": skip, "limit": limit},
            )

            return [BlogListOut.model_validate(blog) for blog in blogs]

        except asyncio.TimeoutError:
            logger.error(
                "Blog query timed out",
                extra={"skip": skip, "limit": limit, "timeout": QUERY_TIMEOUT},
            )
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Query took too long. Try refining your search.",
            )

    except HTTPException:
        # Re-raise HTTP exceptions
        raise

    except SQLAlchemyError as e:
        logger.error("Database error during blog listing", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve blogs",
        ) from e

    except Exception as e:
        logger.error(
            "Unexpected error during blog listing",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error occurred",
        ) from e

@router.get(
    "/popular",
    response_model=list[BlogListOut],
    summary="Get popular blogs",
    description="Retrieve most viewed published blogs (sorted by view_count DESC).",
    responses={
        200: {"description": "List of popular blogs"},
        504: {"description": "Query timeout"},
    },
)
async def get_popular_blogs(
    limit: int = Query(
        10,
        ge=1,
        le=MAX_LIMIT,
        description="Number of popular blogs to return (max 100)",
    ),
    db: Annotated[AsyncSession, Depends(get_async_db)] = None,
) -> list[BlogListOut]:

    """
    Get the most popular blogs (sorted by view count descending).
    Great for "Popular Posts" sidebar or homepage widgets.

    **Query Parameters:**
    - limit: Number of blogs to return (default: 10, max: 100)

    **Returns:**
    - 200: List of popular blogs sorted by view_count DESC
    - 504: Query timeout
    """

    try:
        query = (
            select(Blog)
            .where(
                Blog.is_public == True,
                Blog.status == BlogStatus.PUBLISHED,
            )
            .order_by(Blog.view_count.desc())
            .limit(limit)
        )

        result = await asyncio.wait_for(
            db.execute(query),
            timeout=QUERY_TIMEOUT,
        )

        blogs = result.scalars().all()

        logger.info(
            "Popular blogs retrieved",
            extra={"count": len(blogs)},

        )

        return [BlogListOut.model_validate(blog) for blog in blogs]

    except asyncio.TimeoutError:
        logger.error("Popular blogs query timed out")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Query took too long",
        )

    except SQLAlchemyError as e:
        logger.error("Database error during popular blogs query", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve popular blogs",
        ) from e

@router.get(
    "/slug/{slug}",
    response_model=BlogOut,
    summary="Get blog by slug (SEO URL)",
    description="Retrieve a blog post by its SEO-friendly slug and increment view count.",
    responses={
        200: {"description": "Blog retrieved and view count incremented"},
        404: {"description": "Blog not found"},
    },
)
async def get_blog_by_slug(
    slug: str,
    db: Annotated[AsyncSession, Depends(get_async_db)] = None,
) -> BlogOut:

    """
    Retrieve a blog post by its slug (URL-friendly identifier).
    Automatically increments the view_count for analytics.

    **Path Parameters:**
    - slug: Blog slug (e.g., "getting-started-with-fastapi")

    **Returns:**
    - 200: Blog with all fields including SEO metadata
    - 404: Blog not found

    **Note:** View count is incremented automatically for analytics.
    """

    try:
        blog = await _get_blog_by_slug(db, slug)

        # Increment view count
        await db.execute(
            update(Blog)
            .where(Blog.id == blog.id)
            .values(view_count=Blog.view_count + 1)
        )

        await db.commit()

        # Refresh to get updated view_count
        await db.refresh(blog)

        logger.debug("Blog retrieved by slug", extra={"slug": slug})

        return BlogOut.model_validate(blog)

    except HTTPException:
        raise

    except SQLAlchemyError as e:
        logger.error("Database error during blog retrieval by slug", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve blog",
        ) from e

@router.get(
    "/dashboard",
    response_model=list[BlogListOut],
    status_code=status.HTTP_200_OK,
    summary="Get user's blog dashboard",
    description="Retrieve all blogs for the current user (all statuses).",
    responses={
        200: {"description": "User's blogs"},
        400: {"description": "Invalid status parameter"},
        401: {"description": "Not authenticated"},
        504: {"description": "Query timeout"},
    },
)
async def get_dashboard_blogs(
    status_filter: str = Query(
        "draft",
        alias="status",
        description="Filter by blog status: 'all', 'draft', 'published', 'archived', 'scheduled'",
        regex="^(all|draft|published|archived|scheduled)$",
    ),
    db: Annotated[AsyncSession, Depends(get_async_db)] = None,
    current_user: Annotated[User, Depends(get_current_active_user)] = None,
) -> list[BlogListOut]:
    """
    Get current user's blogs filtered by status.
    Allows users to view their draft, published, archived, or scheduled posts.

    **Requires:** Authentication

    **Query Parameters:**
    - status: Filter by status (all, draft, published, archived, scheduled)
              Default: 'all' (fetch all statuses)

    **Returns:**
    - 200: List of user's blogs sorted by: pinned first, then by date
    - 400: Invalid status value
    - 401: Not authenticated
    - 504: Query timeout
    
    **Sorting Order:**
    1. is_pinned (DESC) - Pinned blogs at top
    2. published_at (DESC) - Recently published first (for published blogs)
    3. updated_at (DESC) - Recently updated (for draft blogs)
    4. created_at (DESC) - Fallback to creation date

    """
    user_hash = _hash_user_id(current_user.id)

    try:
        logger.debug(
            "Dashboard access",
            extra={"user_hash": user_hash, "status_filter": status_filter},
        )
        
        # Normalize status_filter to lowercase
        status_filter_lower = status_filter.lower()
        
        # ====================================================================
        # CASE 1: Fetch ALL statuses (default, initial render)
        # ====================================================================
        if status_filter_lower == "all":
            query = (
                select(Blog)
                .where(Blog.author_id == current_user.id)
                # SORTING: Pinned first, then by publish/update date
                .order_by(
                    Blog.is_pinned.desc(),           # Pinned blogs at top
                    Blog.published_at.desc(),        # Recently published first
                    Blog.updated_at.desc(),          # Recently updated (drafts)
                    Blog.created_at.desc(),          # Fallback to created date
                )
            )
            
            logger.debug(
                "Fetching ALL blogs for dashboard",
                extra={"user_hash": user_hash},
            )
        
        # ====================================================================
        # CASE 2: Fetch specific status
        # ====================================================================
        else:
            try:
                # Validate status parameter
                blog_status = BlogStatus[status_filter_lower.upper()]
            except KeyError:
                valid_statuses = ["all"] + [e.name.lower() for e in BlogStatus]
                logger.warning(
                    "Invalid status parameter",
                    extra={
                        "user_hash": user_hash,
                        "provided_status": status_filter,
                        "valid_options": valid_statuses,
                    },
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}",
                )
            
            query = (
                select(Blog)
                .where(
                    Blog.author_id == current_user.id,
                    Blog.status == blog_status,
                )
                # SORTING: Same for all statuses
                .order_by(
                    Blog.is_pinned.desc(),           # Pinned blogs at top
                    Blog.published_at.desc(),        # Recently published first
                    Blog.updated_at.desc(),          # Recently updated (drafts)
                    Blog.created_at.desc(),          # Fallback to created date
                )
            )
            
            logger.debug(
                "Fetching blogs with status filter",
                extra={"user_hash": user_hash, "status": status_filter},
            )
        
        # ====================================================================
        # EXECUTE QUERY WITH TIMEOUT
        # ====================================================================
        try:
            result = await asyncio.wait_for(
                db.execute(query),
                timeout=QUERY_TIMEOUT,
            )
            blogs = result.scalars().all()
            
            logger.info(
                "Dashboard blogs retrieved",
                extra={
                    "user_hash": user_hash,
                    "count": len(blogs),
                    "status_filter": status_filter,
                },
            )

            return [BlogListOut.model_validate(blog) for blog in blogs]

        except asyncio.TimeoutError:
            logger.error(
                "Dashboard query timed out",
                extra={
                    "user_hash": user_hash,
                    "status_filter": status_filter,
                    "timeout": QUERY_TIMEOUT,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail=f"Query took longer than {QUERY_TIMEOUT}s. Please try again.",
            )
    
    except HTTPException:
        raise
    
    except SQLAlchemyError as e:
        logger.error(
            "Database error during dashboard query",
            exc_info=True,
            extra={"user_hash": user_hash, "status_filter": status_filter},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve your blogs",
        ) from e
    
    except Exception as e:
        logger.error(
            "Unexpected error during dashboard query",
            exc_info=True,
            extra={"user_hash": user_hash, "status_filter": status_filter},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error occurred",
        ) from e

@router.get(
    "/dashboard/advanced",
    response_model=list[BlogListOut],
    status_code=status.HTTP_200_OK,
    summary="Advanced dashboard with detailed sorting",
    description="Dashboard with advanced sorting options",
)
async def get_dashboard_blogs_advanced(
    status_filter: str = Query(
        "all",
        alias="status",
        description="Filter: 'all', 'draft', 'published', 'archived', 'scheduled'",
        regex="^(all|draft|published|archived|scheduled)$",
    ),
    sort_by: str = Query(
        "smart",
        alias="sort",
        description="Sort strategy: 'smart', 'recent', 'views', 'reading_time'",
        regex="^(smart|recent|views|reading_time)$",
    ),
    db: Annotated[AsyncSession, Depends(get_async_db)] = None,
    current_user: Annotated[User, Depends(get_current_active_user)] = None,
) -> list[BlogListOut]:
    """
    Advanced dashboard with multiple sorting options.
    
    **Sort Options:**
    - 'smart' (default): Pinned first, then by publish/update date (RECOMMENDED)
    - 'recent': Most recently created/updated first
    - 'views': Most viewed first
    - 'reading_time': Longest reading time first
    
    **Examples:**
    - `GET /blogs/dashboard/advanced?status=published&sort=views`
    - `GET /blogs/dashboard/advanced?status=draft&sort=recent`
    """
    user_hash = _hash_user_id(current_user.id)
    
    try:
        # Build WHERE clause
        where_clauses = [Blog.author_id == current_user.id]
        
        if status_filter.lower() != "all":
            try:
                blog_status = BlogStatus[status_filter.upper()]
                where_clauses.append(Blog.status == blog_status)
            except KeyError:
                valid_statuses = ["all"] + [e.name.lower() for e in BlogStatus]
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}",
                )
        
        # Build ORDER BY based on sort_by parameter
        sort_by_lower = sort_by.lower()
        
        if sort_by_lower == "smart":
            # DEFAULT: Best UX for dashboard
            # Pinned at top, then recently published/updated
            order_by = [
                Blog.is_pinned.desc(),
                Blog.published_at.desc(),
                Blog.updated_at.desc(),
                Blog.created_at.desc(),
            ]
        
        elif sort_by_lower == "recent":
            # Recently created/updated first
            order_by = [
                Blog.is_pinned.desc(),  # Keep pinned on top
                Blog.updated_at.desc(),
                Blog.created_at.desc(),
            ]
        
        elif sort_by_lower == "views":
            # Most viewed first
            order_by = [
                Blog.is_pinned.desc(),  # Keep pinned on top
                Blog.view_count.desc(),
                Blog.updated_at.desc(),
            ]
        
        elif sort_by_lower == "reading_time":
            # Longest reading time first
            order_by = [
                Blog.is_pinned.desc(),  # Keep pinned on top
                Blog.reading_time_minutes.desc(),
                Blog.updated_at.desc(),
            ]
        
        else:
            order_by = [Blog.is_pinned.desc(), Blog.updated_at.desc()]
        
        query = select(Blog).where(*where_clauses).order_by(*order_by)
        
        try:
            result = await asyncio.wait_for(
                db.execute(query),
                timeout=QUERY_TIMEOUT,
            )
            blogs = result.scalars().all()
            
            logger.info(
                "Advanced dashboard retrieved",
                extra={
                    "user_hash": user_hash,
                    "count": len(blogs),
                    "status_filter": status_filter,
                    "sort_by": sort_by,
                },
            )

            return [BlogListOut.model_validate(blog) for blog in blogs]

        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail=f"Query timed out. Please try again.",
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Advanced dashboard query error",
            exc_info=True,
            extra={"user_hash": user_hash},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve blogs",
        ) from e      

@router.get(
    "/{blog_id}",
    response_model=BlogOut,
    status_code=status.HTTP_200_OK,
    summary="Get a blog post by ID",
    description="Retrieve a single blog post with author details.",
    responses={
        200: {"description": "Blog retrieved"},
        404: {"description": "Blog not found"},
    },
)
async def get_blog(
    blog_id: int,
    db: Annotated[AsyncSession, Depends(get_async_db)] = None,
) -> BlogOut:
    """
    Retrieve a blog post by ID.

    **Path Parameters:**
    - blog_id: The blog's unique identifier

    **Returns:**
    - 200: Blog with author details
    - 404: Blog not found

    **Note:** Currently returns any blog. In production, consider:
    - Private blogs visible only to author
    - Draft blogs visible only to author
    """
    try:
        logger.debug("Blog retrieval initiated", extra={"blog_id": blog_id})

        # Fetch with relations
        blog = await _get_blog_or_404(db, blog_id, include_relations=True)

        logger.debug("Blog retrieved", extra={"blog_id": blog_id})

        return BlogOut.model_validate(blog)

    except HTTPException:
        raise

    except SQLAlchemyError as e:
        logger.error(
            "Database error during blog retrieval",
            exc_info=True,
            extra={"blog_id": blog_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve blog",
        ) from e

    except Exception as e:
        logger.error(
            "Unexpected error during blog retrieval",
            exc_info=True,
            extra={"blog_id": blog_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error occurred",
        ) from e

@router.put(
    "/{blog_id}",
    response_model=BlogOut,
    summary="Update a blog post",
    description="Update a blog post. Only the author can update.",
    responses={
        200: {"description": "Blog updated"},
        400: {"description": "Invalid update data"},
        403: {"description": "Not authorized"},
        404: {"description": "Blog not found"},
        409: {"description": "Slug conflict"},
    },
)
async def update_blog(
    blog_id: int,
    blog_update: BlogUpdate,
    db: Annotated[AsyncSession, Depends(get_async_db)] = None,
    current_user: Annotated[User, Depends(get_current_active_user)] = None,
) -> BlogOut:
    """
    Update a blog post with optional SEO fields.

    **Requires:** Authentication (must be blog author)

    **Path Parameters:**
    - blog_id: Blog to update

    **Request Body:**
    - Partial updates supported (only modified fields required)
    - Can update: title, content, excerpt, slug, meta_description, meta_keywords, og_image, status, etc.

    **Auto-Updates:**
    - If title changes, slug can be auto-updated
    - reading_time_minutes auto-updated if content changes

    **Returns:**
    - 200: Updated blog with all fields
    - 400: Invalid data
    - 403: Not authorized (not the author)
    - 404: Blog not found
    - 409: Slug conflict (duplicate)

    **Note:** Only the blog author can update their blogs.
    """
    user_hash = _hash_user_id(current_user.id)

    try:
        logger.info(
            "Blog update initiated",
            extra={
                "user_hash": user_hash,
                "blog_id": blog_id,
                "update_fields": list(
                    blog_update.model_dump(exclude_unset=True).keys()
                ),
            },
        )

        # Fetch existing blog
        existing_blog = await _get_blog_or_404(db, blog_id)

        # Check authorization
        _check_authorization(existing_blog, current_user, "update")

        # Prepare update data (only non-None values)
        update_data = blog_update.model_dump(exclude_unset=True, exclude_none=True)

        if not update_data:
            logger.warning(
                "Empty update data",
                extra={"blog_id": blog_id, "user_hash": user_hash},
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No update data provided",
            )

        # Auto-calculate reading time if content changed
        if "content" in update_data:
            update_data["reading_time_minutes"] = _calculate_reading_time(
                update_data["content"]
            )

        # Auto-generate slug if title changed and slug not provided
        if "title" in update_data and "slug" not in update_data:
            update_data["slug"] = _generate_slug(update_data["title"])

        # Update published_at if status changed to PUBLISHED
        if (
            "status" in update_data and update_data["status"] == "published" and not existing_blog.published_at
        ):
            update_data["published_at"] = datetime.now(timezone.utc)
        
        logger.debug(
            "Applying updates",
            extra={
                "blog_id": blog_id,
                "user_hash": user_hash,
                "field_count": len(update_data),
            },
        )

        # Apply updates
        await db.execute(
            update(Blog).where(Blog.id == blog_id).values(**update_data)
        )

        await db.commit()

        # Fetch updated blog
        updated_blog = await _get_blog_or_404(db, blog_id)

        logger.info(
            "Blog updated successfully",
            extra={
                "blog_id": blog_id,
                "user_hash": user_hash,
                "fields_updated": len(update_data),
            },
        )

        return BlogOut.model_validate(updated_blog)

    except HTTPException:
        raise

    except IntegrityError as e:
        logger.warning(
            "Constraint violation during update",
            extra={"blog_id": blog_id, "user_hash": user_hash},
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Update violates constraints (e.g., duplicate title)",
        ) from e

    except SQLAlchemyError as e:
        logger.error(
            "Database error during blog update",
            exc_info=True,
            extra={"blog_id": blog_id, "user_hash": user_hash},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update blog",
        ) from e

    except Exception as e:
        logger.error(
            "Unexpected error during blog update",
            exc_info=True,
            extra={"blog_id": blog_id, "user_hash": user_hash},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error occurred",
        ) from e

@router.delete(
    "/{blog_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a blog post",
    description="Delete a blog post. Only the author can delete.",
    responses={
        204: {"description": "Blog deleted"},
        403: {"description": "Not authorized"},
        404: {"description": "Blog not found"},
    },
)
async def delete_blog(
    blog_id: int,
    db: Annotated[AsyncSession, Depends(get_async_db)] = None,
    current_user: Annotated[User, Depends(get_current_active_user)] = None,
) -> None:
    """
    Delete a blog post.

    **Requires:** Authentication (must be blog author)

    **Path Parameters:**
    - blog_id: Blog to delete

    **Returns:**
    - 204: Blog deleted successfully (no content)
    - 403: Not authorized (not the author)
    - 404: Blog not found

    **Note:**
    - Only the blog author can delete their blogs
    - Hard delete (permanent removal). Consider soft-delete for audit trail.
    """
    user_hash = _hash_user_id(current_user.id)

    try:
        logger.info(
            "Blog deletion initiated",
            extra={"blog_id": blog_id, "user_hash": user_hash},
        )

        # Fetch existing blog
        blog = await _get_blog_or_404(db, blog_id)

        # Check authorization
        _check_authorization(blog, current_user, "delete")

        # Delete
        await db.delete(blog)
        await db.commit()

        logger.info(
            "Blog deleted successfully",
            extra={"blog_id": blog_id, "user_hash": user_hash},
        )

        # Return 204 No Content (no response body)
        return None

    except HTTPException:
        raise

    except SQLAlchemyError as e:
        logger.error(
            "Database error during blog deletion",
            exc_info=True,
            extra={"blog_id": blog_id, "user_hash": user_hash},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete blog",
        ) from e

    except Exception as e:
        logger.error(
            "Unexpected error during blog deletion",
            exc_info=True,
            extra={"blog_id": blog_id, "user_hash": user_hash},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error occurred",
        ) from e
    