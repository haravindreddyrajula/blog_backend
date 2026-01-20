"""
Production-ready password security module for FastAPI blog API.

Provides secure password hashing, validation, and generation using bcrypt.
Handles both string and bytes input, enforces complexity requirements,
and includes comprehensive error handling with audit logging.

Configuration:
    BCRYPT_ROUNDS: Number of bcrypt rounds (default: 12, range: 4-31)
                  - Lower = faster but less secure
                  - Higher = slower but more secure
                  - Recommended: 12 for modern hardware (~100ms per hash)
                  - Adjust for your specific server performance
"""

import logging
import os
import secrets
from typing import Union, Optional

from passlib.context import CryptContext
from passlib.exc import UnknownHashError

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION WITH VALIDATION
# ============================================================================

def _validate_bcrypt_rounds(rounds: int) -> None:
    """Validate bcrypt rounds configuration at startup."""
    if not isinstance(rounds, int):
        raise TypeError(f"BCRYPT_ROUNDS must be integer, got {type(rounds)}")
    if not (4 <= rounds <= 31):
        raise ValueError(
            f"BCRYPT_ROUNDS must be between 4 and 31 (recommended: 12). "
            f"Got {rounds}. "
            f"Higher = more secure but slower; lower = faster but less secure."
        )


# Load and validate configuration
bcrypt_rounds = int(os.getenv("BCRYPT_ROUNDS", "12"))
_validate_bcrypt_rounds(bcrypt_rounds)

# Password complexity requirements
MIN_PASSWORD_LENGTH = 8
REQUIRE_SPECIAL_CHAR = True
REQUIRE_MIXED_CASE = True
REQUIRE_DIGIT = True

# Character sets for password generation
LOWERCASE_CHARS = "abcdefghijklmnopqrstuvwxyz"
UPPERCASE_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
DIGIT_CHARS = "0123456789"
SPECIAL_CHARS = "!@#$%^&*()_+-=[]{}|;:,.<>?/"

# Combined charset for password generation (ensures we have all required character types)
FULL_CHARSET = LOWERCASE_CHARS + UPPERCASE_CHARS + DIGIT_CHARS + SPECIAL_CHARS

# Configure password hashing context (uses bcrypt as primary)
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=bcrypt_rounds,
    bcrypt__ident="2b",  # Use modern bcrypt variant (2b = 2y with implementation fix)
)

# ============================================================================
# CUSTOM EXCEPTIONS (Security-focused hierarchy)
# ============================================================================


class PasswordSecurityError(Exception):
    """Base exception for password-related security errors."""

    pass


class PasswordComplexityError(PasswordSecurityError):
    """Raised when password doesn't meet complexity requirements."""

    pass


class PasswordHashingError(PasswordSecurityError):
    """Raised when password hashing operation fails."""

    pass


class PasswordVerificationError(PasswordSecurityError):
    """Raised when password verification operation fails."""

    pass


class PasswordRehashError(PasswordSecurityError):
    """Raised when password rehash check fails."""

    pass


# ============================================================================
# PASSWORD COMPLEXITY VALIDATION
# ============================================================================


def validate_password_complexity(password: str) -> None:
    """
    Validate that password meets all complexity requirements.

    Requirements enforced:
    - Minimum 8 characters
    - At least one uppercase letter (if REQUIRE_MIXED_CASE)
    - At least one lowercase letter (if REQUIRE_MIXED_CASE)
    - At least one digit (if REQUIRE_DIGIT)
    - At least one special character from: !@#$%^&*()_+-=[]{}|;:,.<>?/

    Args:
        password: The password string to validate

    Raises:
        TypeError: If password is not a string
        PasswordComplexityError: If any requirement not met

    Examples:
        >>> validate_password_complexity("MyPass123!")
        # No exception raised - valid password

        >>> validate_password_complexity("weak")
        # Raises PasswordComplexityError: "Password must be at least 8 characters long"
    """
    if not isinstance(password, str):
        raise TypeError(f"Password must be string, got {type(password).__name__}")

    # Check length
    if len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordComplexityError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters long "
            f"(provided: {len(password)})"
        )

    # Check for special character
    if REQUIRE_SPECIAL_CHAR:
        if not any(c in SPECIAL_CHARS for c in password):
            raise PasswordComplexityError(
                f"Password must contain at least one special character from: {SPECIAL_CHARS}"
            )

    # Check for mixed case
    if REQUIRE_MIXED_CASE:
        has_upper = any(c.isupper() for c in password)
        has_lower = any(c.islower() for c in password)
        if not (has_upper and has_lower):
            raise PasswordComplexityError(
                "Password must contain both uppercase and lowercase letters"
            )

    # Check for digit
    if REQUIRE_DIGIT:
        if not any(c.isdigit() for c in password):
            raise PasswordComplexityError(
                "Password must contain at least one digit (0-9)"
            )


# ============================================================================
# PASSWORD HASHING
# ============================================================================


def hash_password(password: Union[str, bytes], validate_complexity: bool = True) -> str:
    """
    Hash a plaintext password for secure storage using bcrypt.

    Converts bytes to UTF-8 string if needed, validates complexity,
    then hashes using configured bcrypt settings.

    Args:
        password: Plaintext password to hash (str or bytes)
        validate_complexity: Whether to check complexity requirements (default: True)
                           Set False only for admin password resets

    Returns:
        str: Hashed password suitable for database storage
            Format: $2b$12$... (bcrypt format)

    Raises:
        TypeError: If password is not string or bytes
        PasswordComplexityError: If password fails complexity check
        PasswordHashingError: If hashing operation fails

    Security Notes:
        - Hashing time: ~100-150ms at bcrypt_rounds=12 (adjust per your hardware)
        - Hash size: ~60 characters
        - Each call produces different hash (salting included)
        - Never log plaintext passwords

    Examples:
        >>> hashed = hash_password("MySecurePass123!")
        >>> hashed.startswith("$2b$")
        True

        >>> # For admin resets (skip complexity check)
        >>> hashed = hash_password("TempPass1!", validate_complexity=False)
    """
    # Type validation
    if not isinstance(password, (str, bytes)):
        raise TypeError(
            f"Password must be string or bytes, got {type(password).__name__}"
        )

    # Convert bytes to string if needed
    if isinstance(password, bytes):
        try:
            password_str = password.decode("utf-8", errors="strict")
        except UnicodeDecodeError as e:
            raise PasswordHashingError(
                f"Password bytes not valid UTF-8: {str(e)}"
            ) from e
    else:
        password_str = password

    # Validate complexity if requested
    if validate_complexity:
        try:
            validate_password_complexity(password_str)
        except PasswordComplexityError:
            raise  # Re-raise complexity errors as-is

    # Perform hashing
    try:
        hashed = pwd_context.hash(password_str)
        logger.debug(
            "Password hashed successfully",
            extra={"operation": "hash", "algorithm": "bcrypt"},
        )
        return hashed
    except Exception as e:
        logger.error(
            "Password hashing failed",
            extra={"operation": "hash", "error": str(e)},
            exc_info=True,
        )
        raise PasswordHashingError(
            f"Failed to hash password: {str(e)}"
        ) from e


# ============================================================================
# PASSWORD VERIFICATION
# ============================================================================


def verify_password(plain_password: Union[str, bytes], hashed_password: str) -> bool:
    """
    Verify a plaintext password against a stored bcrypt hash.

    Handles bytes input by converting to UTF-8, then uses passlib
    for constant-time comparison (resistant to timing attacks).

    Args:
        plain_password: Plaintext password to check (str or bytes)
        hashed_password: Stored bcrypt hash from database (str)

    Returns:
        bool: True if password matches hash, False otherwise
              Always returns False on any error (fail-secure)

    Raises:
        TypeError: If inputs are wrong type
        ValueError: If hashed_password is empty or malformed

    Security Notes:
        - Uses constant-time comparison (immune to timing attacks)
        - Returns False rather than raising exception on hash errors
        - Invalid hashes treated as no-match (not exception)
        - Verification time: ~100-150ms (same as hash time)

    Examples:
        >>> hashed = hash_password("MyPass123!")
        >>> verify_password("MyPass123!", hashed)
        True
        >>> verify_password("WrongPass!", hashed)
        False
        >>> verify_password("MyPass123!", "invalid_hash")
        False  # No exception - security by default
    """
    # Type validation
    if not isinstance(plain_password, (str, bytes)):
        raise TypeError(
            f"Password must be string or bytes, got {type(plain_password).__name__}"
        )

    if not isinstance(hashed_password, str):
        raise TypeError(
            f"Hashed password must be string, got {type(hashed_password).__name__}"
        )

    if not hashed_password:
        raise ValueError("Hashed password cannot be empty")

    # Convert bytes to UTF-8 string
    try:
        if isinstance(plain_password, bytes):
            plain_password_str = plain_password.decode("utf-8", errors="strict")
        else:
            plain_password_str = plain_password
    except UnicodeDecodeError as e:
        logger.warning(
            "Password verification failed - invalid UTF-8",
            extra={"operation": "verify", "reason": "invalid_utf8"},
        )
        return False

    # Perform verification
    try:
        is_valid = pwd_context.verify(plain_password_str, hashed_password)
        logger.debug(
            "Password verification completed",
            extra={"operation": "verify", "result": is_valid},
        )
        return is_valid

    except UnknownHashError:
        logger.warning(
            "Password verification failed - invalid hash format",
            extra={"operation": "verify", "reason": "invalid_hash_format"},
        )
        return False

    except Exception as e:
        logger.error(
            "Password verification failed - unexpected error",
            extra={"operation": "verify", "error": str(e)},
            exc_info=True,
        )
        return False


# ============================================================================
# PASSWORD REHASHING
# ============================================================================


def needs_rehash(hashed_password: str) -> bool:
    """
    Check if a password hash needs to be rehashed (e.g., algorithm upgrade).

    Used during login to detect hashes created with old bcrypt settings.
    If algorithm or rounds change, old hashes should be upgraded on next login.

    Args:
        hashed_password: Stored bcrypt hash from database (str)

    Returns:
        bool: True if hash should be regenerated, False otherwise
              Returns True if hash format is invalid (fail-secure)

    Raises:
        TypeError: If hashed_password is not a string
        ValueError: If hashed_password is empty

    Security Notes:
        - Detects outdated bcrypt parameters (rounds)
        - Detects superseded hash algorithms
        - Always returns True for invalid/unparseable hashes (safe default)
        - Should trigger password rehash on next login

    Examples:
        >>> old_hash = hash_password("Pass123!")
        >>> needs_rehash(old_hash)
        False  # Current settings match

        >>> # After increasing BCRYPT_ROUNDS
        >>> needs_rehash(old_hash)
        True  # Should rehash on next login

        >>> needs_rehash("invalid_hash")
        True  # Invalid hash - mark for rehash
    """
    if not isinstance(hashed_password, str):
        raise TypeError(
            f"Hashed password must be string, got {type(hashed_password).__name__}"
        )

    if not hashed_password:
        raise ValueError("Hashed password cannot be empty")

    try:
        needs_update = pwd_context.needs_update(hashed_password)
        logger.debug(
            "Rehash check completed",
            extra={"operation": "rehash_check", "needs_update": needs_update},
        )
        return needs_update

    except UnknownHashError:
        logger.warning(
            "Rehash check failed - invalid hash format",
            extra={"operation": "rehash_check", "reason": "invalid_hash_format"},
        )
        return True  # Fail secure - mark invalid hashes for rehashing

    except Exception as e:
        logger.error(
            "Rehash check failed - unexpected error",
            extra={"operation": "rehash_check", "error": str(e)},
            exc_info=True,
        )
        return True  # Fail secure - mark problematic hashes for rehashing


# ============================================================================
# PASSWORD GENERATION
# ============================================================================


def generate_secure_password(length: int = 16) -> str:
    """
    Generate a cryptographically secure random password that meets all complexity requirements.

    Uses secrets module for cryptographic randomness, ensures password contains:
    - At least one lowercase letter
    - At least one uppercase letter
    - At least one digit
    - At least one special character
    - Remaining characters random from full charset

    Args:
        length: Desired password length in characters (minimum: 8, default: 16)

    Returns:
        str: Generated password meeting all complexity requirements

    Raises:
        ValueError: If length < 8
        PasswordHashingError: If unable to generate after max attempts

    Performance:
        - ~10-20ms for typical lengths (16 characters)
        - Uses rejection sampling to ensure requirements met
        - Maximum retry attempts: 100 (fail after that)

    Security Notes:
        - Uses secrets module (cryptographically secure)
        - Each character generated independently (true randomness)
        - No patterns or sequential characters
        - Suitable for temporary/admin passwords
        - Should be changed on first login if admin-generated

    Examples:
        >>> pwd = generate_secure_password()
        >>> len(pwd)
        16
        >>> validate_password_complexity(pwd)  # No exception
        >>> pwd2 = generate_secure_password(12)
        >>> pwd != pwd2
        True  # Always different due to randomness
    """
    if not isinstance(length, int):
        raise TypeError(f"Length must be integer, got {type(length).__name__}")

    if length < MIN_PASSWORD_LENGTH:
        raise ValueError(
            f"Password length must be at least {MIN_PASSWORD_LENGTH} characters, got {length}"
        )

    # Generate password ensuring complexity requirements
    max_attempts = 100
    for attempt in range(max_attempts):
        try:
            # Build password with required character types
            password_chars = [
                secrets.choice(LOWERCASE_CHARS),
                secrets.choice(UPPERCASE_CHARS),
                secrets.choice(DIGIT_CHARS),
                secrets.choice(SPECIAL_CHARS),
            ]

            # Fill remainder with random characters from full set
            remaining_length = length - len(password_chars)
            password_chars.extend(
                secrets.choice(FULL_CHARSET) for _ in range(remaining_length)
            )

            # Shuffle to avoid predictable pattern (required chars at start)
            # Use secrets-based shuffle for randomness
            shuffled = []
            remaining_indices = list(range(len(password_chars)))
            while remaining_indices:
                idx = secrets.randbelow(len(remaining_indices))
                shuffled.append(password_chars[remaining_indices.pop(idx)])

            password = "".join(shuffled)

            # Validate meets all requirements
            validate_password_complexity(password)
            logger.debug(
                "Secure password generated",
                extra={"operation": "generate", "length": length},
            )
            return password

        except PasswordComplexityError:
            # Retry - unlikely given our character selection
            if attempt == max_attempts - 1:
                logger.error(
                    "Failed to generate password meeting complexity requirements",
                    extra={
                        "operation": "generate",
                        "reason": "max_attempts_exceeded",
                        "attempts": max_attempts,
                    },
                )
                raise PasswordHashingError(
                    f"Failed to generate password after {max_attempts} attempts"
                )
            continue

    # Shouldn't reach here
    raise PasswordHashingError("Password generation failed unexpectedly")