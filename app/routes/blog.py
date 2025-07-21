import asyncio
import logging
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Security, status
from sqlalchemy import ARRAY, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models.user import User
from app.schemas.blog import BlogCreate, BlogOut, BlogUpdate
from app.models.blog import Blog, BlogStatus
from app.models.comment import Comment
from app.core.deps import get_async_db
from app.services.user import get_current_active_user

router = APIRouter(prefix="/blogs", tags=["Blog"])

logger = logging.getLogger(__name__)

#TODO: token payload, while create access token not inserting scopes
@router.post(
        "/", 
        response_model=BlogOut,
        status_code=status.HTTP_201_CREATED
        # ,dependencies=[Security(get_current_active_user, scopes=["blog:write"])]
)
async def create_blog(
    blog_data: BlogCreate, 
    db: Annotated[AsyncSession, Depends(get_async_db)], 
    current_user: Annotated[User, Depends(get_current_active_user)]
) -> BlogOut:
    """Create new blog post with authorization checks"""
    async with db as session:
        try:

            logger.info(f"Received Create blog request from : {current_user.full_name} with title : {blog_data.title}")

            # Check for existing blog
            existing_blog = await session.scalar(
                select(Blog).where(Blog.title == blog_data.title)
            )
            
            if existing_blog is not None:
                logger.error(f"Blog with title: {blog_data.title}, already exists")
                raise HTTPException( status_code=status.HTTP_226_IM_USED, detail=f"Blog with title: {blog_data.title}, already exists")
            
            new_blog = Blog(
                **blog_data.model_dump(exclude_unset=True),
                author_id = current_user.id,
                author=current_user  # Assign entire user object
            )

            session.add(new_blog)
            await session.commit()

            # return BlogOut.model_validate(new_blog)

            # Refresh to load server-generated attributes
            await session.refresh(new_blog)
            
            # Eager load author relationship
            await session.execute(
                select(Blog)
                .options(selectinload(Blog.author))
                .where(Blog.id == new_blog.id)
            )
            
            logger.info(f"Successfully created blog with title: {blog_data.title}")
            return BlogOut.model_validate(new_blog)
            
        except HTTPException:
            raise  # Re-raise HTTP exceptions
        except Exception as e:
            await session.rollback()
            logger.error(f"Failed to create blog post for title {blog_data.title}: {str(e)}")
            raise HTTPException( status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create blog post: {str(e)}") from e

@router.get("/", response_model=list[BlogOut])
async def get_all_blogs(
    skip: int = 0,
    limit: int = 9,
    search: str = "",
    is_featured: Optional[bool] = None,
    tags: Optional[list[str]] = Query(None),
    db: AsyncSession = Depends(get_async_db)
):
    async with db as session:
        try:
            # Base query for published, public blogs
            query = (
                select(Blog)
                .where(
                    Blog.is_public == True,
                    Blog.status == BlogStatus.PUBLISHED
                )
                .order_by(Blog.created_at.desc())
                .offset(skip)
                .limit(limit)
            )
            logger.info(f"Pagination - skip: {skip}, limit: {limit}")

            # Add search filter if provided
            if search:
                logger.info(f"Searching blogs with term: '{search}'")
                query = query.where(
                    or_(
                        Blog.title.ilike(f"%{search}%"),
                        Blog.content.ilike(f"%{search}%")
                    )
                )
            
            # Filter by featured status
            if is_featured is not None:
                query = query.where(Blog.is_featured == is_featured)

            if tags:
                logger.info(f"Filtering by tags: {tags}")
                if isinstance(Blog.tags.type, ARRAY):  # PostgreSQL
                    for tag in tags:
                        query = query.where(Blog.tags.contains([tag]))
                else:  # SQLite
                    conditions = []
                    for tag in tags:
                        conditions.extend([
                            Blog.tags.contains(f"{tag},"),
                            Blog.tags.contains(f",{tag},"),
                            Blog.tags.contains(f",{tag}"),
                            Blog.tags == tag
                        ])
                    query = query.where(or_(*conditions))

            # Execute query
            # result = await session.execute(query)
            # blogs = result.scalars().all()

            # Execute query with timeout
            try:
                result = await asyncio.wait_for(
                    session.execute(query),
                    timeout=10.0  # 10 second timeout
                )
                blogs = result.scalars().all()
            except asyncio.TimeoutError:
                logger.error("Database query timed out")
                raise HTTPException(
                    status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                    detail="Database operation timed out"
                )

            logger.info(f"Fetched {len(blogs)} public & published blogs")

            # Convert to Pydantic models using model_validate
            return [BlogOut.model_validate(blog) for blog in blogs]
            
        except Exception as e:
            logger.error(f"Failed to fetch blogs: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch blogs"
            ) from e

@router.get("/dashboard", response_model=list[BlogOut], status_code=status.HTTP_200_OK, dependencies=[Security(get_current_active_user)])     
async def get_dashboard_blogs(db: Annotated[AsyncSession, Depends(get_async_db)]):
    async with db as session:
        try:
            query = (
                select(Blog)
                .where(
                    Blog.status == BlogStatus.DRAFT
                )
                .order_by(Blog.created_at.desc())
            )

            # Execute query with timeout
            try:
                result = await asyncio.wait_for(
                    session.execute(query),
                    timeout=10.0  # 10 second timeout
                )
                blogs = result.scalars().all()
            except asyncio.TimeoutError:
                logger.error("Database query timed out")
                raise HTTPException(
                    status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                    detail="Database operation timed out"
                )
            
            logger.info(f"Fetched {len(blogs)} draft blogs for dashboard")

            # Convert to Pydantic models using model_validate
            return [BlogOut.model_validate(blog) for blog in blogs]
        
        except Exception as e:
            logger.error(f"Failed to fetch blogs: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch blogs"
            ) from e

@router.get("/{blog_id}", response_model=BlogOut, status_code=status.HTTP_200_OK)
async def get_blog(blog_id: int, db: Annotated[AsyncSession, Depends(get_async_db)]) -> BlogOut:
    """
    Retrieve a single blog post by ID.
    
    Returns:
        BlogOut: The requested blog post with author details
        
    Raises:
        404: If blog post is not found
        500: If server error occurs
    """
    async with db as session:
        try:
            logger.info(f"Fetching blog with ID: {blog_id}")

            # Eager load author relationship to avoid N+1 queries
            result = await session.execute(
                select(Blog)
                .options(
                    selectinload(Blog.author),
                    selectinload(Blog.comments)
                    # selectinload(Blog.comments).selectinload(Comment.user)  # Avoid N+1 in comments too!
                )
                .where(Blog.id == blog_id)
            )
            blog = result.scalar_one_or_none()

            if not blog:
                logger.warning(f"Blog not found - ID: {blog_id}")
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Blog with ID {blog_id} not found")
            
            logger.debug(f"Successfully retrieved blog ID: {blog_id}")

            # Convert SQLAlchemy model to Pydantic model more elegantly
            return BlogOut.model_validate(blog)
        
        except HTTPException:
            raise   # Re-raise HTTP exceptions (like 404)
        except Exception as e:
            logger.error( f"Failed to fetch blog ID {blog_id}. Error: {str(e)}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve blog: {str(e)}") from e

@router.put("/{blog_id}", response_model=BlogOut)
async def update_blog(blog_id: int, blog_update: BlogUpdate, 
                db: Annotated[AsyncSession, Depends(get_async_db)], 
                current_user: Annotated[User, Depends(get_current_active_user)]
) -> BlogOut:
    """
    Update a blog post.
    
    - Requires authentication
    - Only allows updates by blog author
    - Partial updates supported (only modified fields need to be sent)
    - Returns the updated blog post
    """
    async with db as session:
        try:
            logger.info(
                f"Update blog request - User: {current_user.full_name} "
                f"(ID: {current_user.id}), Blog ID: {blog_id}, "
                f"Update data: {blog_update.model_dump()}"
            )
            
            # Check if the blog exists and belongs to user
            existing_blog = await session.get(Blog, blog_id)
            if not existing_blog:
                logger.error(f"Blog not found - ID: {blog_id}")
                raise HTTPException( status_code=status.HTTP_404_NOT_FOUND, detail=f"Blog with ID {blog_id} not found")
            
            if existing_blog.author_id != current_user.id:
                logger.error(
                    f"Authorization failed - User {current_user.id} "
                    f"attempted to update blog {blog_id} owned by {existing_blog.author_id}"
                )
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this blog")
            

            # Convert string input to enum if needed
            if hasattr(blog_update, 'status') and isinstance(blog_update.status, str):
                try:
                    blog_update.status = BlogStatus[blog_update.status.upper()]
                except KeyError:
                    valid_statuses = [e.value for e in BlogStatus]
                    logger.error(f"Invalid status provided: {blog_update.status}. Valid options: {valid_statuses}")
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail=f"Invalid status. Must be one of: {valid_statuses}")

            # Filter out None values to update only provided fields
            update_data = blog_update.model_dump(exclude_unset=True, exclude_none=True)

            if not update_data:
                logger.error("No valid data provided for update")
                raise HTTPException( status_code=status.HTTP_400_BAD_REQUEST, detail="No valid data provided for update")

            logger.debug(f"Applying updates to blog {blog_id}: {update_data}")

            # Apply updates
            await session.execute(update(Blog).where(Blog.id == blog_id).values(**update_data))
            await session.commit()

            # Fetch the updated blog with relationships
            updated_blog = await session.get(Blog, blog_id, options=[selectinload(Blog.author)])
            if not updated_blog:
                logger.error(f"Blog disappeared after update - ID: {blog_id}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Blog not found after update"
                )
            
            logger.info(f"Successfully updated blog ID: {blog_id}")
            return BlogOut.model_validate(updated_blog)

        except HTTPException:
            raise # Re-raise known HTTP exceptions
        except Exception as e:
            await session.rollback()
            logger.error( f"Failed to update blog ID {blog_id}. Error: {str(e)}", exc_info=True)
            raise HTTPException( status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update blog: {str(e)}") from e

@router.delete("/{blog_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_blog(blog_id: int, db: Annotated[AsyncSession, Depends(get_async_db)], current_user: Annotated[User, Depends(get_current_active_user)]):
    """
    Delete a blog post.
    
    - Requires authentication
    - Only allows deletion by blog author or admin
    - Returns 204 No Content on success
    """
    async with db as session:
        try:
            logger.info(
                f"Delete blog request - User: {current_user.full_name} "
                f"(ID: {current_user.id}), Blog ID: {blog_id}"
            )

            blog = await session.get(Blog, blog_id)
            if not blog:
                logger.error(f"Blog not found - ID: {blog_id}")
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Blog with ID {blog_id} not found")
            
            # Authorization check
            # if blog.author_id != current_user.id and not current_user.is_admin:
            if blog.author_id != current_user.id:
                logger.error(
                    f"Authorization failed - User {current_user.id} "
                    f"attempted to delete blog {blog_id} owned by {blog.author_id}"
                )
                raise HTTPException( status_code=status.HTTP_403_FORBIDDEN, detail=f"Not authorized to delete this blog {blog_id}")
            
            # Perform deletion
            await session.delete(blog)
            await session.commit()
            
            logger.info(f"Successfully deleted blog id: {blog_id}")
            # Following REST best practices, return no content for DELETE operations
            return None

        except HTTPException:
            raise
        except Exception as e:
            await session.rollback()
            logger.error(f"Failed to delete blog ID {blog_id}: {str(e)}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to delete blog: {str(e)}") from e
        
