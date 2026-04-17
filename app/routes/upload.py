from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile

from app.schemas import UploadResponse
from app.services.auth import get_optional_user_id
from app.services.documents import ingest_upload


router = APIRouter(prefix="/api", tags=["upload"])


@router.post("/upload", response_model=UploadResponse)
async def upload(
    file: UploadFile = File(...),
    user_id: str | None = Depends(get_optional_user_id),
) -> UploadResponse:
    return await ingest_upload(file, user_id=user_id)
