from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import asyncio
import json

from src.rag.rag_pipeline import run_rag
from src.llms.groq_client import analyze_image
from src.utils.security import sanitize_input
from src.core.auth import get_optional_user

router = APIRouter()

class ChatRequest(BaseModel):
    query: str
    chat_id: str = "default"
    use_docs: bool = True
    images: list | None = None

@router.post("/chat")
async def chat(request: Request, user=Depends(get_optional_user)):
    try:
        body = await request.json()

        query = sanitize_input(body.get("query", ""))
        chat_id = body.get("chat_id", "default")
        use_docs = body.get("use_docs", True)
        images = body.get("images", [])

        if images:
            image = images[0]
            result = analyze_image(
                image["data"],
                image["type"],
                query
            )
            return {
                "response": result,
                "chat_id": chat_id,
                "sources": [],
                "route": "vision"
            }

        result = run_rag(query, chat_id, use_docs=use_docs)

        return {
            "response": result.get("response", ""),
            "chat_id": chat_id,
            "sources": result.get("sources", []),
            "route": result.get("route", "rag"),
            "user": user
        }

    except Exception as e:
        return {
            "response": f"Error: {str(e)}",
            "chat_id": "default",
            "sources": [],
            "route": "error"
        }

@router.post("/chat/stream")
async def stream_chat(request: Request, user=Depends(get_optional_user)):
    async def generator():
        try:
            body = await request.json()

            query = sanitize_input(body.get("query", ""))
            chat_id = body.get("chat_id", "default")
            use_docs = body.get("use_docs", True)
            images = body.get("images", [])

            if images:
                image = images[0]
                result = analyze_image(
                    image["data"],
                    image["type"],
                    query
                )
                for word in result.split():
                    yield f"data: {json.dumps({'token': word})}\n\n"
                    await asyncio.sleep(0.01)
                yield f"data: {json.dumps({'done': True, 'sources': []})}\n\n"
                return

            result = run_rag(query, chat_id, use_docs=use_docs)

            answer = result.get("response", "")
            sources = result.get("sources", [])

            for word in answer.split():
                yield f"data: {json.dumps({'token': word})}\n\n"
                await asyncio.sleep(0.01)

            yield f"data: {json.dumps({'done': True, 'sources': sources})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        },
    )
