from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi.middleware import SlowAPIMiddleware
from dotenv import load_dotenv
from datetime import datetime
from typing import Optional
from PIL import Image
import pytesseract
import io
import os
from pymongo import MongoClient

from src.core.settings import settings
from src.core.logger import get_logger
from src.rag.rag_pipeline import run_rag
from src.rag.retriever import load_faiss_index, sync_from_mongo

logger = get_logger(__name__)

load_dotenv()

client = MongoClient(settings.MONGO_URL)
db = client["aegis_ai"]

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "anubhav_admin_secure")

def track_event(event_type, user="guest"):
    try:
        db.analytics.insert_one({
            "event": event_type,
            "user": user,
            "timestamp": datetime.utcnow()
        })
    except:
        pass

try:
    from src.core.rate_limiter import limiter
except:
    limiter = None

try:
    from src.api.stream import router as stream_router
    stream_available = True
except:
    stream_available = False

try:
    from src.routes.voice import router as voice_router
    voice_available = True
except:
    voice_available = False

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        load_faiss_index()
        sync_from_mongo()
    except:
        pass
    yield

app = FastAPI(lifespan=lifespan)

app.add_middleware(GZipMiddleware, minimum_size=1000)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if limiter:
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.post("/api/chat")
async def chat(
    message: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    request: Request = None
):
    try:
        image_text = ""

        if file:
            try:
                contents = await file.read()
                image = Image.open(io.BytesIO(contents)).convert("RGB")
                image_text = pytesseract.image_to_string(image) or ""
                track_event("file_upload")
            except:
                image_text = ""

        final_query = ""

        if message:
            final_query += message

        if image_text.strip():
            final_query += f"\nExtracted from image:\n{image_text}"

        if not final_query.strip():
            final_query = "Hello"

        try:
            session_id = request.client.host if request else "default_session"
            response = run_rag(final_query, session_id)

            if isinstance(response, dict):
                response = response.get("answer", str(response))
            else:
                response = str(response)

        except:
            response = "Error generating response"

        track_event("chat")

        return {
            "response": response
        }

    except Exception as e:
        return {
            "response": "Something went wrong",
            "error": str(e)
        }

if stream_available:
    app.include_router(stream_router, prefix="/api")

if voice_available:
    app.include_router(voice_router, prefix="/voice")

@app.middleware("http")
async def analytics_middleware(request: Request, call_next):
    path = request.url.path
    auth = request.headers.get("Authorization", "")
    user = "guest" if not auth else auth

    if "/api/chat" in path:
        track_event("chat", user)
    elif "/api/stream" in path:
        track_event("stream", user)

    response = await call_next(request)
    return response

@app.get("/")
def root():
    return {"status": "ok"}

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "stream": stream_available,
        "voice": voice_available
    }

@app.get("/analytics")
def analytics(request: Request):
    auth = request.headers.get("Authorization")

    if auth != f"Bearer {ADMIN_TOKEN}":
        raise HTTPException(status_code=403)

    return {
        "users": len(db.analytics.distinct("user")),
        "chat": db.analytics.count_documents({"event": "chat"}),
        "stream": db.analytics.count_documents({"event": "stream"}),
        "upload": db.analytics.count_documents({"event": "file_upload"}),
    }
