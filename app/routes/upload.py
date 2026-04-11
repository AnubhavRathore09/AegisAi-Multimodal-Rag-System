from __future__ import annotations

from fastapi import APIRouter, File, UploadFile

from app.schemas import UploadResponse
from app.services.documents import ingest_upload


router = APIRouter(prefix="/api", tags=["upload"])


@router.post("/upload", response_model=UploadResponse)
async def upload(file: UploadFile = File(...)) -> UploadResponse:
    return await ingest_upload(file)
