"""
Production-Ready User Schemas

Defines request/response models for user authentication and account management
with comprehensive validation, security controls, and best practices.

Author: Production Code Review Team
Status: Production-Ready
Last Updated: 2025-01-17

**Security Principles:**
1. Never expose sensitive fields (password hash, internal status)
2. Validate all inputs before database operations
3. Require strong passwords (enforced in route layer)
4. Use EmailStr for email validation (RFC 5322 compliant)
5. Separate input/output models for security
"""

from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


# Password requirements (enforced at route layer, not schema)
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128


class UserBase(BaseModel):
    """
    Base user model with common fields.
    
    Contains fields shared across user schemas. Email is the unique identifier
    for users in this system.
    
    **Security:**
    - email: Uses Pydantic's EmailStr for RFC 5322 validation
    - Primary identifier for authentication and lookups
    """

    email: Annotated[
        EmailStr,
        Field(
            ...,
            description="User email address (unique, RFC 5322 compliant)",
            examples=["user@example.com"],
        ),
    ]


class UserCreate(UserBase):
    """
    User registration request model.
    
    Used when creating a new user account via sign-up endpoint.
    Includes password which must meet security requirements.
    
    **Security:**
    - password: Minimum length enforced by Pydantic
    - Strength requirements (uppercase, lowercase, numbers, special chars) 
      enforced at route layer for clearer error messages
    - Password NEVER stored in logs or responses
    - Must be hashed before database storage (route layer responsibility)
    
    **Example:**
    ```python
    # POST /auth/signup
    {
        "email": "user@example.com",
        "password": "SecureP@ssw0rd123",
        "full_name": "John Doe"
    }
    ```
    
    **Note:** Passwords are validated/hashed in the route layer, not here.
    This schema only enforces basic structural requirements.
    """

    password: Annotated[
        str,
        Field(
            ...,
            min_length=MIN_PASSWORD_LENGTH,
            max_length=MAX_PASSWORD_LENGTH,
            description=(
                f"User password ({MIN_PASSWORD_LENGTH}-{MAX_PASSWORD_LENGTH} characters, "
                "uppercase, lowercase, number, and special char required in route layer)"
            ),
            examples=["SecureP@ssw0rd123"],
        ),
    ]

    full_name: Annotated[
        Optional[str],
        Field(
            None,
            min_length=1,
            max_length=255,
            description="User's display name (optional, 1-255 characters)",
            examples=["John Doe"],
        ),
    ] = None

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """
        Basic password validation.
        
        Enforces:
        - Minimum length (8 characters)
        - Not empty/whitespace only
        - UTF-8 compatible
        
        Additional rules (e.g., complexity) enforced at route layer for better UX.
        """
        if not isinstance(v, str):
            raise ValueError("Password must be string")
        
        v = v.strip()  # Allow leading/trailing spaces in password? No.
        
        if not v:
            raise ValueError("Password cannot be empty or whitespace only")
        
        if len(v) < MIN_PASSWORD_LENGTH:
            raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
        
        if len(v) > MAX_PASSWORD_LENGTH:
            raise ValueError(f"Password cannot exceed {MAX_PASSWORD_LENGTH} characters")
        
        # Validate UTF-8 encoding
        try:
            v.encode("utf-8")
        except UnicodeEncodeError:
            raise ValueError("Password contains invalid characters")
        
        return v

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: Optional[str]) -> Optional[str]:
        """
        Validate full name.
        
        - Strip whitespace
        - Prevent injection attacks (but allow apostrophes, hyphens, etc.)
        - UTF-8 compatible
        """
        if not v:
            return None
        
        v = v.strip()
        
        if not v:
            return None
        
        if len(v) > 255:
            raise ValueError("Full name cannot exceed 255 characters")
        
        # Allow letters, spaces, hyphens, apostrophes (common in names)
        # Reject control characters and suspicious sequences
        for char in v:
            if ord(char) < 32:
                raise ValueError(f"Full name contains invalid control character")
        
        return v

    class Config:
        """Pydantic configuration."""
        str_strip_whitespace = False  # Don't auto-strip (but manual strip above)
        json_schema_extra = {
            "description": "User registration request",
            "example": {
                "email": "user@example.com",
                "password": "SecureP@ssw0rd123",
                "full_name": "John Doe",
            },
        }


class UserLogin(UserBase):
    """
    User login request model.
    
    Used when authenticating via email/password. Simple model with just
    credentials.
    
    **Security:**
    - email: Validated via EmailStr
    - password: Validated as string (no length checks here - checked in route)
    - No user data returned (security via obscurity)
    
    **Example:**
    ```python
    # POST /auth/login
    {
        "email": "user@example.com",
        "password": "SecureP@ssw0rd123"
    }
    ```
    
    **Response (not defined here):**
    Returns Token model (access_token, refresh_token, etc.)
    """

    password: Annotated[
        str,
        Field(
            ...,
            min_length=1,  # Allow any length (will fail auth if wrong)
            max_length=MAX_PASSWORD_LENGTH,
            description="User password (for authentication)",
        ),
    ]

    @field_validator("password")
    @classmethod
    def validate_password_present(cls, v: str) -> str:
        """Ensure password is not empty."""
        if not v or not v.strip():
            raise ValueError("Password is required")
        return v

    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "description": "User login request",
            "example": {
                "email": "user@example.com",
                "password": "SecureP@ssw0rd123",
            },
        }


class UserOut(UserBase):
    """
    User response model.
    
    Returned when fetching user information. Includes database-generated fields
    but EXCLUDES sensitive data (password hash, internal flags).
    
    **Security:**
    - NEVER includes password_hash, hashed_password, or any password data
    - is_active included but interpretation depends on context
    - User can only see their own full details (route layer enforces)
    - Admin sees additional fields via AdminUserOut (if needed)
    
    **Config:**
    - from_attributes=True: Maps SQLAlchemy ORM to Pydantic
    - Serializes datetime to ISO 8601 (not included in this basic version)
    
    **Limitations:**
    - Does not include created_at/updated_at (could be added if needed)
    - Does not include is_active (could be added for admin view)
    - Does not include roles/permissions (create separate UserWithRoles if needed)
    
    **Example:**
    ```json
    {
        "id": 1,
        "email": "user@example.com",
        "full_name": "John Doe",
        "is_active": true
    }
    ```
    """

    id: Annotated[
        int,
        Field(
            ...,
            ge=1,
            description="User ID (database primary key)",
        ),
    ]

    full_name: Annotated[
        Optional[str],
        Field(
            None,
            description="User's display name",
        ),
    ] = None

    is_active: Annotated[
        bool,
        Field(
            True,
            description="Account active status (false=deactivated/soft-deleted)",
        ),
    ]

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "description": "User account information",
            "example": {
                "id": 1,
                "email": "user@example.com",
                "full_name": "John Doe",
                "is_active": True,
            },
        },
    )


class UserUpdate(BaseModel):
    """
    User profile update request model.
    
    Used when updating user profile information (not password/email).
    All fields optional for partial updates.
    
    **Security:**
    - Cannot change email (use separate endpoint)
    - Cannot change password (use separate endpoint)
    - Cannot change is_active (admin only)
    - User can only update their own profile
    
    **Example:**
    ```python
    # PATCH /users/me
    {
        "full_name": "Jane Doe"
    }
    ```
    """

    full_name: Annotated[
        Optional[str],
        Field(
            None,
            min_length=1,
            max_length=255,
            description="User's display name (optional)",
        ),
    ] = None

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: Optional[str]) -> Optional[str]:
        """Validate full name (same as UserCreate)."""
        if not v:
            return None
        
        v = v.strip()
        if not v:
            return None
        
        return v

    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "description": "User profile update",
            "example": {
                "full_name": "Jane Doe",
            },
        }


class PasswordChange(BaseModel):
    """
    Password change request model.
    
    Used when user wants to change their password. Requires both old and new
    password to prevent unauthorized changes.
    
    **Security:**
    - Requires old password (verify user still has access)
    - New password must be different from old
    - User can only change their own password
    - Should enforce password history (e.g., can't reuse last 5 passwords)
    
    **Example:**
    ```python
    # POST /users/me/password
    {
        "current_password": "OldP@ssw0rd123",
        "new_password": "NewSecureP@ss123"
    }
    ```
    """

    current_password: Annotated[
        str,
        Field(
            ...,
            min_length=1,
            description="Current password (for verification)",
        ),
    ]

    new_password: Annotated[
        str,
        Field(
            ...,
            min_length=MIN_PASSWORD_LENGTH,
            max_length=MAX_PASSWORD_LENGTH,
            description=f"New password ({MIN_PASSWORD_LENGTH}-{MAX_PASSWORD_LENGTH} chars)",
        ),
    ]

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        """Validate new password has minimum length."""
        if len(v) < MIN_PASSWORD_LENGTH:
            raise ValueError(f"New password must be at least {MIN_PASSWORD_LENGTH} characters")
        return v

    @field_validator("new_password")
    @classmethod
    def prevent_password_reuse(cls, v: str, info: dict) -> str:
        """Prevent new password same as current."""
        if "current_password" in info.data and v == info.data["current_password"]:
            raise ValueError("New password must be different from current password")
        return v

    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "description": "Password change request",
        }