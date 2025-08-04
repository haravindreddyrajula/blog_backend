from sqlalchemy import Column, Integer, String, Boolean, Text, ForeignKey, DateTime
from datetime import datetime, timezone
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.schemas.blog import BlogStatus

class Blog(Base):
    __tablename__ = "blogs"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False, index=True)
    excerpt = Column(String)
    content = Column(Text, nullable=False)
    status = Column(SQLEnum(BlogStatus), default=BlogStatus.DRAFT)
    views = Column(Integer,default=0)
    cover_image_url = Column(String, nullable=True)
    is_public = Column(Boolean, default=True)
    is_featured = Column(Boolean, default=False)
    # tags = Column(ARRAY(String), nullable=True)  # For PostgreSQL array type
    tags = Column(String, nullable=True)
    comments = relationship("Comment", back_populates="blog", cascade="all, delete-orphan")
    author_id = Column(Integer, ForeignKey("users.id"), index=True)
    author = relationship("User", back_populates="blogs")
    created_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))
