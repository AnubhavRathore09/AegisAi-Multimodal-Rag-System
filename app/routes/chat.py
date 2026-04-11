from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.config import settings
from app.schemas import ChatRequest, ChatResponse
from app.services.rag import run_chat, stream_chat

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    return await run_chat(request)


@router.post("/stream")
async def stream(request: ChatRequest) -> StreamingResponse:
    return StreamingResponse(
        stream_chat(request),
        media_type=settings.stream_media_type,
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

