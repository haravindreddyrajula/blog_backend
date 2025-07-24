from typing import Optional
from pydantic import BaseModel, ConfigDict
from datetime import datetime
from enum import Enum

class BlogStatus(str, Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"

class BlogBase(BaseModel):
    title: str
    content: str
    status: BlogStatus = BlogStatus.DRAFT
    cover_image_url: Optional[str] = None
    is_public: bool = True
    is_featured: bool = False 
    # tags: Optional[list[str]] = None
    tags: Optional[str] = None

class BlogCreate(BlogBase):
    pass

class BlogUpdate(BlogBase):
    title: Optional[str] = None
    content: Optional[str] = None
    status: Optional[BlogStatus] = None
    is_public: Optional[bool] = None
    is_featured: Optional[bool] = None  

class BlogOut(BlogBase):
    model_config = ConfigDict(from_attributes=True) 

    id: int
    created_at: datetime
    updated_at: datetime
    # author_id: int
    # author_name: Optional[str] = None
