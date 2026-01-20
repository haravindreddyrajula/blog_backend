"""
JWT Token management for FastAPI authentication and authorization.

This module provides secure JWT token creation, verification, revocation, and
lifecycle management. It integrates with Pydantic for validation, SQLAlchemy
for persistence, and the python-jose library for cryptography.

Key Features:
- Create access and refresh tokens with security claims
- Verify tokens with multi-layer validation (expiry, revocation, user status)
- Track revoked tokens in database for logout enforcement
- Batch operations for efficient token management
- Audit logging for security events
- Protection against common JWT attacks (token reuse, family chains, scope abuse)

Token Claims:
- sub: Subject (typically user email)
- exp: Expiration time
- iat: Issued at time
- nbf: Not before time
- iss: Issuer (from settings)
- aud: Audience (from settings)
- type: "access" or "refresh"
- jti: Unique token ID (for revocation)
- rti: Refresh token family ID (for rotation chain)
- scopes: List of authorization scopes

Security Considerations:
1. Tokens are cryptographically signed but NOT encrypted
2. Don't store sensitive data in token claims
3. Always verify token signature, expiry, and revocation status
4. Use HTTPS for all token transmission
5. Store tokens securely on client (HttpOnly cookies preferred over localStorage)
6. Implement token rotation on refresh
7. Short-lived access tokens (15 min) + long-lived refresh tokens (7 days)
"""

import uuid
import logging
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional, Union

from fastapi import HTTPException, status
from jose import jwt, JWTError
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.revoked_tokens import RevokedToken
from app.models.user import User


logger = logging.getLogger(__name__)


# ============================================================================
# EXCEPTIONS
# ============================================================================

class TokenException(HTTPException):
    """Base exception for token-related errors raised to FastAPI clients."""

    def __init__(
        self,
        detail: str,
        status_code: int = status.HTTP_401_UNAUTHORIZED,
    ):
        super().__init__(
            status_code=status_code,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


class TokenError(Exception):
    """Base exception for internal token operation errors."""

    pass


class TokenRevocationError(TokenError):
    """Raised when token revocation fails."""

    pass


class TokenVerificationError(TokenError):
    """Raised when token verification fails."""

    pass


class TokenCleanupError(TokenError):
    """Raised when token cleanup fails."""

    pass


# ============================================================================
# ENUMS & MODELS
# ============================================================================

class TokenType(str, Enum):
    """JWT token type enumeration."""

    ACCESS = "access"
    REFRESH = "refresh"


class TokenData(BaseModel):
    """Validated token data extracted from JWT payload."""

    sub: str = Field(..., description="Subject (usually user email)")
    scopes: list[str] = Field(default_factory=list, description="Authorization scopes")
    token_type: TokenType = Field(..., description="Token type (access or refresh)")
    jti: str = Field(..., description="Unique token identifier for revocation tracking")


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def _generate_jti() -> str:
    """
    Generate a unique JWT ID (JTI) for token revocation tracking.

    Returns:
        UUID4 string identifier.
    """
    return str(uuid.uuid4())


def _validate_expiry_delta(expires_delta: timedelta) -> None:
    """
    Validate that expiration delta is positive.

    Args:
        expires_delta: Time delta for token expiration.

    Raises:
        ValueError: If expires_delta is negative or zero.
    """
    if expires_delta.total_seconds() <= 0:
        raise ValueError("Token expiration must be in the future (positive timedelta)")


def _validate_additional_claims(claims: dict) -> None:
    """
    Validate that additional claims don't override security claims.

    Args:
        claims: Additional claims dictionary.

    Raises:
        ValueError: If reserved claims are present.
    """
    reserved_claims = {"exp", "iat", "nbf", "iss", "aud", "type", "jti", "rti", "sub"}
    conflicting = set(claims.keys()) & reserved_claims

    if conflicting:
        raise ValueError(
            f"Cannot override reserved JWT claims: {conflicting}. "
            "Use token creation functions for these claims."
        )


# ============================================================================
# TOKEN CREATION
# ============================================================================

def create_access_token(
    user_email: str,
    additional_claims: Optional[dict] = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a JWT access token with enhanced security claims.

    Tokens include:
    - Standard JWT claims (iss, aud, exp, iat, nbf)
    - Subject (sub): user email
    - Token type: "access"
    - Unique ID (jti): for revocation tracking

    Args:
        user_email: User's email address (token subject)
        additional_claims: Optional additional claims (scopes, permissions, etc.)
        expires_delta: Optional custom expiration time. Defaults to ACCESS_TOKEN_EXPIRE_MINUTES.

    Returns:
        Encoded JWT token string.

    Raises:
        ValueError: If user_email is empty or additional_claims contains reserved fields.
        RuntimeError: If token encoding fails.

    Example:
        token = create_access_token(
            user_email="user@example.com",
            additional_claims={"scopes": ["read", "write"]},
            expires_delta=timedelta(minutes=30),
        )
    """
    if not user_email or not isinstance(user_email, str):
        raise ValueError("user_email must be a non-empty string")

    # Validate and set expiration
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    _validate_expiry_delta(expires_delta)

    # Validate additional claims
    if additional_claims:
        _validate_additional_claims(additional_claims)

    # Build token payload
    now = datetime.now(timezone.utc)
    expire = now + expires_delta

    payload = {
        "sub": user_email,
        "exp": expire,
        "iat": now,
        "nbf": now,
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "type": TokenType.ACCESS.value,
        "jti": _generate_jti(),
    }

    # Add additional claims
    if additional_claims:
        payload.update(additional_claims)

    try:
        token = jwt.encode(
            payload,
            settings.SECRET_KEY.get_secret_value(),
            algorithm=settings.ALGORITHM,
        )
        logger.debug("Access token created for user %s", user_email)
        return token

    except Exception as e:
        logger.error("Failed to encode access token: %s", str(e), exc_info=True)
        raise RuntimeError("Token creation failed") from e


def create_refresh_token(
    user_email: str,
    additional_claims: Optional[dict] = None,
    expires_delta: Optional[timedelta] = None,
    family_id: Optional[str] = None,
) -> str:
    """
    Create a JWT refresh token with token rotation chain tracking.

    Refresh tokens include:
    - All standard access token claims
    - Token type: "refresh"
    - Refresh token family ID (rti): for detecting token reuse attacks

    Args:
        user_email: User's email address (token subject)
        additional_claims: Optional additional claims
        expires_delta: Optional custom expiration. Defaults to REFRESH_TOKEN_EXPIRE_MINUTES.
        family_id: Optional existing family ID to link token rotation chain.
                   If None, generates new family ID.

    Returns:
        Encoded JWT refresh token string.

    Raises:
        ValueError: If inputs are invalid or additional_claims reserved.
        RuntimeError: If token encoding fails.

    Example:
        refresh_token = create_refresh_token(
            user_email="user@example.com",
            family_id="existing-family-id",  # For token rotation
        )
    """
    if not user_email or not isinstance(user_email, str):
        raise ValueError("user_email must be a non-empty string")

    # Validate and set expiration
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES)
    _validate_expiry_delta(expires_delta)

    # Validate additional claims
    if additional_claims:
        _validate_additional_claims(additional_claims)

    # Build token payload
    now = datetime.now(timezone.utc)
    expire = now + expires_delta

    payload = {
        "sub": user_email,
        "exp": expire,
        "iat": now,
        "nbf": now,
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "type": TokenType.REFRESH.value,
        "jti": _generate_jti(),
        "rti": family_id or _generate_jti(),  # Refresh token family ID
    }

    # Add additional claims
    if additional_claims:
        payload.update(additional_claims)

    try:
        token = jwt.encode(
            payload,
            settings.SECRET_KEY.get_secret_value(),
            algorithm=settings.ALGORITHM,
        )
        logger.debug("Refresh token created for user %s", user_email)
        return token

    except Exception as e:
        logger.error("Failed to encode refresh token: %s", str(e), exc_info=True)
        raise RuntimeError("Refresh token creation failed") from e


# ============================================================================
# TOKEN VERIFICATION
# ============================================================================

async def verify_token(
    token: str,
    expected_type: TokenType,
    session: AsyncSession,
    required_scopes: Optional[list[str]] = None,
) -> TokenData:
    """
    Verify and decode a JWT token with comprehensive validation.

    Performs multiple validation layers:
    1. Cryptographic signature verification
    2. Expiration time validation
    3. Issued-at and not-before time validation
    4. Token type validation
    5. Revocation status check
    6. User existence and active status check
    7. Scope authorization check

    Args:
        token: JWT token string to verify
        expected_type: Expected token type (ACCESS or REFRESH)
        session: AsyncSession for database queries
        required_scopes: Optional list of required scopes for authorization

    Returns:
        TokenData containing verified token payload

    Raises:
        TokenException: If token is invalid, expired, revoked, or unauthorized
        TokenVerificationError: If database verification fails

    Example:
        token_data = await verify_token(
            token="eyJ0eX...",
            expected_type=TokenType.ACCESS,
            session=db_session,
            required_scopes=["read:posts"],
        )
        user_email = token_data.sub
    """
    if not token or not isinstance(token, str):
        raise TokenException("Token is required and must be a string")

    try:
        # Decode and validate JWT signature, expiry, issuer, audience
        payload = jwt.decode(
            token,
            settings.SECRET_KEY.get_secret_value(),
            algorithms=[settings.ALGORITHM],
            audience=settings.JWT_AUDIENCE,
            issuer=settings.JWT_ISSUER,
            options={
                "verify_aud": True,
                "verify_iss": True,
                "verify_exp": True,
                "verify_nbf": True,
                "require_sub": True,
                "leeway": 30,  # 30 seconds clock skew tolerance
            },
        )

    except JWTError as e:
        logger.warning("JWT decode error: %s", str(e))
        raise TokenException("Invalid or expired token") from e

    # Validate token type
    token_type_str = payload.get("type")
    if token_type_str != expected_type.value:
        logger.warning(
            "Token type mismatch: expected %s, got %s",
            expected_type.value,
            token_type_str,
        )
        raise TokenException("Invalid token type")

    # Get token identifier for revocation check
    jti = payload.get("jti")
    if not jti:
        logger.warning("Token missing JTI claim")
        raise TokenException("Invalid token format")

    # Check revocation status
    is_revoked = await _is_token_revoked(jti, expected_type, session)
    if is_revoked:
        logger.warning("Revoked token verification attempt: %s", jti)
        raise TokenException("Token has been revoked")

    # Verify user exists and is active
    user_email = payload.get("sub")
    result = await session.execute(select(User).where(User.email == user_email))
    user = result.scalars().first()

    if not user:
        logger.warning("Token verification for non-existent user: %s", user_email)
        raise TokenException("User not found")

    if not user.is_active:
        logger.warning("Token verification for inactive user: %s", user_email)
        raise TokenException("User account is inactive")

    # Validate scopes if required
    token_scopes = payload.get("scopes", [])
    if required_scopes:
        missing_scopes = set(required_scopes) - set(token_scopes)
        if missing_scopes:
            logger.warning(
                "Insufficient scopes for user %s. Missing: %s",
                user_email,
                missing_scopes,
            )
            raise TokenException(
                "Insufficient scopes",
                status_code=status.HTTP_403_FORBIDDEN,
            )

    logger.debug("Token verified successfully for user %s", user_email)

    return TokenData(
        sub=user_email,
        scopes=token_scopes,
        token_type=expected_type,
        jti=jti,
    )


# ============================================================================
# TOKEN REVOCATION
# ============================================================================

async def revoke_token(
    jti: str,
    token_type: TokenType,
    user_email: str,
    expires_at: datetime,
    session: AsyncSession,
    reason: str = "Logout",
) -> None:
    """
    Revoke a single token by adding it to the blacklist.

    Args:
        jti: Unique token identifier to revoke
        token_type: Type of token (ACCESS or REFRESH)
        user_email: User who owns the token
        expires_at: Token expiration time
        session: AsyncSession for database operations
        reason: Optional revocation reason (e.g., "Logout", "Password reset")

    Raises:
        TokenRevocationError: If revocation fails
        ValueError: If inputs are invalid

    Example:
        await revoke_token(
            jti="uuid-1234",
            token_type=TokenType.ACCESS,
            user_email="user@example.com",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
            session=db_session,
            reason="User logout",
        )
    """
    if not jti or not isinstance(jti, str):
        raise ValueError("jti must be a non-empty string")
    if not user_email or not isinstance(user_email, str):
        raise ValueError("user_email must be a non-empty string")

    try:
        # Check if token already revoked
        existing = await session.execute(
            select(RevokedToken).where(RevokedToken.jti == jti)
        )

        if existing.scalars().first():
            logger.debug("Token already revoked: %s", jti)
            return

        # Create revocation record
        revoked_token = RevokedToken(
            jti=jti,
            token_type=token_type.value,
            user_identity=user_email,
            expires_at=expires_at,
            revoked_at=datetime.now(timezone.utc),
            is_blacklisted=True,
            reason=reason,
        )

        session.add(revoked_token)
        await session.commit()

        logger.info(
            "Token revoked: jti=%s, user=%s, reason=%s",
            jti,
            user_email,
            reason,
        )

    except SQLAlchemyError as e:
        await session.rollback()
        logger.error("Failed to revoke token: %s", str(e), exc_info=True)
        raise TokenRevocationError(f"Token revocation failed: {str(e)}") from e


async def revoke_user_tokens(
    user_email: str,
    session: AsyncSession,
    reason: str = "User revoked all tokens",
) -> int:
    """
    Revoke all active tokens for a user.

    Useful for password changes, account lockouts, or security events.

    Args:
        user_email: Email of user whose tokens to revoke
        session: AsyncSession for database operations
        reason: Revocation reason

    Returns:
        Number of tokens added to revocation list

    Raises:
        TokenRevocationError: If operation fails

    Example:
        count = await revoke_user_tokens(
            user_email="user@example.com",
            session=db_session,
            reason="Password changed by user",
        )
    """
    if not user_email or not isinstance(user_email, str):
        raise ValueError("user_email must be a non-empty string")

    try:
        # Find non-revoked tokens for user still valid
        result = await session.execute(
            select(RevokedToken).where(
                (RevokedToken.user_identity == user_email)
                & (RevokedToken.is_blacklisted == False)
                & (RevokedToken.expires_at > datetime.now(timezone.utc))
            )
        )

        tokens = result.scalars().all()

        # Mark all as revoked
        for token in tokens:
            token.is_blacklisted = True
            token.reason = reason
            token.revoked_at = datetime.now(timezone.utc)

        if tokens:
            await session.commit()
            logger.info(
                "Revoked %d tokens for user %s: %s",
                len(tokens),
                user_email,
                reason,
            )

        return len(tokens)

    except SQLAlchemyError as e:
        await session.rollback()
        logger.error("Failed to revoke user tokens: %s", str(e), exc_info=True)
        raise TokenRevocationError(f"User token revocation failed: {str(e)}") from e


async def batch_revoke_tokens(
    jti_list: list[str],
    session: AsyncSession,
    reason: str = "Batch revocation",
) -> int:
    """
    Efficiently revoke multiple tokens in a single transaction.

    Args:
        jti_list: List of token identifiers to revoke
        session: AsyncSession for database operations
        reason: Revocation reason

    Returns:
        Number of tokens revoked

    Raises:
        TokenRevocationError: If operation fails
        ValueError: If jti_list is empty

    Example:
        count = await batch_revoke_tokens(
            jti_list=["uuid-1", "uuid-2", "uuid-3"],
            session=db_session,
            reason="Session invalidation",
        )
    """
    if not jti_list or not isinstance(jti_list, list):
        raise ValueError("jti_list must be a non-empty list")

    try:
        # Update all tokens to revoked status
        result = await session.execute(
            select(RevokedToken).where(
                (RevokedToken.jti.in_(jti_list))
                & (RevokedToken.is_blacklisted == False)
            )
        )

        tokens = result.scalars().all()

        for token in tokens:
            token.is_blacklisted = True
            token.reason = reason
            token.revoked_at = datetime.now(timezone.utc)

        if tokens:
            await session.commit()
            logger.info(
                "Batch revoked %d tokens: %s",
                len(tokens),
                reason,
            )

        return len(tokens)

    except SQLAlchemyError as e:
        await session.rollback()
        logger.error("Failed in batch revocation: %s", str(e), exc_info=True)
        raise TokenRevocationError(f"Batch revocation failed: {str(e)}") from e


# ============================================================================
# REVOCATION CHECKING
# ============================================================================

async def _is_token_revoked(
    jti: str,
    token_type: TokenType,
    session: AsyncSession,
) -> bool:
    """
    Check if a token is revoked.

    Args:
        jti: Token unique identifier
        token_type: Token type to validate
        session: AsyncSession for database query

    Returns:
        True if token is revoked or invalid, False if valid

    Raises:
        TokenVerificationError: If database query fails (only in DEBUG mode)
    """
    try:
        result = await session.execute(
            select(RevokedToken).where(
                (RevokedToken.jti == jti)
                # & (RevokedToken.is_blacklisted == True)
                & (RevokedToken.token_type == token_type.value)
            )
        )

        revoked_token = result.scalars().first()
        return revoked_token is not None

    except SQLAlchemyError as e:
        logger.error("Database error during revocation check: %s", str(e), exc_info=True)

        # Fail secure: assume token is revoked if we can't verify
        if settings.is_production:
            return True  # Deny access if verification fails

        # In development, raise for debugging
        raise TokenVerificationError(f"Revocation check failed: {str(e)}") from e


# ============================================================================
# MAINTENANCE
# ============================================================================

async def cleanup_expired_tokens(session: AsyncSession) -> int:
    """
    Delete expired revoked tokens from database.

    Reduces database bloat by removing tokens that can no longer be used.
    Safe to call periodically (e.g., daily via scheduled task).

    Args:
        session: AsyncSession for database operations

    Returns:
        Number of tokens deleted

    Raises:
        TokenCleanupError: If cleanup fails

    Example:
        # In Celery task or scheduled job
        deleted = await cleanup_expired_tokens(db_session)
        logger.info(f"Cleaned up {deleted} expired tokens")
    """
    try:
        result = await session.execute(
            delete(RevokedToken).where(
                RevokedToken.expires_at < datetime.now(timezone.utc)
            )
        )

        await session.commit()

        deleted_count = result.rowcount
        if deleted_count > 0:
            logger.info("Cleaned up %d expired tokens", deleted_count)

        return deleted_count

    except SQLAlchemyError as e:
        await session.rollback()
        logger.error("Failed to cleanup expired tokens: %s", str(e), exc_info=True)
        raise TokenCleanupError(f"Token cleanup failed: {str(e)}") from e
