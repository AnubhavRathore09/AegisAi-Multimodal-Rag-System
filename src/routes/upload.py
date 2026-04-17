from fastapi import APIRouter, UploadFile, File, HTTPException
from src.rag.document_processor import process_document
from src.core.logger import get_logger
from pymongo import MongoClient
from datetime import datetime
import os

client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017/"))
db = client["aegis_ai"]

def track_event(event_type, user="guest"):
    db.analytics.insert_one({
        "event": event_type,
        "user": user,
        "timestamp": datetime.utcnow()
    })

router = APIRouter()
logger = get_logger(__name__)

@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    try:
        track_event("file_upload", "guest")

        content = await file.read()
        text = content.decode("utf-8", errors="ignore")

        chunks = process_document(text, file.filename)

        return {
            "status": "success",
            "filename": file.filename,
            "chunks": chunks,
            "type": "document"
        }

    except HTTPException as e:
        raise e

    except Exception as e:
        logger.error(f"Upload failed: {str(e)}")
        return {
            "status": "error",
            "filename": file.filename,
            "chunks": 0
        }
