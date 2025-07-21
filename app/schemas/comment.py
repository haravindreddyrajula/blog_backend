from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from datetime import datetime

# Constants
MAX_NAME_LENGTH = 100
MAX_CONTENT_LENGTH = 1000

class CommentCreate(BaseModel):
    name: Annotated[
        str, 
        StringConstraints(
            strip_whitespace=True, 
            min_length=1, 
            max_length=MAX_NAME_LENGTH
        )
    ] = Field(
        ..., 
        example="John Doe",
        description="Name of the comment author (1-100 characters)"
    )
    
    content: Annotated[
        str, 
        StringConstraints(
            strip_whitespace=True, 
            min_length=1, 
            max_length=MAX_CONTENT_LENGTH
        )
    ] = Field(
        ..., 
        example="Great post!",
        description="Comment content (1-1000 characters)"
    )

class CommentOut(CommentCreate):
    id: int
    created_at: datetime
    blog_id: int

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 1,
                "name": "John Doe",
                "content": "Great post!",
                "created_at": "2023-01-01T00:00:00Z",
                "blog_id": 1
            }
        }
    )
