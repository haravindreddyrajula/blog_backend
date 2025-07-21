import asyncio
import logging
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.deps import get_async_db
from app.models.blog import Blog
from app.models.comment import Comment
from app.models.user import User
from app.schemas.comment import CommentCreate, CommentOut
from app.services.user import get_current_active_user, oauth2_scheme

router = APIRouter(prefix="/comments", tags=["Comments"])

logger = logging.getLogger(__name__)

@router.post(
    "/{blog_id}",
    response_model=CommentOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        404: {"description": "Blog not found or not public"},
        500: {"description": "Internal server error"},
    },
    summary="Add a comment to a blog post",
    description="Adds a new comment to a public blog post after validation."
)
async def add_comment(
    blog_id: Annotated[int, Path(..., title="Blog ID", description="ID of the blog to comment on", example=1)],
    comment: CommentCreate, 
    db: Annotated[AsyncSession, Depends(get_async_db)]
) -> CommentOut:
    """
    Add a new comment to a public blog post.
    
    - **blog_id**: ID of the blog post to comment on
    - **comment**: Comment content and author name
    - Returns: The created comment with ID and timestamps
    """
    async with db as session:
        try:
            # Check if blog exists and is public
            query = select(Blog).where(Blog.id==blog_id, Blog.is_public == True)
            result = await session.execute(query)
            blog = result.scalar_one_or_none()
            
            if not blog:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Blog not found or not public"
                )
            
            # Create new comment
            new_comment = Comment(
                blog_id=blog_id,
                name=comment.name,
                content=comment.content
            )

            # Save to database
            session.add(new_comment)
            await session.commit()
            
            logger.info(f"New comment added to blog {blog_id} by {comment.name}")
            # return new_comment
            return CommentOut.model_validate(new_comment)
            
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"Database error adding comment to blog {blog_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Could not save comment"
            )
        except Exception as e:
            logger.error(f"Unexpected error adding comment to blog {blog_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An unexpected error occurred"
            )

@router.get(
    "/{blog_id}",
    response_model=list[CommentOut],
    status_code=status.HTTP_200_OK,
    responses={
        404: {"description": "Blog not found"},
        422: {"description": "Validation error"},
    },
    summary="Get comments for a blog post",
    description="Retrieves paginated comments for a specific blog post, ordered by newest first."
)
async def get_comments(
    blog_id: Annotated[int, Path(..., title="Blog ID", description="ID of the blog to fetch comments for", example=1)],
    db: Annotated[AsyncSession, Depends(get_async_db)],
    skip: Annotated[int, Query(ge=0, description="Pagination offset", example=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="Maximum number of comments to return (1-100)", example=10)] = 10
) -> list[CommentOut]:
    async with db as session:
        try:
            # Check if blog exists
            query = select(Blog).where(Blog.id==blog_id)
            result = await session.execute(query)
            blog = result.scalar_one_or_none()
            
            if not blog:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Blog not found"
                )
            
            comment_query = (
                select(Comment)
                .where(Comment.blog_id == blog_id)
                .order_by(Comment.created_at.desc())
                .offset(skip)
                .limit(limit)
            )

            # Execute query with timeout
            try:
                coment_result = await asyncio.wait_for(
                    session.execute(comment_query),
                    timeout=10.0  # 10 second timeout
                )
                comments = coment_result.scalars().all()
            except asyncio.TimeoutError:
                logger.error("Database query timed out")
                raise HTTPException(
                    status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                    detail="Database operation timed out"
                )
            
            logger.info(f"Fetched {len(comments)} comments")
            
            return [CommentOut.model_validate(comment) for comment in comments]

        except Exception as e:
            logger.error(f"Unexpected error on fetching comments to blog {blog_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch comments"
            )

@router.delete(
    "/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        403: {"description": "Not authorized to delete this comment"},
        404: {"description": "Comment not found"},
        422: {"description": "Validation error"},
    },
    summary="Delete a comment",
    description="Deletes a comment if the current user is the author or has admin privileges."
)
async def delete_comment(
    comment_id: Annotated[int, Path(..., title="Comment ID", description="ID of the comment to delete", example=1)],
    db: Annotated[AsyncSession, Depends(get_async_db)],
    current_user: Annotated[User, Depends(get_current_active_user)]
):
    async with db as session:
        try:
            # Get the comment with associated blog and author info
            query = select(Comment).join(Comment.blog).where(Comment.id == comment_id)
            result = await session.execute(query)
            comment = result.scalar_one_or_none()

            if not comment:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Comment not found"
                )
            
            # Authorization check (assuming comment has author_id or blog has owner_id)
            if not (
                # current_user.is_admin or 
                comment.name == current_user.id or comment.blog.author_id == current_user.id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized to delete this comment"
                )
            
            await session.delete(comment)
            await session.commit()

            logger.info(f"comment: {comment.content} deleted from blog: {comment.blog_id}")
            return None

        except Exception as e:
            await session.rollback()
            raise HTTPException( status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete comment") from e
