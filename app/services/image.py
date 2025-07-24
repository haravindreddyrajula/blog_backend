import logging
from pathlib import Path
import uuid
import aiofiles
from fastapi import APIRouter, File, HTTPException, UploadFile, status

router = APIRouter(prefix="/images", tags=["Images"])

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

logger = logging.getLogger(__name__)

@router.post("/upload", response_model=str)
async def upload_image(file: UploadFile = File(...)):
    try:
        # Validate file type
        allowed_extensions = {"jpg", "jpeg", "png", "webp"}
        file_ext = file.filename.split(".")[-1].lower()
        if file_ext not in allowed_extensions:
            logger.error(f"Image file extension: {file_ext}, not supported")
            raise HTTPException( status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file type. Only JPG, PNG, and WEBP are allowed.")
        
        if file.size > MAX_FILE_SIZE:
            logger.error(f"Image: {file.filename}, has exceeded allowed file size of 5MB")
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File too large")

        # Generate secure filename
        filename = f"{uuid.uuid4()}.{file_ext}"
        upload_dir = Path("static/uploads")
        upload_dir.mkdir(parents=True, exist_ok=True)
        file_location = upload_dir / filename

        # Async file save
        async with aiofiles.open(file_location, "wb") as f:
            while chunk := await file.read(1024 * 1024):  # 1MB chunks
                await f.write(chunk)
        
        logger.info(f"{filename} - image saved at {file_location}")

        return f"/static/uploads/{filename}"

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unable to save the Image: {file.filename}")
        raise HTTPException( status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to upload image: {str(e)}")
    