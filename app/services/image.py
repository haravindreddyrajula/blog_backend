# ============================================================================
# IMAGE UPLOAD MODULE - PRODUCTION-READY
# ============================================================================
#
# Handles secure image uploads with comprehensive validation.
#
# Features:
# - Content-type validation via magic bytes (not just extension)
# - Path traversal prevention
# - Disk space validation
# - Secure filename generation
# - Proper error handling without information leakage
# - Configurable upload directory and size limits
# - Comprehensive audit logging
#
# Dependencies: aiofiles, pillow (for image validation)
# Environment: UPLOAD_DIR, MAX_IMAGE_SIZE_MB
#
# ============================================================================

import logging
import io
import os
from pathlib import Path
from typing import Optional
from uuid import uuid4

import aiofiles
from fastapi import APIRouter, File, HTTPException, UploadFile, status
from PIL import Image
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================

# Read from environment, with sensible defaults
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "static/uploads")).resolve()
MAX_FILE_SIZE_BYTES = int(os.getenv("MAX_IMAGE_SIZE_MB", 5)) * 1024 * 1024
MIN_DISK_SPACE_BYTES = 100 * 1024 * 1024  # 100MB reserved

# Allowed image types with MIME type validation
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}
ALLOWED_MIMETYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp"
}

# Magic bytes (file signatures) for format validation
MAGIC_BYTES = {
    b"\xff\xd8\xff": "jpg",      # JPEG
    b"\x89\x50\x4e\x47": "png",  # PNG
    b"\x47\x49\x46": "gif",      # GIF (87a/89a)
    b"\x52\x49\x46\x46": "webp", # WebP (RIFF header)
}

# Image dimension limits (prevent DOS via huge images)
MAX_IMAGE_WIDTH = 4000
MAX_IMAGE_HEIGHT = 4000
MIN_IMAGE_WIDTH = 1
MIN_IMAGE_HEIGHT = 1

# ============================================================================
# RESPONSE MODELS
# ============================================================================

class ImageUploadResponse(BaseModel):
    """Response model for successful image upload."""
    url: str
    filename: str
    size_bytes: int
    
    class Config:
        schema_extra = {
            "example": {
                "url": "/static/uploads/550e8400-e29b-41d4-a716-446655440000.jpg",
                "filename": "550e8400-e29b-41d4-a716-446655440000.jpg",
                "size_bytes": 245678
            }
        }

# ============================================================================
# ROUTER
# ============================================================================

router = APIRouter(prefix="/images", tags=["Images"])

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _ensure_upload_directory() -> None:
    """Ensure upload directory exists and is writable."""
    try:
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        
        # Test write permission
        test_file = UPLOAD_DIR / ".write_test"
        test_file.touch()
        test_file.unlink()
        
        logger.info(f"Upload directory verified: {UPLOAD_DIR}")
    except OSError as e:
        logger.critical(f"Upload directory not writable: {UPLOAD_DIR}: {e}")
        raise RuntimeError(f"Upload directory error: {e}") from e


def _get_available_disk_space() -> int:
    """Get available disk space in bytes."""
    stat = os.statvfs(UPLOAD_DIR)
    available = stat.f_bavail * stat.f_frsize
    return available


def _validate_disk_space() -> None:
    """Ensure sufficient disk space before upload."""
    available = _get_available_disk_space()
    
    if available < (MAX_FILE_SIZE_BYTES + MIN_DISK_SPACE_BYTES):
        error_msg = f"Insufficient disk space. Required: {MAX_FILE_SIZE_BYTES + MIN_DISK_SPACE_BYTES} bytes, Available: {available} bytes"
        logger.warning(error_msg)
        raise HTTPException(
            status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
            detail="Server storage full. Please try again later."
        )


def _verify_file_signature(data: bytes) -> Optional[str]:
    """
    Verify file is actually an image by checking magic bytes.
    
    Returns:
        Detected format (jpg/png/gif/webp) or None if not recognized
    """
    for magic, fmt in MAGIC_BYTES.items():
        if data.startswith(magic):
            return fmt
    return None


async def _validate_image_dimensions(file_data: bytes) -> None:
    """
    Validate image dimensions are within acceptable range.
    Prevents DOS via extremely large images.
    
    Raises:
        HTTPException: If dimensions invalid
    """
    try:
        image = Image.open(io.BytesIO(file_data))
        width, height = image.size
        
        if not (MIN_IMAGE_WIDTH <= width <= MAX_IMAGE_WIDTH and 
                MIN_IMAGE_HEIGHT <= height <= MAX_IMAGE_HEIGHT):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Image dimensions {width}x{height} exceed limits ({MAX_IMAGE_WIDTH}x{MAX_IMAGE_HEIGHT})"
            )
    except (OSError, ValueError) as e:
        logger.warning(f"Failed to validate image dimensions: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image file"
        ) from e


def _sanitize_filename(original_filename: str, detected_format: str) -> str:
    """
    Generate secure filename using UUID, ignoring original name.
    
    Args:
        original_filename: Original uploaded filename (for logging only)
        detected_format: Validated format (jpg/png/gif/webp)
    
    Returns:
        Safe filename with UUID and validated extension
    """
    # Use only UUID, ignore original filename (prevents traversal and enumeration)
    safe_filename = f"{uuid4()}.{detected_format}"
    logger.debug(f"Generated safe filename for {original_filename}: {safe_filename}")
    return safe_filename

# ============================================================================
# ENDPOINTS
# ============================================================================

@router.post(
    "/upload",
    response_model=ImageUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload an image",
    description="Upload an image file (JPG, PNG, GIF, WebP). Max 5MB."
)
async def upload_image(
    file: UploadFile = File(..., description="Image file to upload")
) -> ImageUploadResponse:
    """
    Upload an image with comprehensive security validation.
    
    Security features:
    - File type validated by magic bytes (not extension)
    - MIME type checked
    - Image dimensions validated
    - Filename sanitized to prevent path traversal
    - Disk space validated
    - All errors logged for audit trail
    
    Args:
        file: Image file from multipart form data
    
    Returns:
        ImageUploadResponse with URL, filename, and size
    
    Raises:
        HTTPException: 400 if validation fails, 507 if no disk space, 500 on server error
    """
    
    if not file.filename:
        logger.warning("Upload attempted with no filename")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required"
        )
    
    original_filename = file.filename
    
    try:
        # ====================================================================
        # VALIDATION PHASE
        # ====================================================================
        
        # 1. Validate disk space BEFORE processing
        _validate_disk_space()
        
        # 2. Check file size
        if file.size and file.size > MAX_FILE_SIZE_BYTES:
            logger.warning(
                f"File size exceeded",
                extra={
                    "filename": original_filename,
                    "size": file.size,
                    "max_size": MAX_FILE_SIZE_BYTES,
                }
            )
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File exceeds maximum size of {MAX_FILE_SIZE_BYTES // (1024*1024)}MB"
            )
        
        # 3. Read file content for validation
        file_content = await file.read()
        file_size = len(file_content)
        
        if file_size == 0:
            logger.warning(f"Empty file upload: {original_filename}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File is empty"
            )
        
        # 4. Validate file signature (magic bytes) - detects actual format
        detected_format = _verify_file_signature(file_content)
        if not detected_format:
            logger.warning(
                f"Invalid file signature",
                extra={"filename": original_filename, "claimed_ext": Path(original_filename).suffix}
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid image format. File signature does not match JPG, PNG, GIF, or WebP."
            )
        
        # 5. Validate MIME type
        if file.content_type and file.content_type not in ALLOWED_MIMETYPES:
            logger.warning(
                f"Invalid MIME type",
                extra={"filename": original_filename, "mime_type": file.content_type}
            )
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Invalid MIME type: {file.content_type}"
            )
        
        # 6. Validate image dimensions
        await _validate_image_dimensions(file_content)
        
        # ====================================================================
        # STORAGE PHASE
        # ====================================================================
        
        # Generate secure filename
        safe_filename = _sanitize_filename(original_filename, detected_format)
        file_location = UPLOAD_DIR / safe_filename
        
        # Atomic write: write to temp first, then rename
        temp_location = UPLOAD_DIR / f".{safe_filename}.tmp"
        
        try:
            # Write to temporary file
            async with aiofiles.open(temp_location, "wb") as f:
                await f.write(file_content)
            
            # Atomic rename to final location
            temp_location.rename(file_location)
            
            logger.info(
                f"Image uploaded successfully",
                extra={
                    "original_filename": original_filename,
                    "safe_filename": safe_filename,
                    "size_bytes": file_size,
                    "path": str(file_location),
                }
            )
            
        except OSError as e:
            # Clean up temp file if it exists
            if temp_location.exists():
                temp_location.unlink()
            
            logger.error(
                f"Failed to write image file",
                extra={"filename": safe_filename, "error": str(e)},
                exc_info=True
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save image. Please try again."
            ) from e
        
        # ====================================================================
        # RESPONSE
        # ====================================================================
        
        public_url = f"/static/uploads/{safe_filename}"
        
        return ImageUploadResponse(
            url=public_url,
            filename=safe_filename,
            size_bytes=file_size
        )
    
    except HTTPException:
        # Re-raise HTTP exceptions (already have proper responses)
        raise
    
    except Exception as e:
        # Catch unexpected errors - log but don't expose details
        logger.error(
            f"Unexpected error during image upload",
            extra={"filename": original_filename},
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred. Please try again."
        ) from e

# ============================================================================
# INITIALIZATION
# ============================================================================

def initialize_image_upload() -> None:
    """
    Initialize image upload module.
    Call this during application startup.
    """
    _ensure_upload_directory()
    logger.info("Image upload module initialized")