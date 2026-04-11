from fastapi import APIRouter
from pymongo import MongoClient
import os

router = APIRouter()

client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017/"))
db = client["aegis_ai"]

@router.get("/analytics")
def get_analytics():
    total_users = len(db.analytics.distinct("user"))
    total_chats = db.analytics.count_documents({"event": "chat"})
    total_stream = db.analytics.count_documents({"event": "stream"})
    total_uploads = db.analytics.count_documents({"event": "file_upload"})
    total_voice = db.analytics.count_documents({"event": "voice_used"})

    return {
        "users": total_users,
        "chats": total_chats,
        "stream": total_stream,
        "uploads": total_uploads,
        "voice": total_voice
    }
