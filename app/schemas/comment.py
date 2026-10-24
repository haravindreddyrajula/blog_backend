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
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, AfterValidator

# Constants
MAX_CONTENT_LENGTH = 2000  # ~400 words (typical comment length)

def _reject_control_chars(v: str) -> str:
    if any(ord(c) < 32 and c not in "\n\r\t" for c in v):
        raise ValueError("Comment contains invalid control characters")
    return v

CommentContent = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_CONTENT_LENGTH),
    AfterValidator(_reject_control_chars),
]

class CommentCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"content": "Great post!"}]},
    )
    content: CommentContent


class CommentOut(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "id": 1,
                    "blog_id": 42,
                    "author_id": 10,
                    "content": "Great post!",
                    "created_at": "2026-10-24T12:30:00Z",
                }
            ]
        },
    )

    id: int
    blog_id: int
    author_id: int
    content: str
    created_at: datetime


class CommentAuthor(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str | None = None


class CommentOutWithAuthor(CommentOut):
    author: CommentAuthor