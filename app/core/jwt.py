from datetime import datetime, timedelta, timezone
from enum import Enum
import logging
from sqlalchemy import delete
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends, HTTPException, status
from jose import jwt, JWTError
from typing import Optional, Union
from pydantic import BaseModel, Field
from app.core.config import settings
from app.core.deps import get_async_db
from app.models.revoked_tokens import RevokedToken
from app.models.user import User
from app.schemas.token import RevokedTokenCreate 

logger = logging.getLogger(__name__)

class TokenType(str, Enum):
    ACCESS = "access"
    REFRESH = "refresh"

class TokenData(BaseModel):
    """Model for validated token data"""
    sub: str = Field(..., description="Subject (usually user ID)")
    scopes: list[str] = Field(default_factory=list)
    token_type: Optional[TokenType] = Field(None, description="Token type for validation")
    jti: Optional[str] = Field(None, description="Unique token identifier")

class TokenException(HTTPException):
    """Custom exception for token-related errors"""
    def __init__(self, detail: str, status_code: int = status.HTTP_401_UNAUTHORIZED):
        super().__init__(
            status_code=status_code,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"}
        )
    
def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
    additional_claims: Optional[dict] = None
) -> str:
    """
    Create a JWT access token with enhanced security claims.
    
    Args:
        data: Data to include in the token (must contain 'sub')
        expires_delta: Optional custom expiration time
        additional_claims: Optional additional claims to include
    
    Returns:
        Encoded JWT token
    
    Raises:
        ValueError: If required fields are missing
    """
    if not data.get("sub"):
        raise ValueError("Token data must contain 'sub' field")

    to_encode = data.copy()
    if additional_claims:
        to_encode.update(additional_claims)
    
    # Set expiration
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta if expires_delta else timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    
    # Standard claims
    to_encode.update({
        "exp": expire,
        "iat": now,                      # Issued at
        "iss": settings.JWT_ISSUER,      # Issuer
        "aud": settings.JWT_AUDIENCE,    # Audience
        "type": TokenType.ACCESS.value,  # Token type
        "jti": generate_jti(),           # Unique token identifier for revocation
        "nbf": now                       # Not before time
    })
    
    return jwt.encode(
        to_encode,
        settings.SECRET_KEY.get_secret_value(),
        algorithm=settings.ALGORITHM
    )

def create_refresh_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
    family_id: Optional[str] = None
) -> str:
    """
    Create a secure refresh token with family tracking.
    
    Args:
        data: Data to include (must contain 'sub')
        expires_delta: Optional custom expiration
        family_id: Optional existing family ID for token rotation
    
    Returns:
        Encoded refresh token
    """
    if not data.get("sub"):
        raise ValueError("Token data must contain 'sub' field")

    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta if expires_delta else timedelta(minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES))

    to_encode.update({
        "exp": expire,
        "iat": now,
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "type": TokenType.REFRESH.value,
        "jti": generate_jti(),
        "rti": family_id if family_id else generate_jti(),  # Refresh token family ID
        "nbf": now
    })

    return jwt.encode(
        to_encode,
        settings.SECRET_KEY.get_secret_value(),
        algorithm=settings.ALGORITHM
    )

async def verify_token(
    token: str,
    expected_type: Optional[Union[TokenType, str]] = None, #accepts both tokentype and str types
    required_scopes: Optional[list[str]] = None,
    db: AsyncSession = Depends(get_async_db)
) -> TokenData:
    """
    Verify and decode a JWT token with production-grade validation.
    
    Args:
        token: JWT token to verify
        expected_type: Expected token type
        required_scopes: Required scopes for authorization
        db: Database session
    
    Returns:
        Validated TokenData
    
    Raises:
        TokenException: For any validation failure
    """
    async with db as session:
        try:
            payload = jwt.decode(
                token,
                settings.SECRET_KEY.get_secret_value(),
                algorithms=[settings.ALGORITHM],
                audience=settings.JWT_AUDIENCE,
                issuer=settings.JWT_ISSUER,
                options={
                    "verify_aud": settings.JWT_AUDIENCE is not None,
                    "require_sub": True,
                    "verify_exp": True,
                    "verify_iss": True,
                    "verify_nbf": True,
                    "leeway": 30
                }
            )

            # Validate token type
            if expected_type:
                # Convert string to enum if needed
                if isinstance(expected_type, str):
                    expected_type = TokenType(expected_type)
                if payload.get("type") != expected_type.value:
                    raise TokenException("Invalid token type")

            # Check revocation status
            jti = payload.get("jti")
            if jti and await is_token_revoked(jti, session,expected_type):
                raise TokenException("Token revoked")
            
            # Verify user exists and is active
            email = payload.get("sub")
            result = await session.execute(select(User).where(User.email == email))
            user = result.scalars().first()
            
            if not user:
                raise TokenException("User not found")
            if not user.is_active:
                raise TokenException("User inactive")
                
            # Validate scopes
            token_scopes = payload.get("scopes", [])
            if required_scopes and not all(scope in token_scopes for scope in required_scopes):
                raise TokenException("Insufficient scopes", status.HTTP_403_FORBIDDEN)
                        
            logger.info("Token Verification successful")

            return TokenData(
                sub=payload["sub"],
                scopes=token_scopes,
                token_type=payload.get("type"),
                jti=jti
            )
            
        except JWTError as e:
            raise TokenException(f"Invalid token: {str(e)}")

def generate_jti() -> str:
    """Generate a unique JWT ID using UUID4"""
    import uuid
    return str(uuid.uuid4())

async def revoke_token(token_data: RevokedTokenCreate,db: AsyncSession) -> None:
    """
    Safely revoke a token with comprehensive error handling
    
    Args:
        db: Async database session
        token_data: Validated revocation data
        
    Raises:
        TokenRevocationError: If revocation fails
    """
    async with db as session:
        try:
            # Check if token is already revoked
            existing = await session.execute(
                select(RevokedToken).where(RevokedToken.jti == token_data.jti)
            )
            if existing.scalars().first():
                return  # Already revoked

            # Create new revoked token record
            revoked_token = RevokedToken(
                jti=token_data.jti,
                token_type=token_data.token_type,
                user_identity=token_data.user_identity,
                expires_at=token_data.expires_at,
                revoked_at=datetime.now(timezone.utc),
                is_blacklisted=True,
                reason=token_data.reason
            )
            
            session.add(revoked_token)
            await session.commit()
            
        except SQLAlchemyError as e:
            await session.rollback()
            raise TokenRevocationError(f"Failed to revoke token: {str(e)}")

async def batch_revoke_tokens(
    db: AsyncSession,
    tokens_data: list[RevokedTokenCreate]
) -> None:
    """
    Efficiently revoke multiple tokens in a single transaction
    
    Args:
        db: Async database session
        tokens_data: List of tokens to revoke
    """
    try:
        # Get existing JTIs to avoid duplicates
        existing_jtis = set()
        result = await db.execute(
            select(RevokedToken.jti).where(
                RevokedToken.jti.in_([t.jti for t in tokens_data])
            )
        )
        existing_jtis.update(result.scalars().all())
        
        # Bulk insert new revocations
        new_revocations = [
            RevokedToken(
                jti=token.jti,
                token_type=token.token_type,
                user_identity=token.user_identity,
                expires_at=token.expires_at,
                revoked_at=datetime.now(timezone.utc),
                is_blacklisted=True,
                reason=token.reason
            )
            for token in tokens_data
            if token.jti not in existing_jtis
        ]
        
        if new_revocations:
            db.add_all(new_revocations)
            await db.commit()
            
    except SQLAlchemyError as e:
        await db.rollback()
        raise TokenRevocationError(f"Batch revocation failed: {str(e)}")

async def is_token_revoked(
        jti: str,
        db: AsyncSession = Depends(get_async_db), 
        expected_type: Optional[TokenType] = None, 
        check_expiry: Optional[bool] = True
) -> bool:
    """
    Comprehensive token verification with revocation, expiry, and type checks
    
    Args:
        jti: Token unique identifier (JWT ID)
        db: Async database session
        check_expiry: Verify token expiration (default True)
        expected_type: If provided, enforces token type validation
        
    Returns:
        bool: True if token is invalid/revoked, False if valid
        
    Raises:
        TokenVerificationError: On database errors in production mode
    """
    async with db as session:
        try:
            # Base query for revocation check
            query = select(RevokedToken).where(
                RevokedToken.jti == jti,
                RevokedToken.is_blacklisted == True
            )
            
            # Add expiry filter if requested
            if check_expiry:
                query = query.where(
                    RevokedToken.expires_at > datetime.now(timezone.utc)
                )
            
            # Execute revocation check
            result = await session.execute(query)
            revoked = result.scalars().first() is not None
            if revoked:
                return True
                
            # Additional type verification if requested
            if expected_type is not None:
                if revoked and revoked.token_type != expected_type.value:
                    return True
                
            logger.info("Token revocation check passed")
                    
            return False
            
        except SQLAlchemyError as e:
            if settings.DEBUG:
                raise TokenVerificationError(f"Database verification failed: {str(e)}")
            # Fail secure - assume token is invalid if we can't verify
            return True

async def cleanup_expired_tokens(db: AsyncSession) -> int:
    """
    Cleanup expired revoked tokens from database
    
    Args:
        db: Async database session
        
    Returns:
        int: Number of tokens deleted
    """
    try:
        result = await db.execute(
            delete(RevokedToken).where(
                RevokedToken.expires_at < datetime.now(timezone.utc)
            )
        )
        await db.commit()
        return result.rowcount
        
    except SQLAlchemyError as e:
        await db.rollback()
        raise TokenCleanupError(f"Failed to cleanup tokens: {str(e)}")

class TokenRevocationError(Exception):
    """Custom exception for revocation failures"""
    pass

class TokenVerificationError(Exception):
    """Custom exception for verification failures"""
    pass

class TokenCleanupError(Exception):
    """Custom exception for cleanup failures"""
    pass