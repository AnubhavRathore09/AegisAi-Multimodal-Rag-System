from fastapi import APIRouter, UploadFile, File
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
async def voice_chat(file: UploadFile = File(...)):
    try:
        track_event("voice_used", "guest")

        temp_path = f"temp_{file.filename}"
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        user_text = transcribe_audio(temp_path)
        ai_response = get_llm_response(user_text)
        audio_path = generate_speech(ai_response)

        os.remove(temp_path)

        return {
            "user_text": user_text,
            "ai_text": ai_response,
            "audio_url": audio_path
        }

    except Exception as e:
        return {"error": str(e)}
