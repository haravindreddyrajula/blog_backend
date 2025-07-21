from datetime import datetime
import logging
from typing import Annotated, AsyncIterator
from fastapi import APIRouter, Body, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import jwt, JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.deps import get_async_db
from app.schemas.user import UserLogin
from app.schemas.token import RevokedTokenCreate, Token
from app.models.user import User
from app.core.security import verify_password
from app.core.jwt import create_access_token, is_token_revoked, revoke_token, verify_token
from app.core.config import settings
from app.services.user import get_current_active_user, oauth2_scheme

router = APIRouter(prefix="/auth", tags=["Auth"])

logger = logging.getLogger(__name__)

# @router.post("/login", response_model=Token, status_code=status.HTTP_200_OK)
# async def login(user_cred: UserLogin, db_provider: Annotated[AsyncIterator[AsyncSession], Depends(get_async_db)]):

#     async with db_provider as session:
#         result = await session.execute(select(User).where(User.email == user_cred.email))
#         user = result.scalars().first()

#         if not user or not verify_password(user_cred.password, user.hashed_password):
#             raise HTTPException(
#                 status_code=status.HTTP_401_UNAUTHORIZED,
#                 detail="Incorrect username or password",
#                 headers={"WWW-Authenticate": "Bearer"},
#             )

#         if not user.is_active:
#             raise HTTPException(
#                 status_code=status.HTTP_403_FORBIDDEN,
#                 detail="Account inactive"
#             )

#         access_token = create_access_token(data={"sub": user.email})
#         return {
#             "access_token": access_token,
#             "token_type": "Bearer",
#             "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
#         }

# TODO : Integerate with normal login
@router.post("/login", response_model=Token, status_code=status.HTTP_200_OK)
async def login(db_provider: Annotated[AsyncIterator[AsyncSession], Depends(get_async_db)],form_data: OAuth2PasswordRequestForm = Depends()):

    async with db_provider as session:

        logger.info(f"Received Login request for : {form_data.username}")
        result = await session.execute(select(User).where(User.email == form_data.username))
        user = result.scalars().first()

        if not user or not verify_password(form_data.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password"
            )
        
        logger.debug(f"Auth Login: password Verified for user: {form_data.username}")

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account inactive"
            )
        
        logger.debug(f"Auth Login: User is active: {form_data.username}")

        access_token = create_access_token(data={"sub": user.email})

        logger.info(f"Login successful for user: {form_data.username}")

        return {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        }

@router.post("/refresh", response_model=Token)
async def refresh_token(
    refresh_token: str = Body(..., embed=True)
):
    try:
        token_data = verify_token(refresh_token, expected_type="refresh")

        if not token_data:
            raise HTTPException(status_code=401, detail="Invalid refresh token")
        
        # Check if refresh token is revoked
        if await is_token_revoked(token_data.jti):
            raise HTTPException(status_code=401, detail="Token revoked")
        
        # Create new access token
        access_token = create_access_token(data={"sub": token_data.sub})
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,  # You may rotate refresh tokens here
            "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        }
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token"
        )
    
@router.post("/logout")
async def logout(
    db: Annotated[AsyncSession, Depends(get_async_db)],
    current_user: User = Depends(get_current_active_user),
    token: str = Depends(oauth2_scheme) 
):
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY.get_secret_value(),
            algorithms=[settings.ALGORITHM],
            options={"verify_aud": False}  # For logout, verification can be lighter
        )

        revoke_token_data = RevokedTokenCreate(
            jti=payload.get("jti"),
            token_type=payload.get("type", "access"), # making "access" default if no type found
            user_identity=current_user.email,
            expires_at=datetime.fromtimestamp(payload["exp"]),
            reason="Logout"
        )
        
        await revoke_token(
            revoke_token_data,
            db=db
        )
        
        logger.info("logout successful")

        return {"message": "Successfully logged out"}
        
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )