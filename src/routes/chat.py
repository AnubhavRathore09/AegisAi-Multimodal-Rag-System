from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from src.config import settings
from src.schemas import ChatRequest, ChatResponse
from src.services.auth import get_optional_user_id
from src.services.rag import run_chat, stream_chat

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, user_id: str | None = Depends(get_optional_user_id)) -> ChatResponse:
    return await run_chat(request, user_id=user_id)


@router.post("/stream")
async def stream(request: ChatRequest, user_id: str | None = Depends(get_optional_user_id)) -> StreamingResponse:
    return StreamingResponse(
        stream_chat(request, user_id=user_id),
        media_type=settings.stream_media_type,
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
