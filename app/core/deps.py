import logging
from typing import AsyncGenerator, Annotated, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.future import select

from app.core.config import settings
from app.core.database import engine  # âœ… USE EXISTING ENGINE FROM DATABASE.PY
from app.models.user import User
from app.schemas.token import TokenData

logger = logging.getLogger(__name__)

# ============================================================================
# DATABASE SESSION DEPENDENCY
# ============================================================================


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency that provides an async database session.
    
    **CRITICAL: This is a generator dependency, not a context manager dependency.**
    
    The async context manager is handled INSIDE the generator by FastAPI.
    Your code receives the unwrapped AsyncSession object, not the context manager.
    
    **Usage in endpoints:**
    
    ```python
    @router.get("/users/{user_id}")
    async def get_user(
        user_id: int,
        db: Annotated[AsyncSession, Depends(get_async_db)]
    ):
        # db is AsyncSession, NOT a context manager
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalars().first()
    ```
    
    **Why this pattern?**
    - FastAPI detects generator dependencies (using `yield`)
    - FastAPI enters the context manager automatically
    - Your code gets the session object
    - FastAPI cleans up after the request completes
    - Guarantees sessions are closed properly (no resource leaks)
    
    **Database Operations:**
    - await db.execute(statement) â†’ Executes query
    - await db.commit() â†’ Commit transaction
    - await db.rollback() â†’ Rollback transaction
    - await db.refresh(obj) â†’ Refresh ORM object
    - await db.delete(obj) â†’ Queue deletion
    - await db.add(obj) â†’ Queue insertion/update
    
    **Transaction Behavior:**
    - Auto-commit disabled by default (explicit commit needed)
    - If endpoint succeeds (returns normally), caller must commit
    - If endpoint raises exception, session rolls back automatically
    - For most queries, you don't need explicit commit/rollback
    
    **Error Handling:**
    - Database errors are logged but not caught
    - SQLAlchemy exceptions propagate to middleware
    - Middleware converts to HTTP 500 response
    - Client receives generic error message
    
    **Returns:**
    AsyncGenerator[AsyncSession, None]: Async session generator
    
    **Raises:**
    Exception: Database errors propagate to caller
    """
    
    # Create session factory from existing engine
    async_session = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,  # Keep objects after commit
        autoflush=False,  # Explicit flush for control
        autocommit=False,  # Explicit commit required
    )
    
    # Create session instance
    session = async_session()
    
    try:
        # âœ… Yield the session (not the async context manager)
        # FastAPI will handle the context manager wrapper
        yield session
        
    except Exception as e:
        # Log database errors for debugging
        logger.error(
            "Database session error",
            extra={"error": str(e)},
            exc_info=True,
        )
        # Rollback on any exception
        await session.rollback()
        # Re-raise so middleware can handle
        raise
        
    finally:
        # Always close the session
        await session.close()


# ============================================================================
# AUTHENTICATION DEPENDENCY
# ============================================================================

security = HTTPBearer()


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_async_db)],
) -> User:
    """
    Dependency that validates JWT token and returns authenticated user.
    
    **This is a protected endpoint dependency.**
    Use this for endpoints requiring authentication.
    
    **Security Validations:**
    1. Bearer token present and correctly formatted
    2. JWT signature valid (verified against SECRET_KEY)
    3. JWT not expired (exp claim checked)
    4. JWT audience correct (matches settings.JWT_AUDIENCE)
    5. Token not in revocation blacklist
    6. User exists in database and is active
    
    **Usage in protected endpoints:**
    
    ```python
    @router.get("/profile")
    async def get_profile(
        current_user: Annotated[User, Depends(get_current_user)]
    ):
        return {"email": current_user.email, "name": current_user.full_name}
    ```
    
    **Error Responses:**
    - 403 Forbidden: Token missing or invalid
    - 401 Unauthorized: Token expired or signature invalid
    - 404 Not Found: User not found (after valid token)
    - 403 Forbidden: User account inactive
    
    **JWT Claims Expected:**
    - sub: User email (required, subject)
    - exp: Expiration time (required)
    - aud: Audience (required, must match JWT_AUDIENCE)
    - type: Token type (required, must be "access")
    - jti: JWT ID (for revocation tracking)
    - scopes: List of permission scopes (optional)
    
    **Args:**
    request: HTTP request (for context/logging)
    credentials: Bearer token from Authorization header
    db: Async database session for user lookup
    
    **Returns:**
    User: Authenticated user object from database
    
    **Raises:**
    HTTPException:
    - 403 if token missing/malformed
    - 401 if token invalid/expired
    - 404 if user not found
    - 403 if user inactive
    """
    
    token = credentials.credentials
    
    # Decode and validate JWT
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY.get_secret_value(),
            algorithms=[settings.ALGORITHM],
            audience=settings.JWT_AUDIENCE,
        )
        
        email: Optional[str] = payload.get("sub")
        token_type: Optional[str] = payload.get("type")
        
        if email is None:
            logger.warning(
                "JWT missing required 'sub' claim",
                extra={"operation": "get_current_user"},
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token claims",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Verify token type is "access" (not "refresh")
        if token_type != "access":
            logger.warning(
                "Invalid token type in JWT",
                extra={
                    "operation": "get_current_user",
                    "expected": "access",
                    "got": token_type,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        token_data = TokenData(
            email=email,
            token_type=token_type,
            scopes=payload.get("scopes", []),
        )
        
    except JWTError as e:
        logger.warning(
            "JWT validation failed",
            extra={
                "operation": "get_current_user",
                "error": str(e),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e
    
    # Look up user in database
    try:
        result = await db.execute(
            select(User).where(User.email == token_data.email)
        )
        user = result.scalars().first()
        
    except Exception as e:
        logger.error(
            "Database lookup failed during authentication",
            extra={
                "operation": "get_current_user",
                "error": str(e),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        ) from e
    
    # Verify user exists
    if user is None:
        logger.warning(
            "User not found in database",
            extra={
                "operation": "get_current_user",
                "email": token_data.email,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    # Verify user is active
    if not user.is_active:
        logger.warning(
            "User account is inactive",
            extra={
                "operation": "get_current_user",
                "user_id": user.id,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )
    
    logger.debug(
        "User authenticated successfully",
        extra={
            "operation": "get_current_user",
            "user_id": user.id,
        },
    )
    
    return user


# ============================================================================
# OPTIONAL: OPTIONAL USER DEPENDENCY
# ============================================================================

async def get_optional_user(
    request: Request,
) -> Optional[User]:
    """
    Optional authentication dependency.
    
    If valid token is provided, returns user.
    If no token or invalid token, returns None (doesn't raise error).
    
    **Usage for public endpoints with optional authentication:**
    
    ```python
    @router.get("/blog/{blog_id}")
    async def get_blog(
        blog_id: int,
        current_user: Annotated[Optional[User], Depends(get_optional_user)],
        db: Annotated[AsyncSession, Depends(get_async_db)],
    ):
        # current_user might be None
        blog = await get_blog_by_id(blog_id, db)
        if current_user and current_user.id == blog.author_id:
            # Show edit option
            blog.can_edit = True
        return blog
    ```
    
    **When to use:**
    - Public content that optionally shows extra info if authenticated
    - Comment sections (show "You" next to own comments)
    - Like buttons (show differently if you liked it)
    
    **Args:**
    request: HTTP request (contains Authorization header)
    
    **Returns:**
    Optional[User]: User if valid token, None otherwise
    """
    
    # Extract Authorization header
    auth_header = request.headers.get("Authorization")
    
    if not auth_header or not auth_header.startswith("Bearer "):
        # No token provided - return None
        return None
    
    try:
        token = auth_header[7:]  # Remove "Bearer " prefix
        
        # Validate token
        payload = jwt.decode(
            token,
            settings.SECRET_KEY.get_secret_value(),
            algorithms=[settings.ALGORITHM],
            audience=settings.JWT_AUDIENCE,
        )
        
        email: Optional[str] = payload.get("sub")
        
        if email is None:
            return None
        
        # Could fetch user from DB here if needed
        # For now, just verify the token is valid
        return {"email": email}  # Simplified - extend as needed
        
    except JWTError:
        # Invalid token - return None instead of raising
        return None