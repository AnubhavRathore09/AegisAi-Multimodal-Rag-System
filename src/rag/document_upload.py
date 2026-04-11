import os
import uuid
import tempfile
import base64
import hashlib
import numpy as np

try:
    import faiss  # type: ignore
except Exception:
    faiss = None

from fastapi import UploadFile, HTTPException
from langchain_text_splitters import RecursiveCharacterTextSplitter
from PyPDF2 import PdfReader

from src.db.mongo import get_docs_collection
from src.services.embedding import get_embedding
from src.llms.groq_client import analyze_image
from src.core.config import settings
from src.core.logger import get_logger

logger = get_logger(__name__)

DIMENSION = 384
faiss_index = faiss.IndexFlatL2(DIMENSION) if faiss is not None else None

doc_store = []

def get_file_hash(content: bytes):
    return hashlib.md5(content).hexdigest()

def extract_pdf(path):
    reader = PdfReader(path)
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""
    return text

def extract_txt(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def chunk_text(text):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
    )
    return splitter.split_text(text)

def image_to_text(image_bytes, ext):
    try:
        import pytesseract
        from PIL import Image
        import io
        import easyocr

        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

        ocr_text = pytesseract.image_to_string(image)

        reader = easyocr.Reader(['en'], gpu=False)
        easyocr_result = reader.readtext(np.array(image))
        easy_text = " ".join([res[1] for res in easyocr_result])

        combined_text = f"{ocr_text}\n{easy_text}".strip()

        b64 = base64.b64encode(image_bytes).decode("utf-8")
        mime = f"image/{ext.replace('.', '')}"

        llm_text = analyze_image(
            b64,
            mime,
            "Describe this image in detail. Extract all text. Identify objects, charts, and meaning."
        )

        final_text = f" OCR TEXT:\n{combined_text}\n\nAI UNDERSTANDING:\n{llm_text}".strip()

        return final_text

    except Exception as e:
        logger.error(f"Image processing error: {str(e)}")
        return ""

def store_chunks(chunks, filename, file_hash):
    col = get_docs_collection()
    col.delete_many({"file_hash": file_hash})

    vectors = []
    records = []

    for chunk in chunks:
        emb = get_embedding(chunk)
        vectors.append(emb)

        record = {
            "id": str(uuid.uuid4()),
            "text": chunk,
            "embedding": emb,
            "source": filename,
            "file_hash": file_hash
        }

        records.append(record)
        doc_store.append(record)

    if vectors and faiss_index is not None:
        vectors = np.array(vectors).astype("float32")
        faiss_index.add(vectors)

    if records:
        col.insert_many(records)

    logger.info(f"Stored {len(records)} chunks from {filename}")

    return len(records)

async def process_upload(file: UploadFile) -> dict:
    ext = os.path.splitext(file.filename)[1].lower()

    ALLOWED_DOCS = {".pdf", ".txt"}
    ALLOWED_IMAGES = {".png", ".jpg", ".jpeg", ".webp"}

    if ext not in ALLOWED_DOCS and ext not in ALLOWED_IMAGES:
        raise HTTPException(400, f"Unsupported file type {ext}")

    content = await file.read()
    file_hash = get_file_hash(content)

    col = get_docs_collection()
    existing = col.find_one({"file_hash": file_hash})

    if existing:
        return {
            "status": "duplicate",
            "message": "File already uploaded",
            "filename": file.filename
        }

    tmp_path = None

    try:
        if ext in ALLOWED_IMAGES:
            text = image_to_text(content, ext)

            if not text:
                raise HTTPException(400, "Failed to process image")

            chunks = chunk_text(text)

        else:
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                tmp.write(content)
                tmp_path = tmp.name

            if ext == ".pdf":
                text = extract_pdf(tmp_path)
            else:
                text = extract_txt(tmp_path)

            if not text.strip():
                raise HTTPException(400, "No text found in file")

            chunks = chunk_text(text)

        count = store_chunks(chunks, file.filename, file_hash)

        return {
            "status": "success",
            "chunks": count,
            "filename": file.filename,
            "type": "image" if ext in ALLOWED_IMAGES else "document"
        }

    except Exception as e:
        logger.error(f"Upload failed: {file.filename} | {str(e)}")
        raise HTTPException(500, str(e))

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
