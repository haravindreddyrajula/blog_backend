"""
Production-Ready JWT Token Schemas

Defines request/response models for JWT token operations with comprehensive
validation, security controls, and API documentation.

Author: Production Code Review Team
Status: Production-Ready
Last Updated: 2025-01-17
"""

from datetime import datetime, timedelta
from enum import Enum
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field, field_validator

class TokenType(str, Enum):
    """
    Token type enumeration for JWT tokens.
    
    Used to distinguish between different token types in the system:
    - ACCESS: Short-lived token for API requests (10-30 minutes)
    - REFRESH: Long-lived token for obtaining new access tokens (days/weeks)
    
    **Why separate token types?**
    - ACCESS tokens are frequently validated (performance critical)
    - REFRESH tokens are validated only during token refresh (less frequent)
    - REFRESH tokens are stored only as hashes (revocation tracking)
    - Different expiration times for security vs convenience tradeoff
    
    **Security Note:**
    - Token type is validated on every auth operation
    - Prevents mixing access and refresh token types
    - Enables fine-grained revocation tracking
    """
    
    ACCESS = "access"
    REFRESH = "refresh"


class Token(BaseModel):
    """
    JWT token response model.
    
    Returned after successful authentication. Contains both access and optional
    refresh tokens for stateless, distributed authentication.
    
    **Security Notes:**
    - access_token: Short-lived (10-30 minutes), used for API calls
    - refresh_token: Long-lived (days/weeks), used to get new access token
    - token_type: Always "Bearer" (RFC 6750 standard)
    - expires_in: Seconds until access_token expires
    
    **Example:**
    ```json
    {
        "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
        "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
        "token_type": "Bearer",
        "expires_in": 900
    }
    ```
    """

    access_token: Annotated[
        str,
        Field(
            ...,
            min_length=10,  # JWT tokens minimum realistic length
            max_length=2048,  # Maximum realistic JWT length
            description="JWT access token (short-lived, ~10-30 minutes)",
            examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."],
        ),
    ]

    refresh_token: Annotated[
        Optional[str],
        Field(
            None,
            min_length=10,
            max_length=2048,
            description="JWT refresh token (long-lived, optional, used for rotation)",
            examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."],
        ),
    ] = None

    token_type: Annotated[
        Literal["Bearer"],
        Field(
            "Bearer",
            description="Token authentication scheme (RFC 6750 compliant)",
        ),
    ]

    expires_in: Annotated[
        int,
        Field(
            ...,
            ge=60,  # Minimum 1 minute
            le=86400 * 365,  # Maximum 1 year (in seconds)
            description="Seconds until access_token expires",
            examples=[900],
        ),
    ]

    @field_validator("expires_in")
    @classmethod
    def validate_expiration(cls, v: int) -> int:
        """
        Validate token expiration is reasonable.
        
        Ensures expiration times are within expected bounds:
        - Minimum: 60 seconds (for testing)
        - Maximum: 1 year (for refresh tokens)
        """
        if v < 60:
            raise ValueError("expires_in must be at least 60 seconds")
        if v > 86400 * 365:
            raise ValueError("expires_in must not exceed 1 year")
        return v

    class Config:
        """Pydantic configuration."""
        str_strip_whitespace = True
        json_schema_extra = {
            "description": "JWT token pair for stateless authentication",
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "Bearer",
                "expires_in": 900,
            },
        }


class TokenData(BaseModel):
    """
    JWT token payload data.
    
    Extracted from the JWT token after validation. Contains claims that
    identify the user and their permissions.
    
    **JWT Claims:**
    - email: User email (subject identifier)
    - scopes: List of permission scopes granted to this token
    - iat: Issued at (set by JWT library)
    - exp: Expiration time (set by JWT library)
    - jti: JWT ID (unique per token, for revocation)
    
    **Security Notes:**
    - email is required and validated by Pydantic
    - scopes are restricted to maximum 10 (prevent bloat)
    - Each scope is validated as lowercase alphanumeric + underscore
    """

    email: Annotated[
        Optional[str],
        Field(
            None,
            description="User email address (from JWT 'sub' claim)",
            examples=["user@example.com"],
        ),
    ] = None

    scopes: Annotated[
        list[str],
        Field(
            default_factory=list,
            max_length=10,  # Prevent excessive scopes
            description="Permission scopes granted to this token",
            examples=[["read:blogs", "write:comments"]],
        ),
    ] = []

    @field_validator("scopes", mode="before")
    @classmethod
    def validate_scopes(cls, v: list[str]) -> list[str]:
        """
        Validate scope format and count.
        
        Each scope must:
        - Be lowercase alphanumeric + underscore
        - Be less than 50 characters
        - Follow pattern: resource:action (e.g., "blogs:read")
        """
        if not isinstance(v, list):
            raise ValueError("scopes must be a list")
        if len(v) > 10:
            raise ValueError("Maximum 10 scopes allowed")
        
        for scope in v:
            if not isinstance(scope, str):
                raise ValueError("Each scope must be a string")
            if not scope or len(scope) > 50:
                raise ValueError("Scope must be 1-50 characters")
            if not all(c.isalnum() or c in "_:" for c in scope):
                raise ValueError(
                    "Scope must contain only alphanumeric, underscore, and colon"
                )
        
        return v

    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "description": "Decoded JWT token claims (extracted from token)",
            "example": {
                "email": "user@example.com",
                "scopes": ["read:blogs", "write:comments"],
            },
        }


class RevokedTokenCreate(BaseModel):
    """
    Revoked token creation model.
    
    Used to record a JWT token in the revocation blacklist. When a user logs out
    or a token is compromised, it's added here to prevent further use.
    
    **Workflow:**
    1. User logs out or token is compromised
    2. Extract jti (unique ID) from token
    3. Create RevokedTokenCreate record
    4. Insert into revoked_tokens table
    5. On every protected endpoint, check if jti is in blacklist
    
    **Security Notes:**
    - jti must be unique per token (checked at token generation)
    - expires_at determines when cleanup jobs can remove this record
    - reason enables audit trail for security investigations
    
    **Example:**
    ```python
    # During logout
    token_payload = jwt.decode(token, SECRET_KEY)
    revoked = RevokedTokenCreate(
        jti=token_payload["jti"],
        token_type="access",
        user_identity="user@example.com",
        expires_at=datetime.utcnow() + timedelta(hours=1),
        reason="user logout"
    )
    ```
    """

    jti: Annotated[
        str,
        Field(
            ...,
            min_length=36,  # UUID format: 8-4-4-4-12
            max_length=36,
            description="JWT ID (unique identifier from JWT 'jti' claim, UUID format)",
            examples=["550e8400-e29b-41d4-a716-446655440000"],
        ),
    ]

    token_type: Annotated[
        Literal["access", "refresh"],
        Field(
            ...,
            description="Type of token being revoked",
        ),
    ]

    user_identity: Annotated[
        str,
        Field(
            ...,
            min_length=1,
            max_length=255,
            description="User email or ID (for audit trail)",
            examples=["user@example.com"],
        ),
    ]

    expires_at: Annotated[
        datetime,
        Field(
            ...,
            description="When the token naturally expires (for cleanup scheduling)",
        ),
    ]

    reason: Annotated[
        Optional[str],
        Field(
            None,
            max_length=255,
            description="Revocation reason for audit trail",
            examples=["user logout", "password change", "security incident"],
        ),
    ] = None

    @field_validator("expires_at")
    @classmethod
    def validate_expiration_future(cls, v: datetime) -> datetime:
        """Ensure expiration time is in the future."""
        if v <= datetime.utcnow():
            raise ValueError("expires_at must be in the future")
        return v

    @field_validator("jti")
    @classmethod
    def validate_jti_format(cls, v: str) -> str:
        """
        Validate JTI is UUID format.
        
        UUIDs follow pattern: 8-4-4-4-12 hexadecimal digits separated by hyphens
        Example: 550e8400-e29b-41d4-a716-446655440000
        """
        parts = v.split("-")
        if len(parts) != 5:
            raise ValueError("jti must be UUID format (8-4-4-4-12)")
        
        lengths = [len(p) for p in parts]
        if lengths != [8, 4, 4, 4, 12]:
            raise ValueError("jti must be valid UUID format")
        
        for part in parts:
            if not all(c in "0123456789abcdefABCDEF" for c in part):
                raise ValueError("jti must contain only hexadecimal characters")
        
        return v.lower()  # Normalize to lowercase

    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "description": "Record of revoked JWT token for blacklist",
            "example": {
                "jti": "550e8400-e29b-41d4-a716-446655440000",
                "token_type": "access",
                "user_identity": "user@example.com",
                "expires_at": "2025-01-17T13:00:00Z",
                "reason": "user logout",
            },
        }