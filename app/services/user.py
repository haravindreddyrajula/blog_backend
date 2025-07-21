import logging
from typing import Annotated, AsyncIterator, Optional
from fastapi.security import OAuth2PasswordBearer, SecurityScopes
from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends, HTTPException, status
from app.core.config import settings
from app.core.deps import get_async_db
from app.core.jwt import is_token_revoked, verify_token
from app.models.user import User

# Configure OAuth2 with auto_error=False for more control
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/login",
    auto_error=False,
    scopes={
        "blog:read": "Read blog posts",
        "blog:write": "Create/edit blog posts",
        "user:admin": "Admin operations"
    }
)

logger = logging.getLogger(__name__)

async def get_current_active_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_async_db)],
    security_scopes: SecurityScopes = SecurityScopes([])
) -> User:
    
    """
    Dependency to get the current active user with verified token and proper scopes.
    Raises HTTP 401 if unauthenticated or user inactive.
    """

    # Verify token exists
    if token is None:
        logger.debug("Current User - token is none")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Verify token with all security checks
    token_data = await verify_token(token, expected_type="access", db=db)
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check token revocation -> repeated in verify token
    # if await is_token_revoked(token_data.jti, db=db_provider):
    #     logger.info("is_token_revoked not received")
    #     raise HTTPException(
    #         status_code=status.HTTP_401_UNAUTHORIZED,
    #         detail="Revoked token",
    #         headers={"WWW-Authenticate": "Bearer"},
    #     )
    
    # Get user from database
    user = await get_user_by_identity(token_data.sub, db=db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    
    # Check active status
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user account",
        )
    
    # Verify scopes if required
    # if security_scopes.scopes:
    #     authenticate_value = f'Bearer scope="{security_scopes.scope_str}"'
    #     for scope in security_scopes.scopes:
    #         if scope not in token_data.scopes:
    #             raise HTTPException(
    #                 status_code=status.HTTP_403_FORBIDDEN,
    #                 detail="Insufficient permissions",
    #                 headers={"WWW-Authenticate": authenticate_value},
    #             )
    # else:
    #     authenticate_value = "Bearer"
    
    logger.info(f"user - {user.email} retrieved successfully")

    return user

async def get_user_by_identity(identity: str, db: AsyncSession = Depends(get_async_db)) -> Optional[User]:
        """Fetch user by email or ID with proper error handling"""
        #async with db as session:
        try:
            # Single query that checks both email and ID
            result = await db.execute(
                select(User).where(or_(
                    User.email == identity,
                    User.id == identity
                ))
            )
            return result.scalars().first()
        except SQLAlchemyError as e:
            if settings.DEBUG:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Database error: {str(e)}",
                )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Service temporarily unavailable",
            )
    
 
    