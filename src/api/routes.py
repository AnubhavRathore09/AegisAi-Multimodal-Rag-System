"""POST /api/chat — full RAG pipeline."""
from fastapi import APIRouter, HTTPException
from src.models import ChatRequest, ChatResponse
from src.services.rag_pipeline import run_rag
from src.memory.chat_memory import save_message
from src.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    logger.info("Chat | id=%s | q=%s", req.chat_id, req.query[:80])

    try:
        result = run_rag(
            query=req.query,
            chat_id=req.chat_id,
            images=[img.dict() for img in req.images] if req.images else None,
            user=req.user,
        )
    except Exception as exc:
        logger.error("Pipeline error: %s", exc)
        raise HTTPException(status_code=500, detail=f"Pipeline error: {exc}")

    answer = result.get("response", "")
    if not answer:
        raise HTTPException(status_code=500, detail="No response generated.")

    # Save memory
    save_message(req.chat_id, "user", req.query)
    save_message(req.chat_id, "assistant", answer)

    logger.info(
        "Response | id=%s | route=%s | len=%d",
        req.chat_id,
        result.get("route"),
        len(answer),
    )

    return ChatResponse(
        response=answer,
        chat_id=req.chat_id,
        sources=result.get("sources", []),
        route=result.get("route"),
    )


@router.get("/chat/sources")
def get_sources():
    from src.rag.retriever import get_all_sources
    return {"sources": get_all_sources()}
