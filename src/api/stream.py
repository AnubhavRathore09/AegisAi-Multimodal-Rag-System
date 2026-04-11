import json
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from pymongo import MongoClient
from datetime import datetime
import os

from src.llms.groq_client import get_streaming_response
from src.rag.retriever import retrieve_documents, build_context_with_citations
from src.memory.chat_memory import get_history_as_messages, save_message
from src.core.logger import get_logger
from src.utils.security import sanitize_input
from src.core.auth import get_optional_user

client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017/"))
db = client["aegis_ai"]

def track_event(event_type, user="guest"):
    db.analytics.insert_one({
        "event": event_type,
        "user": user,
        "timestamp": datetime.utcnow()
    })

logger = get_logger(__name__)
router = APIRouter()

class StreamRequest(BaseModel):
    query: str
    chat_id: str = "default"
    user: str = "user"

@router.post("/stream")
async def stream_chat(req: StreamRequest, request: Request, user=Depends(get_optional_user)):
    user_id = user if user else "guest"

    async def generate():
        try:
            track_event("stream", user_id)

            clean_query = sanitize_input(req.query)

            history = get_history_as_messages(req.chat_id)
            docs = retrieve_documents(clean_query)
            context, sources = build_context_with_citations(docs)

            if context:
                prompt = f"Context:\n{context}\n\nQuestion: {clean_query}"
            else:
                prompt = clean_query

            full_response = ""

            for token in get_streaming_response(prompt, history):
                full_response += token
                yield f"data: {json.dumps({'token': token})}\n\n"

            save_message(req.chat_id, "user", clean_query)
            save_message(req.chat_id, "assistant", full_response)

            yield f"data: {json.dumps({'done': True, 'sources': sources})}\n\n"

        except Exception as exc:
            logger.error(f"Stream error: {exc}")
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        },
    )
