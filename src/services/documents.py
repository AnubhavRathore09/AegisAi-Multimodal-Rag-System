from __future__ import annotations

import asyncio
import hashlib
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile
from pypdf import PdfReader

from src.config import UPLOAD_DIR, settings
from src.schemas import UploadResponse
from src.services.logging_service import app_logger
from src.services.ocr import extract_text_from_image_bytes_async
from src.services.vector_store import vector_store


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


def _read_document_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return read_pdf(path)
    return path.read_text(encoding="utf-8", errors="ignore")


def load_uploaded_document_text(upload_id: str | None, fallback_text: str = "") -> str:
    """
    Resolve the full original text for an uploaded document.

    The chat payload only carries a lightweight preview, so we recover the
    full file text from the indexed upload metadata when possible.
    """
    cleaned_upload_id = str(upload_id or "").strip()
    if cleaned_upload_id:
        matching_docs = [
            doc for doc in vector_store.documents
            if str(doc.get("upload_id", "")).strip() == cleaned_upload_id
            and str(doc.get("kind", "")).strip() == "document"
        ]
        if matching_docs:
            source_path = str(matching_docs[0].get("path", "") or "").strip()
            if source_path:
                candidate_path = Path(source_path)
                if candidate_path.exists() and candidate_path.is_file():
                    try:
                        text = _read_document_file(candidate_path)
                        normalized = " ".join(text.split()).strip()
                        if normalized:
                            return normalized
                    except Exception:
                        pass

            chunks: list[str] = []
            seen: set[str] = set()
            for doc in matching_docs:
                chunk = " ".join(str(doc.get("text", "")).split()).strip()
                if not chunk or chunk in seen:
                    continue
                seen.add(chunk)
                chunks.append(chunk)
            if chunks:
                return " ".join(chunks).strip()

    return " ".join(str(fallback_text or "").split()).strip()


def save_upload(content: bytes, suffix: str) -> Path:
    digest = hashlib.sha256(content).hexdigest()[:16]
    path = UPLOAD_DIR / f"{digest}{suffix}"
    path.write_bytes(content)
    return path


async def ingest_upload(file: UploadFile, user_id: str | None = None) -> UploadResponse:
    suffix = Path(file.filename or "upload.bin").suffix.lower()
    if suffix not in ALLOWED_DOCUMENT_TYPES and suffix not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported file type. Use PDF, TXT, MD, CSV, PNG, JPG, JPEG, or WEBP.")

    content_type = str(file.content_type or "").lower()
    if suffix in ALLOWED_IMAGE_TYPES and content_type and not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Image upload content type is invalid")
    if suffix in ALLOWED_DOCUMENT_TYPES and content_type and not (
        content_type.startswith("text/") or "pdf" in content_type or content_type == "application/octet-stream"
    ):
        raise HTTPException(status_code=400, detail="Document upload content type is invalid")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty upload")

    saved_path = await asyncio.to_thread(save_upload, content, suffix)
    upload_id = str(uuid.uuid4())

    if suffix in ALLOWED_IMAGE_TYPES:
        print("OCR_START", file.filename or saved_path.name, flush=True)
        print("OCR_IMAGE_RECEIVED", len(content), flush=True)
        app_logger.log("OCR_IMAGE_RECEIVED", filename=file.filename or saved_path.name, bytes=len(content), user_id=user_id or "guest")
        extracted_text = await extract_text_from_image_bytes_async(content)
        if not extracted_text:
            print("OCR_FAILED", file.filename or saved_path.name, flush=True)
            app_logger.log("OCR_FAILED", filename=file.filename or saved_path.name, user_id=user_id or "guest")
            extracted_text = "Unable to extract text from image."
            chunks = []
        else:
            print("OCR_TEXT_EXTRACTED", len(extracted_text), flush=True)
            print("OCR_TEXT_LENGTH", len(extracted_text), flush=True)
            print("OCR_SUCCESS", file.filename or saved_path.name, flush=True)
            app_logger.log("OCR_SUCCESS", filename=file.filename or saved_path.name, chars=len(extracted_text), user_id=user_id or "guest")
            chunks = chunk_text(extracted_text, settings.chunk_size, settings.chunk_overlap)
        indexed = await asyncio.to_thread(
            vector_store.add_documents,
            [
                {
                    "text": chunk,
                    "source": file.filename or saved_path.name,
                    "kind": "image",
                    "upload_id": upload_id,
                    "user_id": user_id,
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
            message="Image uploaded and OCR text indexed." if indexed else "Unable to extract text from image.",
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
                    "user_id": user_id,
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
