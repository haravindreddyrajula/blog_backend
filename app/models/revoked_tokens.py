from sqlalchemy import Column, String, DateTime, Boolean
from datetime import datetime, timezone
from app.core.database import Base

class RevokedToken(Base):
    __tablename__ = "revoked_tokens"
    
    jti = Column(String(36), primary_key=True)  # JWT ID
    token_type = Column(String(10))            # "access" or "refresh"
    user_identity = Column(String)             # Typically user ID or email
    revoked_at = Column(DateTime, default=datetime.now(timezone.utc))
    expires_at = Column(DateTime)              # When token naturally expires
    is_blacklisted = Column(Boolean, default=True)
    reason = Column(String)