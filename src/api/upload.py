"""POST /api/upload — document and image ingestion."""

from fastapi import APIRouter, UploadFile, File
from src.models.upload import UploadResponse
from src.rag.document_upload import process_upload
from src.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.post("/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...)) -> UploadResponse:
    try:
        logger.info(f"Upload | file={file.filename}, type={file.content_type}")

        result = await process_upload(file)

        return UploadResponse(**result)

    except Exception as e:
        logger.error(f"Upload API error: {e}")
        raise
