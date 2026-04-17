from fastapi import APIRouter, UploadFile, File, Form
import shutil
import os
from pymongo import MongoClient
from datetime import datetime

from src.voice.speech_to_text import transcribe_audio
from src.voice.text_to_speech import generate_speech
from src.llms.groq_client import get_llm_response

client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017/"))
db = client["aegis_ai"]

def track_event(event_type, user="guest"):
    db.analytics.insert_one({
        "event": event_type,
        "user": user,
        "timestamp": datetime.utcnow()
    })

router = APIRouter()

@router.post("/voice-chat")
async def voice_chat(
    file: UploadFile | None = File(default=None),
    audio: UploadFile | None = File(default=None),
    language: str | None = Form(default=None),
):
    try:
        track_event("voice_used", "guest")

        incoming = audio or file
        if incoming is None:
            return {"error": "No audio file provided"}

        temp_path = f"temp_{incoming.filename}"
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(incoming.file, buffer)

        user_text = transcribe_audio(temp_path)
        os.remove(temp_path)

        return {
            "text": user_text,
            "language": language or "auto",
        }

    except Exception as e:
        return {"error": str(e)}
