import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.constants import DEFAULT_LIMIT, MAX_LIMIT
from app.core.deps import get_async_db
from app.models.blog import Blog
from app.models.comment import Comment
from app.models.user import User
from app.schemas.comment import CommentCreate, CommentOut
from app.services.user import get_current_active_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/comments", tags=["Comments"])

DbSession = Annotated[AsyncSession, Depends(get_async_db)]
CurrentUser = Annotated[User, Depends(get_current_active_user)]
BlogId = Annotated[int, Path(ge=1, description="Blog ID")]
CommentId = Annotated[int, Path(ge=1, description="Comment ID")]


async def _get_public_blog_or_404(db: AsyncSession, blog_id: int) -> Blog:
    blog = await db.scalar(
        select(Blog).where(Blog.id == blog_id, Blog.is_public.is_(True))
    )
    if blog is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Blog not found")
    return blog


@router.post("/{blog_id}", status_code=status.HTTP_201_CREATED, response_model=CommentOut)
async def add_comment(
    blog_id: BlogId, payload: CommentCreate, db: DbSession, current_user: CurrentUser
) -> Comment:
    await _get_public_blog_or_404(db, blog_id)
    comment = Comment(blog_id=blog_id, author_id=current_user.id, content=payload.content)
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    logger.info(
        "Comment created",
        extra={"comment_id": comment.id, "blog_id": blog_id, "user": current_user.id},
    )
    return comment


@router.get("/{blog_id}", response_model=list[CommentOut])
async def get_comments(
    blog_id: BlogId,
    db: DbSession,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> list[Comment]:
    await _get_public_blog_or_404(db, blog_id)  # was must_be_public=False
    result = await db.scalars(
        select(Comment)
        .options(joinedload(Comment.author))
        .where(Comment.blog_id == blog_id)
        .order_by(Comment.created_at.desc(), Comment.id.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(result.all())


@router.delete("/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment(
    comment_id: CommentId, db: DbSession, current_user: CurrentUser
) -> None:
    comment = await db.scalar(
        select(Comment)
        .options(joinedload(Comment.blog))
        .where(Comment.id == comment_id)
    )
    if comment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Comment not found")
    if current_user.id not in (comment.author_id, comment.blog.author_id):
        logger.warning(
            "Forbidden comment delete",
            extra={"comment_id": comment_id, "user": current_user.id},
        )
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized")

    blog_id = comment.blog_id  # read before the object is deleted
    await db.delete(comment)
    await db.commit()
    logger.info("Comment deleted", extra={"comment_id": comment_id, "blog_id": blog_id})
