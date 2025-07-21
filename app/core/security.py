import logging
import os
import secrets
from passlib.context import CryptContext
from passlib.exc import UnknownHashError
from typing import Union

# Configure logging
logger = logging.getLogger(__name__)

# Configuration                           
bcrypt_rounds = int(os.getenv("BCRYPT_ROUNDS", "12"))
if not (4 <= bcrypt_rounds <= 31):  # reasonable bounds for bcrypt
    raise ValueError("BCRYPT_ROUNDS must be between 4 and 31")

# Password complexity requirements
MIN_PASSWORD_LENGTH = 8
REQUIRE_SPECIAL_CHAR = True
REQUIRE_MIXED_CASE = True
REQUIRE_DIGIT = True

# Configure password hashing context
pwd_context = CryptContext(
    schemes=["bcrypt"], 
    deprecated="auto",
    bcrypt__rounds=bcrypt_rounds, # Adjust based on your performance/security needs
    bcrypt__ident="2b"  # Use the modern bcrypt variant
)

class PasswordError(Exception):
    """Base exception for password-related errors"""
    pass

class PasswordComplexityError(PasswordError):
    """Raised when password doesn't meet complexity requirements"""
    pass

def validate_password_complexity(password: str) -> None:
    """
    Validate password meets complexity requirements.
    
    Args:
        password: The password to validate
    
    Raises:
        PasswordComplexityError: If password doesn't meet requirements
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordComplexityError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters long")
    
    if REQUIRE_SPECIAL_CHAR and not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?/" for c in password):
        raise PasswordComplexityError("Password must contain at least one special character")
    
    if REQUIRE_MIXED_CASE and (password.lower() == password or password.upper() == password):
        raise PasswordComplexityError("Password must contain both uppercase and lowercase letters")
    
    if REQUIRE_DIGIT and not any(c.isdigit() for c in password):
        raise PasswordComplexityError("Password must contain at least one digit")

def hash_password(password: Union[str, bytes], validate_complexity: bool = True) -> str:
    """
    Hash a password for secure storage.
    
    Args:
        password: The plaintext password to hash (str or bytes)
        validate_complexity: Whether to check password complexity rules
    
    Returns:
        The hashed password as a string
    
    Raises:
        TypeError: If password is not a string or bytes
        PasswordComplexityError: If password doesn't meet complexity requirements
    """
    if not isinstance(password, (str, bytes)):
        raise TypeError("Password must be string or bytes")
    
    if isinstance(password, bytes):
        password_str = password.decode('utf-8', errors='replace')
    else:
        password_str = password
    
    if validate_complexity:
        validate_password_complexity(password_str)
    
    try:
        return pwd_context.hash(password)
    except Exception as e:
        logger.error(f"Error hashing password: {str(e)}")
        raise PasswordError("Error hashing password") from e

def verify_password(plain_password: Union[str, bytes], hashed_password: str) -> bool:
    """
    Verify a password against a stored hash.
    
    Args:
        plain_password: The password to verify (str or bytes)
        hashed_password: The stored hash to compare against
    
    Returns:
        bool: True if password matches, False otherwise
    
    Raises:
        TypeError: If inputs are of wrong type
        ValueError: If hashed password is malformed
    """
    if not isinstance(plain_password, (str, bytes)):
        raise TypeError("Password must be string or bytes")
    if not isinstance(hashed_password, str):
        raise TypeError("Hashed password must be string")
    if not hashed_password:
        raise ValueError("Empty hash provided")
    
    try:
        if isinstance(plain_password, str):
            plain_password = plain_password.encode("utf-8")
        
        return pwd_context.verify(plain_password, hashed_password)
    except UnknownHashError as e:
        logger.error(f"Invalid hash format during verification: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error during verification: {str(e)}")
        return False

def needs_rehash(hashed_password: str) -> bool:
    """
    Check if a password hash needs rehashing (e.g., due to algorithm upgrades)
    
    Args:
        hashed_password: The stored hash to check
    
    Returns:
        bool: True if needs rehash, False otherwise
    
    Raises:
        ValueError: If hashed password is malformed
    """
    if not hashed_password:
        raise ValueError("Empty hash provided")
    
    try:
        return pwd_context.needs_update(hashed_password)
    except UnknownHashError as e:
        logger.error(f"Invalid hash format during rehash check: {str(e)}")
        return True  # Force rehash if we can't parse the existing hash
    except Exception as e:
        logger.error(f"Unexpected error during rehash check: {str(e)}")
        return True

def generate_secure_password(length: int = 16) -> str:
    """
    Generate a cryptographically secure random password that meets complexity requirements
    
    Args:
        length: Length of password to generate (minimum 8)
    
    Returns:
        str: Generated password
    
    Raises:
        ValueError: If length is too short
    """
    if length < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password length must be at least {MIN_PASSWORD_LENGTH}")
    
    charset = (
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789"
        "!@#$%^&*"
    )
    
    while True:
        password = "".join(secrets.choice(charset) for _ in range(length))
        try:
            validate_password_complexity(password)
            return password
        except PasswordComplexityError:
            continue  # Try again if by chance we didn't meet requirements
