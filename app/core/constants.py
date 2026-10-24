from typing import Final

UNEXPECTED_ERROR: Final[str] = "Unexpected error occurred"


# Pagination
DEFAULT_PAGE_SIZE: Final[int] = 10
MAX_PAGE_SIZE: Final[int] = 50

DEFAULT_LIMIT: Final[int] = 10
MAX_LIMIT: Final[int] = 100


# Blog / SEO
SLUG_MAX_LENGTH: Final[int] = 200
META_DESCRIPTION_MAX_LENGTH: Final[int] = 160
WORDS_PER_MINUTE: Final[int] = 200

# Images
ALLOWED_IMAGE_TYPES: Final[frozenset[str]] = frozenset(
    {"image/jpeg", "image/png", "image/webp"}
)
MAX_IMAGE_SIZE_BYTES: Final[int] = 5 * 1024 * 1024

# Auth
BEARER_TOKEN_TYPE: Final[str] = "bearer"
