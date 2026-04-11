from __future__ import annotations

import asyncio
import hashlib
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile
from pypdf import PdfReader

from app.config import UPLOAD_DIR, settings
from app.schemas import UploadResponse
from app.services.logging_service import app_logger
from app.services.ocr import extract_text_from_image_bytes_async
from app.services.vector_store import vector_store


ALLOWED_DOCUMENT_TYPES = {
    ".pdf",
    ".txt",
    ".md",
    ".csv",
}
ALLOWED_IMAGE_TYPES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
}


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    normalized = " ".join(text.split())
    if not normalized:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(len(normalized), start + chunk_size)
        chunks.append(normalized[start:end])
        if end == len(normalized):
            break
        start = max(end - overlap, start + 1)
    return chunks


def read_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages).strip()


def save_upload(content: bytes, suffix: str) -> Path:
    digest = hashlib.sha256(content).hexdigest()[:16]
    path = UPLOAD_DIR / f"{digest}{suffix}"
    path.write_bytes(content)
    return path


async def ingest_upload(file: UploadFile) -> UploadResponse:
    suffix = Path(file.filename or "upload.bin").suffix.lower()
    if suffix not in ALLOWED_DOCUMENT_TYPES and suffix not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty upload")

    saved_path = await asyncio.to_thread(save_upload, content, suffix)
    upload_id = str(uuid.uuid4())

    if suffix in ALLOWED_IMAGE_TYPES:
        extracted_text = await extract_text_from_image_bytes_async(content)
        if not extracted_text:
            extracted_text = "Image uploaded successfully, but OCR is unavailable or no readable text was detected."

        chunks = chunk_text(extracted_text, settings.chunk_size, settings.chunk_overlap)
        indexed = await asyncio.to_thread(
            vector_store.add_documents,
            [
                {
                    "text": chunk,
                    "source": file.filename or saved_path.name,
                    "kind": "image",
                    "upload_id": upload_id,
                    "path": str(saved_path),
                }
                for chunk in chunks
            ],
        )
        response = UploadResponse(
            upload_id=upload_id,
            kind="image",
            filename=file.filename or saved_path.name,
            extracted_text=extracted_text,
            chunks_indexed=indexed,
            chunks=indexed,
            message="Image uploaded and OCR text indexed.",
            processing={"status": "completed", "background": False},
        )
        app_logger.log(
            "upload",
            upload_id=upload_id,
            filename=file.filename or saved_path.name,
            kind=response.kind,
            chunks_indexed=indexed,
        )
        return response

    text = await asyncio.to_thread(read_pdf, saved_path) if suffix == ".pdf" else await asyncio.to_thread(
        saved_path.read_text,
        encoding="utf-8",
        errors="ignore",
    )
    text = " ".join(text.split()).strip()
    if not text:
        raise HTTPException(status_code=400, detail="No readable text found in the document")

    chunks = chunk_text(text, settings.chunk_size, settings.chunk_overlap)
    indexed = await asyncio.to_thread(
        vector_store.add_documents,
        [
            {
                "text": chunk,
                "source": file.filename or saved_path.name,
                "kind": "document",
                "upload_id": upload_id,
                "path": str(saved_path),
            }
            for chunk in chunks
        ],
    )
    response = UploadResponse(
        upload_id=upload_id,
        kind="document",
        filename=file.filename or saved_path.name,
        extracted_text=text[:600],
        chunks_indexed=indexed,
        chunks=indexed,
        message="Document uploaded and indexed for retrieval.",
        processing={"status": "completed", "background": False},
    )
    app_logger.log(
        "upload",
        upload_id=upload_id,
        filename=file.filename or saved_path.name,
        kind=response.kind,
        chunks_indexed=indexed,
    )
    return response
