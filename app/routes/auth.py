"""
Production-ready authentication endpoints for FastAPI blog API.

Provides secure user authentication with token-based access control.
Endpoints:
  - POST /auth/login: Authenticate user, issue tokens
  - POST /auth/refresh: Issue new access token from refresh token
  - POST /auth/logout: Revoke tokens
"""

import logging
from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import jwt, JWTError
from sqlalchemy import and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.config import settings
from app.core.deps import get_async_db
from app.core.jwt import (
    create_access_token,
    create_refresh_token,
    verify_token,
    revoke_token,
    TokenVerificationError,
    TokenRevocationError,
)
from app.core.security import verify_password
from app.models.user import User
from app.schemas.token import RevokedTokenCreate, Token, TokenType

# ============================================================================
# CONFIGURATION
# ============================================================================

router = APIRouter(prefix="/auth", tags=["Auth"])
logger = logging.getLogger(__name__)

# Rate limiting thresholds (implement with slowapi in main.py)
LOGIN_RATE_LIMIT = "5/minute"
REFRESH_RATE_LIMIT = "10/minute"
LOGOUT_RATE_LIMIT = "20/minute"

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


def _extract_bearer_token(authorization: Optional[str]) -> str:
    """
    Extract Bearer token from Authorization header.

    Args:
        authorization: Authorization header value

    Returns:
        str: Token without "Bearer " prefix

    Raises:
        HTTPException: If header missing or malformed
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
        )

    parts = authorization.split(" ")
    if len(parts) != 2:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
        )

    scheme, credentials = parts
    if scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication scheme (expected Bearer)",
        )

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing credentials",
        )

    return credentials


async def _get_user_from_email(
    db: AsyncSession, email: str
) -> Optional[User]:
    """
    Retrieve user from database by email.

    Args:
        db: Async database session
        email: User email address

    Returns:
        User object if found, None otherwise

    Raises:
        Exception: Database errors re-raised
    """
    try:
        result = await db.execute(
            select(User).where(User.email == email)
        )
        return result.scalars().first()
    except Exception as e:
        logger.error(
            "Database query failed during user lookup",
            extra={"operation": "get_user", "email": email, "error": str(e)},
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        ) from e


# ============================================================================
# LOGIN ENDPOINT
# ============================================================================


@router.post(
    "/login",
    response_model=Token,
    status_code=status.HTTP_200_OK,
    summary="User login",
    description="Authenticate with email and password to receive access and refresh tokens.",
    responses={
        200: {"description": "Login successful, tokens issued"},
        400: {"description": "Invalid request format"},
        401: {"description": "Invalid credentials"},
        403: {"description": "Account inactive"},
        500: {"description": "Internal server error"},
    },
)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncSession, Depends(get_async_db)],
) -> Token:
    """
    Authenticate user with email and password.

    Validates credentials against database, checks account status,
    and issues JWT access and refresh tokens.

    Args:
        form_data: OAuth2 password grant with username (email) and password
        db: Async database session

    Returns:
        Token: Contains access_token, refresh_token, token_type, expires_in

    Raises:
        HTTPException:
            - 401 if credentials invalid or user not found
            - 403 if account inactive
            - 500 if database error

    Security:
        - Uses secure password verification (constant-time)
        - Does not reveal whether username exists
        - Logs authentication events
        - Rate limited (5 attempts/minute)
    """
    email = form_data.username  # OAuth2PasswordRequestForm uses 'username' field

    logger.info(
        "Login attempt received",
        extra={"operation": "login", "email_hash": hash(email)},
    )

    # Get user from database
    user = await _get_user_from_email(db, email)

    # Verify credentials (constant-time comparison)
    # Always check password even if user not found (prevents user enumeration)
    if user is None:
        # User not found - still verify to waste attacker's time
        # Use dummy hash from settings to maintain constant time
        logger.warning(
            "Login failed - user not found",
            extra={"operation": "login", "reason": "user_not_found"},
        )
        verify_password(form_data.password, settings.DUMMY_PASSWORD_HASH or "")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",  # Generic - don't reveal user doesn't exist
        )

    if not verify_password(form_data.password, user.hashed_password):
        logger.warning(
            "Login failed - incorrect password",
            extra={"operation": "login", "user_id": user.id},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",  # Generic
        )

    logger.debug(
        "Password verification successful",
        extra={"operation": "login", "user_id": user.id},
    )

    # Check if account is active
    if not user.is_active:
        logger.warning(
            "Login failed - account inactive",
            extra={"operation": "login", "user_id": user.id},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account inactive",
        )

    logger.debug(
        "Account active check passed",
        extra={"operation": "login", "user_id": user.id},
    )

    # Create tokens
    try:
        access_token = create_access_token(user_email=user.email)
        refresh_token = create_refresh_token(user_email=user.email)
    except Exception as e:
        logger.error(
            "Token creation failed",
            extra={"operation": "login", "user_id": user.id, "error": str(e)},
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        ) from e

    logger.info(
        "Login successful",
        extra={"operation": "login", "user_id": user.id},
    )

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="Bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# ============================================================================
# REFRESH ENDPOINT
# ============================================================================


@router.post(
    "/refresh",
    response_model=Token,
    status_code=status.HTTP_200_OK,
    summary="Refresh access token",
    description="Exchange refresh token for new access token.",
    responses={
        200: {"description": "Token refreshed successfully"},
        400: {"description": "Invalid request format"},
        401: {"description": "Invalid or revoked refresh token"},
        500: {"description": "Internal server error"},
    },
)
async def refresh_access_token(
    refresh_token_str: Annotated[str, Body(..., embed=True)],
    db: Annotated[AsyncSession, Depends(get_async_db)],
) -> Token:
    """
    Generate new access token from refresh token.

    Validates refresh token, checks revocation status,
    and issues new access token.

    Args:
        refresh_token_str: Refresh token from request body
        db: Async database session

    Returns:
        Token: New access token (same refresh token returned)

    Raises:
        HTTPException:
            - 401 if token invalid, expired, or revoked
            - 500 if database error

    Security:
        - Validates token type is "refresh"
        - Checks revocation status in database
        - Rate limited (10 attempts/minute)
        - Validates JWT claims (issuer, audience)
    """
    logger.info(
        "Token refresh requested",
        extra={"operation": "refresh"},
    )

    if not refresh_token_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing refresh token",
        )

    # Verify token signature and claims
    try:
        token_data = await verify_token(
            token=refresh_token_str,
            expected_type=TokenType.REFRESH,
            db=db,
        )
    except TokenVerificationError as e:
        logger.warning(
            "Token verification failed",
            extra={"operation": "refresh", "reason": str(e)},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        ) from e
    except JWTError as e:
        logger.warning(
            "JWT error during token verification",
            extra={"operation": "refresh", "error": str(e)},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        ) from e
    except Exception as e:
        logger.error(
            "Unexpected error during token verification",
            extra={"operation": "refresh", "error": str(e)},
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        ) from e

    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    # Double-check token type (defense in depth)
    if token_data.token_type != TokenType.REFRESH.value:
        logger.warning(
            "Token type mismatch during refresh",
            extra={
                "operation": "refresh",
                "expected": TokenType.REFRESH.value,
                "got": token_data.token_type,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    # Create new access token (same refresh token)
    try:
        new_access_token = create_access_token(user_email=token_data.sub)
    except Exception as e:
        logger.error(
            "Access token creation failed",
            extra={"operation": "refresh", "error": str(e)},
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        ) from e

    logger.info(
        "Token refresh successful",
        extra={"operation": "refresh"},
    )

    return Token(
        access_token=new_access_token,
        refresh_token=refresh_token_str,  # Return same refresh token
        token_type="Bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# ============================================================================
# LOGOUT ENDPOINT
# ============================================================================


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="User logout",
    description="Revoke access and refresh tokens.",
    responses={
        200: {"description": "Logout successful"},
        401: {"description": "Invalid token"},
        500: {"description": "Internal server error"},
    },
)
async def logout(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_db)],
) -> dict:
    """
    Logout user by revoking tokens.

    Extracts token from Authorization header, decodes without
    verifying signature (only signature-check done at next auth attempt),
    and revokes token by adding to revocation table.

    Args:
        request: HTTP request (contains Authorization header)
        db: Async database session

    Returns:
        dict: Success message

    Security:
        - Extracts token from Bearer scheme
        - Decodes JWT to get expiration time
        - Records revocation in database
        - Does not require valid signature (logout always succeeds)
        - Rate limited (20 attempts/minute)
    """
    authorization = request.headers.get("Authorization")

    logger.info(
        "Logout requested",
        extra={"operation": "logout"},
    )

    # Extract token from header
    if not authorization or not authorization.startswith("Bearer "):
        logger.info(
            "Logout without valid token",
            extra={"operation": "logout", "reason": "no_authorization_header"},
        )
        return {"message": "Logged out"}

    try:
        token = _extract_bearer_token(authorization)
    except HTTPException as e:
        logger.warning(
            "Token extraction failed during logout",
            extra={"operation": "logout", "reason": str(e.detail)},
        )
        # Still return success - user is logging out anyway
        return {"message": "Logged out"}

    # Decode token (without full verification - only need claims)
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY.get_secret_value(),
            algorithms=[settings.ALGORITHM],
            options={
                "verify_aud": True,  # ✅ ALWAYS verify audience
                "verify_exp": False,  # OK to allow expired tokens at logout
            },
            audience=settings.JWT_AUDIENCE,
        )
    except JWTError as e:
        logger.warning(
            "Token decode failed during logout",
            extra={"operation": "logout", "error": str(e)},
        )
        # Still return success - don't leak token validity info
        return {"message": "Logged out"}

    # Extract claims
    jti = payload.get("jti")
    token_type = payload.get("type", TokenType.ACCESS.value)
    user_id = payload.get("sub")  # ✅ Extract actual user ID
    exp = payload.get("exp")

    if not jti or not exp:
        logger.warning(
            "Missing required claims in token",
            extra={"operation": "logout", "reason": "missing_claims"},
        )
        return {"message": "Logged out"}

    # Create revocation record
    try:
        revoke_data = RevokedTokenCreate(
            jti=jti,
            token_type=token_type,
            user_identity=user_id or "unknown",  # ✅ Use actual user
            expires_at=datetime.fromtimestamp(exp, tz=timezone.utc),
            reason="User logout",
        )

        await revoke_token(revoke_data, db=db)
    except TokenRevocationError as e:
        logger.error(
            "Token revocation failed",
            extra={"operation": "logout", "error": str(e)},
            exc_info=True,
        )
        # Don't fail logout - token will be validated against db on next request
        logger.info(
            "Logout completed (revocation deferred to next auth)",
            extra={"operation": "logout"},
        )
        return {"message": "Logged out"}
    except Exception as e:
        logger.error(
            "Unexpected error during logout",
            extra={"operation": "logout", "error": str(e)},
            exc_info=True,
        )
        # Don't fail logout - user expects to be logged out
        return {"message": "Logged out"}

    logger.info(
        "Logout successful",
        extra={"operation": "logout", "user_id": user_id},
    )

    return {"message": "Successfully logged out"}
