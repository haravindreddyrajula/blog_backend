"""
Production-Ready SQLAlchemy RevokedToken Model

Implements JWT token blacklist for logout functionality and security controls.

Author: Production Code Review Team
Status: Production-Ready
Last Updated: 2025-01-17
"""

from datetime import datetime
from enum import Enum

from sqlalchemy import (
    Column,
    DateTime,
    Enum as SQLEnum,
    Index,
    String,
    func,
)

from app.core.database import Base


class TokenType(str, Enum):
    """
    JWT token type enumeration.

    Distinguishes between different token purposes in the system.

    **Token Types:**
        ACCESS: Short-lived access token (10-30 minutes)
        REFRESH: Long-lived refresh token (days/weeks)
    """

    ACCESS = "access"
    REFRESH = "refresh"


class RevokedToken(Base):
    """
    Revoked JWT token model.

    Implements token blacklist for logout functionality and
    security controls on JWT tokens.

    **Attributes:**
        jti: JWT ID claim (unique identifier for token)
        token_type: Type of token (access or refresh)
        user_identity: User ID or email (for audit trail)
        revoked_at: When token was revoked (logout time)
        expires_at: When token naturally expires (for cleanup)
        reason: Revocation reason (logout, security, etc)

    **Constraints:**
        - jti: Primary key, unique per token (from JWT 'jti' claim)
        - token_type: Enum, must be 'access' or 'refresh'
        - user_identity: String, NOT NULL (tracks who logged out)
        - revoked_at: Auto-set to current time, indexed for queries
        - expires_at: Required, used for cleanup queries
        - reason: Optional, for audit trail (logout, security, etc)

    **Workflow:**
        1. User logs out â†’ token added to blacklist with revoke reason
        2. On EVERY protected endpoint:
           - Extract jti from JWT
           - Check if jti exists in revoked_tokens
           - Reject if found (token is revoked)
        3. Periodically cleanup expired tokens:
           - Run cron: DELETE FROM revoked_tokens WHERE expires_at < NOW()
           - Optional: Redis cache for high-traffic systems

    **Performance:**
        - jti indexed for O(1) lookups on every request
        - user_identity indexed for audit queries
        - expires_at indexed for cleanup queries
        - Consider Redis cache for high-traffic systems

    **Security Notes:**
        - JTI must be unique per token (check at token generation)
        - MUST check blacklist on EVERY protected endpoint
        - Never trust just expiration time (token might be revoked)
        - Clean up expired tokens periodically (prevents unbounded growth)
        - Optional: Cache in Redis for sub-millisecond lookups

    **Scaling Considerations:**
        - For <1000 QPS: Database-only is fine
        - For 1000-10000 QPS: Use Redis cache with database backup
        - For >10000 QPS: Use distributed cache (Redis Cluster)

    **Example Usage:**
        ```python
        from datetime import timedelta, timezone

        # Create token during logout
        token_revocation = RevokedToken(
            jti="550e8400-e29b-41d4-a716-446655440000",  # From JWT
            token_type=TokenType.ACCESS,
            user_identity="user@example.com",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            reason="User logout"
        )
        session.add(token_revocation)
        await session.commit()

        # Check if token revoked (on protected endpoint)
        result = await session.execute(
            select(RevokedToken).where(RevokedToken.jti == token_jti)
        )
        if result.scalar_one_or_none():
            raise HTTPException(status_code=401, detail="Token revoked")

        # Cleanup expired tokens (run periodically)
        await session.execute(
            delete(RevokedToken).where(
                RevokedToken.expires_at < datetime.now(timezone.utc)
            )
        )
        await session.commit()
        ```

    **Dependency Integration:**
        ```python
        # In your security/auth module
        async def verify_token_not_revoked(token: str) -> None:
            payload = jwt.decode(token, SECRET_KEY)
            jti = payload.get("jti")

            # Check database
            result = await session.execute(
                select(RevokedToken).where(RevokedToken.jti == jti)
            )
            if result.scalar_one_or_none():
                raise HTTPException(status_code=401, detail="Token revoked")
        ```
    """

    __tablename__ = "revoked_tokens"

    # ========================================================================
    # PRIMARY KEY (JTI from JWT)
    # ========================================================================

    jti = Column(
        String(36),  # UUID format: 8-4-4-4-12 = 36 chars
        primary_key=True,
        comment="JWT ID claim (unique token identifier from JWT 'jti' field)",
    )

    # ========================================================================
    # TOKEN METADATA
    # ========================================================================

    token_type = Column(
        SQLEnum(TokenType),
        nullable=False,
        index=True,
        comment="Token type: access (short-lived) or refresh (long-lived)",
    )

    user_identity = Column(
        String(255),
        nullable=False,
        index=True,
        comment="User ID or email (for audit trail of who logged out)",
    )

    # ========================================================================
    # TIMESTAMPS
    # ========================================================================

    revoked_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
        comment="When token was revoked (logout time)",
    )

    expires_at = Column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="When token naturally expires (for automatic cleanup)",
    )

    # ========================================================================
    # METADATA
    # ========================================================================

    reason = Column(
        String(255),
        nullable=True,
        comment="Revocation reason: 'logout', 'security', 'password_change', etc",
    )

    # ========================================================================
    # INDEXES
    # ========================================================================

    # __table_args__ = (
    #     Index("ix_revoked_tokens_jti", "jti", unique=True),
    #     Index("ix_revoked_tokens_token_type", "token_type"),
    #     Index("ix_revoked_tokens_user_identity", "user_identity"),
    #     Index("ix_revoked_tokens_expires_at", "expires_at"),  # For cleanup
    # )

    # ========================================================================
    # REPRESENTATION
    # ========================================================================

    def __repr__(self) -> str:
        return (
            f"<RevokedToken(jti={self.jti[:8]}..., "
            f"token_type={self.token_type}, revoked_at={self.revoked_at})>"
        )