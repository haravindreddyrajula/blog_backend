from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel

class Token(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str
    expires_in: int

class TokenData(BaseModel):
    email: Optional[str] = None
    scopes: list[str] = []

class RevokedTokenCreate(BaseModel):
    """Pydantic model for creating revoked tokens"""
    jti: str
    token_type: Literal["access", "refresh"]
    user_identity: str
    expires_at: datetime
    reason: Optional[str] = None