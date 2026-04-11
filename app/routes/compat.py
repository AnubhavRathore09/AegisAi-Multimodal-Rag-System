from __future__ import annotations

from fastapi import APIRouter, File, Form, UploadFile

from app.config import settings
from app.schemas import BatchEvaluationRequest
from app.services.evaluator import EvaluationSample, rag_evaluator
from app.services.logging_service import app_logger
from app.services.memory import memory_store
from app.services.speech import speech_service
from app.services.vector_store import vector_store

router = APIRouter(tags=["compat"])
ADMIN_TOKEN = "anubhav_admin_secure"


@router.get("/api/history")
async def list_history():
    return memory_store.list_sessions()


@router.get("/api/history/{session_id}")
async def get_history(session_id: str):
    return {"messages": memory_store.load_session_messages(session_id)}


@router.delete("/api/history/{session_id}")
async def delete_history(session_id: str):
    memory_store.delete_session(session_id)
    return {"deleted": True}


@router.get("/api/chat/sources")
async def chat_sources():
    seen = set()
    sources = []
    for document in vector_store.documents:
        source = str(document.get("source", "")).strip()
        if not source or source in seen:
            continue
        seen.add(source)
        sources.append({"source": source, "kind": document.get("kind", "document")})
    return {"sources": sources}


@router.get("/analytics")
async def analytics():
    sessions = memory_store.list_sessions()
    messages = sum(len(memory_store.load_session_messages(session["id"])) for session in sessions)
    return {
        "users": len(sessions),
        "chats": messages,
        "streams": app_logger.counters.get("stream", 0),
        "uploads": len({str(doc.get('source', '')) for doc in vector_store.documents if doc.get('source')}),
        "voice": app_logger.counters.get("voice", 0),
        "hybrid_search": True,
        "model_switch": True,
        "logging": True,
        "evaluation_batch": True,
        "deployment_ready": True,
    }


@router.post("/voice/voice-chat")
async def voice_chat(audio: UploadFile = File(...), language: str | None = Form(default=None)):
    content = await audio.read()
    text = await speech_service.transcribe_async(audio.filename or "voice.webm", content, language=language)
    app_logger.log("voice", filename=audio.filename or "voice.webm", language=language or "auto")
    return {"text": text}


@router.post("/api/evaluate_batch")
async def evaluate_batch(payload: BatchEvaluationRequest):
    samples = [
        EvaluationSample(
            query=item.query,
            retrieved_docs=item.retrieved_docs,
            answer=item.answer,
            reference_answer=item.expected,
            reference_docs=item.reference_docs,
        )
        for item in payload.samples
    ]
    result = await rag_evaluator.evaluate_batch(samples)
    app_logger.log("evaluation_batch", samples=len(samples), summary=result.get("summary", {}), results=result.get("results", []))
    summary = result.get("summary", {})
    return {
        "accuracy": summary.get("accuracy", 0.0),
        "avg_score": summary.get("avg_score", 0.0),
        "details": result.get("results", []),
        "summary": summary,
    }


@router.get("/api/features")
async def features():
    return {
        "models": settings.available_models,
        "role_modes": settings.role_modes,
        "prompt_templates": settings.prompt_templates,
        "features": {
            "multi_doc_intelligence": True,
            "citation_system": True,
            "query_rewriting": True,
            "feedback_system": True,
            "streaming_response": True,
            "role_modes": True,
            "prompt_templates": True,
            "summarization": True,
            "dark_mode": True,
            "export_chat": True,
            "suggestions": True,
            "model_switch": True,
            "token_usage": True,
            "background_processing": True,
            "hallucination_control": True,
            "retrieval_optimization": True,
            "context_limit": True,
            "security": True,
            "logging_system": True,
            "session_memory": True,
            "edge_handling": True,
            "performance": True,
            "ux_polish": True,
            "hybrid_search": True,
            "llm_router": True,
            "evaluation_batch": True,
            "deployment_ready": True,
            "real_documents": True,
            "explainability": True,
        },
    }


@router.get("/api/logs/recent")
async def recent_logs(limit: int = 30):
    return {"logs": app_logger.recent(limit=min(max(limit, 1), 100))}
