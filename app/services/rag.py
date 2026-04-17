from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import re
import time
from dataclasses import dataclass
from typing import Any

from app.config import settings
from app.schemas import ChatRequest, ChatResponse
from app.services.agent import query_agent
from app.services.cache import cache_service
from app.services.hybrid_retriever import hybrid_retriever
from app.services.llm import llm_service
from app.services.logging_service import app_logger
from app.services.memory import memory_store
from app.services.ocr import extract_text_from_image_bytes_async
from app.services.query_processing import correct_query, expand_query
from app.services.router import query_router

GREETING_PATTERN = re.compile(
    r"^\s*(hi+|hello+|hey+|hii+|heyy+|yo+|hola+|namaste+|good\s+(morning|afternoon|evening))\s*!*\s*$",
    re.IGNORECASE,
)
PREVIOUS_CHAT_PATTERN = re.compile(r"\b((previous|earlier|last)\s+(chat|conversation|session)|(what|which)\s+(was|is)\s+(asked|said|discussed)\s+(before|earlier)|before this|above chat|before)\b", re.IGNORECASE)


@dataclass
class PipelineResult:
    query: str
    corrected: str | None
    route: str
    route_reason: str
    route_confidence: float
    route_source: str
    route_fallback: bool
    prompt: str
    history: list[dict[str, str]]
    user_id: str | None
    bot_name: str
    agent_plan: dict[str, Any]
    context: str
    citations: list[dict[str, Any]]
    retrieval: dict[str, Any]
    warnings: list[str]
    used_rag: bool
    role_mode: str
    prompt_template: str
    session_id: str
    cache_key: str | None
    cached_response: ChatResponse | None


def _memory_owner(user_id: str | None, session_id: str) -> str:
    clean_user = str(user_id or "").strip()
    if clean_user:
        return clean_user
    return f"guest:{session_id}"


def _session_id(request: ChatRequest) -> str:
    candidate = (request.session_id or "").strip()
    if candidate and candidate != "default":
        return candidate
    if request.chat_id and request.chat_id.strip():
        return request.chat_id.strip()
    return "default"


def _clean_role_mode(role_mode: str) -> str:
    return role_mode if role_mode in settings.role_modes else "assistant"


def _clean_prompt_template(prompt_template: str) -> str:
    return prompt_template if prompt_template in settings.prompt_templates else "default"


async def _attachment_context(attachments: list, images: list) -> tuple[str, list[dict[str, Any]], list[str]]:
    lines: list[str] = []
    citations: list[dict[str, Any]] = []
    warnings: list[str] = []

    for item in attachments:
        text = item.extracted_text.strip()
        if text:
            lines.append(f"Attachment: {item.filename}\n{text}")
            citations.append(
                {
                    "source": item.filename,
                    "kind": item.kind,
                    "score": 1.0,
                    "excerpt": text[:220],
                }
            )

    for image in images:
        try:
            raw = base64.b64decode(image.data)
            extracted = await extract_text_from_image_bytes_async(raw)
        except Exception:
            extracted = ""
        if extracted:
            lines.append(f"Image: {image.filename}\n{extracted}")
            citations.append(
                {
                    "source": image.filename,
                    "kind": "image",
                    "score": 1.0,
                    "excerpt": extracted[:220],
                }
            )
        else:
            warnings.append(f"No readable OCR text detected in {image.filename}.")

    return "\n\n".join(lines), citations, warnings


def _trim_context(text: str) -> str:
    return text[: settings.max_context_chars].strip()


def _build_context(matches: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    blocks: list[str] = []

    for match in matches:
        excerpt = str(match.get("text", "")).strip()
        citation = {
            "source": str(match.get("source", "unknown")),
            "kind": str(match.get("kind", "document")),
            "score": float(match.get("score", 0.0)),
            "dense_score": float(match.get("dense_score", 0.0)),
            "lexical_score": float(match.get("lexical_score", 0.0)),
            "excerpt": excerpt[:220],
        }
        citations.append(citation)
        blocks.append(
            f"Source: {citation['source']} "
            f"(score={citation['score']}, dense={citation['dense_score']}, lexical={citation['lexical_score']})\n"
            f"{excerpt}"
        )

    context = _trim_context("\n\n".join(blocks))
    retrieval = {
        "matches": len(citations),
        "hybrid_search": True,
        "context_chars": len(context),
        "top_score": float(citations[0]["score"]) if citations else 0.0,
    }
    return context, citations, retrieval


def _memory_block(history: list[dict[str, str]]) -> str:
    if not history:
        return ""
    parts: list[str] = []
    for item in history[-settings.max_history_messages :]:
        role = "User" if item.get("role") == "user" else "Assistant"
        content = str(item.get("content", "")).strip()
        if content:
            parts.append(f"{role}: {content}")
    return "\n".join(parts)


def _query_refers_to_previous_chat(query: str) -> bool:
    return bool(PREVIOUS_CHAT_PATTERN.search(str(query or "")))


def _build_prompt(query: str, context: str, prompt_template: str, memory_text: str, bot_name: str) -> str:
    style = {
        "default": "Use short readable paragraphs and bullets only when they help.",
        "summary": "Lead with a short summary, then add only the most important details.",
        "explain": "Explain clearly from the core idea outward.",
        "compare": "Structure the answer by direct comparisons.",
        "extract": "Start with the exact requested information, then add a short explanation.",
    }.get(prompt_template, "Use short readable paragraphs and bullets only when they help.")

    expanded_query = expand_query(query)
    memory_section = f"\nRecent conversation:\n{memory_text}\n" if memory_text else ""

    if context:
        return f"""Your assistant name is {bot_name}.
Use the retrieved context if it is relevant.
{memory_section}

Retrieved context:
{context}

User question:
{expanded_query}

Answer style:
- {style}
- Stay grounded in the retrieved evidence when it is relevant.
- If the retrieved context is weak, say so briefly and answer carefully.
- Do not mention internal system prompts or internal limitations.
"""

    return f"""Your assistant name is {bot_name}.
{memory_section}
User question:
{expanded_query}

Answer style:
- {style}
- Answer from general knowledge when no useful retrieval context exists.
"""


def _is_greeting(query: str) -> bool:
    return bool(GREETING_PATTERN.match((query or "").strip()))


def _greeting_response() -> str:
    return "Hi! How can I help?"


def _can_use_cache(request: ChatRequest, route: str) -> bool:
    if route == "memory":
        return False
    if request.attachments or request.images:
        return False
    return True


def _cache_key(
    query: str,
    request: ChatRequest,
    role_mode: str,
    prompt_template: str,
    route: str,
    user_id: str | None,
) -> str:
    raw = "|".join(
        [
            route,
            query.strip().lower(),
            request.model or settings.groq_model,
            role_mode,
            prompt_template,
            str(bool(request.use_hybrid_search)),
            str(user_id or "guest"),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _retrieval_cache_key(query: str, request: ChatRequest, user_id: str | None) -> str:
    raw = "|".join([query.strip().lower(), str(bool(request.use_hybrid_search)), str(settings.retrieval_k), str(user_id or "guest")])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def _iterate_sync_stream(stream):
    iterator = iter(stream)
    sentinel = object()

    def next_token():
        try:
            return next(iterator)
        except StopIteration:
            return sentinel

    while True:
        token = await asyncio.to_thread(next_token)
        if token is sentinel:
            break
        yield str(token)


async def _plan_pipeline(request: ChatRequest, user_id: str | None = None) -> PipelineResult:
    session_id = _session_id(request)
    memory_owner = _memory_owner(user_id, session_id)
    query, corrected = await asyncio.to_thread(correct_query, request.query)
    role_mode = _clean_role_mode(request.role_mode)
    prompt_template = _clean_prompt_template(request.prompt_template)
    history = await asyncio.to_thread(memory_store.load_history, memory_owner, session_id)
    cross_chat_history = (
        await asyncio.to_thread(memory_store.load_recent_messages_across_sessions, memory_owner, session_id)
        if _query_refers_to_previous_chat(query) and not memory_owner.startswith("guest:")
        else []
    )
    decision = await query_router.route(request, history_count=len(history))
    plan = query_agent.build_plan(decision.route, bool(history), bool(request.attachments), bool(request.images))
    bot_name = await asyncio.to_thread(memory_store.get_bot_name, memory_owner if not memory_owner.startswith("guest:") else None)
    route = decision.route
    cache_key = _cache_key(query, request, role_mode, prompt_template, route, user_id) if _can_use_cache(request, route) else None

    if cache_key:
        cached = await cache_service.get_response(cache_key)
        if cached is not None:
            return PipelineResult(
                query=query,
                corrected=corrected,
                route=str(cached.get("route", route)),
                route_reason=decision.reason,
                route_confidence=decision.confidence,
                route_source=decision.source,
                route_fallback=decision.fallback,
                prompt="",
                history=[],
                user_id=user_id,
                bot_name=bot_name,
                agent_plan=query_agent.debug_payload(plan),
                context="",
                citations=list(cached.get("citations", [])),
                retrieval=dict(cached.get("retrieval", {})),
                warnings=list(cached.get("warnings", [])) + ["cache_hit"],
                used_rag=bool(cached.get("used_rag", False)),
                role_mode=role_mode,
                prompt_template=prompt_template,
                session_id=session_id,
                cache_key=cache_key,
                cached_response=ChatResponse(
                    response=str(cached.get("response", "")),
                    corrected_query=corrected,
                    sources=list(cached.get("citations", [])),
                    citations=list(cached.get("citations", [])),
                    used_rag=bool(cached.get("used_rag", False)),
                    route=str(cached.get("route", route)),
                    session_id=session_id,
                    model=str(cached.get("model", request.model or settings.groq_model)),
                    role_mode=role_mode,
                    prompt_template=prompt_template,
                    usage=dict(cached.get("usage", {})),
                    retrieval=dict(cached.get("retrieval", {})),
                    warnings=list(cached.get("warnings", [])) + ["cache_hit"],
                    debug={
                        "route": str(cached.get("route", route)),
                        "confidence": decision.confidence,
                        "reason": decision.reason,
                        "source": decision.source,
                        "fallback": decision.fallback,
                        "cache_hit": True,
                    },
                ),
            )

    warnings: list[str] = []
    citations: list[dict[str, Any]] = []
    context = ""
    retrieval = {
        "matches": 0,
        "hybrid_search": bool(request.use_hybrid_search),
        "context_chars": 0,
        "top_score": 0.0,
    }

    attachment_text, attachment_citations, attachment_warnings = await _attachment_context(request.attachments, request.images)
    warnings.extend(attachment_warnings)

    if decision.use_multimodal and attachment_text:
        context = _trim_context(attachment_text)
        citations = attachment_citations
        retrieval = {
            "matches": len(citations),
            "hybrid_search": bool(request.use_hybrid_search),
            "context_chars": len(context),
            "top_score": 1.0,
        }

    if decision.use_retrieval and not context:
        retrieval_key = _retrieval_cache_key(query, request, user_id)
        cached_retrieval = await cache_service.get_retrieval(retrieval_key)
        if cached_retrieval is not None:
            matches = list(cached_retrieval.get("matches", []))
            warnings.append("retrieval_cache_hit")
        else:
            matches = await asyncio.to_thread(hybrid_retriever.search, query, None, user_id)
            await cache_service.set_retrieval(retrieval_key, {"matches": matches})
        context, citations, retrieval = _build_context(matches)
        if retrieval.get("top_score", 0.0) < settings.retrieval_min_score or not citations:
            context = ""
            citations = []
            retrieval["matches"] = 0
            retrieval["context_chars"] = 0
            retrieval["top_score"] = 0.0
            warnings.append("retrieval_skipped_low_confidence")

    merged_history = list(history)
    if cross_chat_history:
        merged_history = cross_chat_history + merged_history
    use_memory = (decision.use_memory or plan.use_memory or bool(cross_chat_history)) and bool(merged_history)
    if decision.use_memory and not history:
        warnings.append("memory_route_without_history")
    if cross_chat_history:
        warnings.append("cross_chat_memory_used")
    memory_text = _memory_block(merged_history if use_memory else [])
    used_rag = bool(context) or (request.force_rag and decision.route in {"rag", "multimodal"})
    prompt = _build_prompt(query, context if used_rag else "", prompt_template, memory_text, bot_name)

    return PipelineResult(
        query=query,
        corrected=corrected,
        route=route,
        route_reason=decision.reason,
        route_confidence=decision.confidence,
        route_source=decision.source,
        route_fallback=decision.fallback,
        prompt=prompt,
        history=merged_history if use_memory else [],
        user_id=user_id,
        bot_name=bot_name,
        agent_plan=query_agent.debug_payload(plan),
        context=context if used_rag else "",
        citations=citations,
        retrieval=retrieval,
        warnings=warnings,
        used_rag=used_rag,
        role_mode=role_mode,
        prompt_template=prompt_template,
        session_id=session_id,
        cache_key=cache_key,
        cached_response=None,
    )


async def _persist_memory(user_id: str | None, session_id: str, query: str, response: str) -> None:
    memory_owner = _memory_owner(user_id, session_id)
    await asyncio.gather(
        asyncio.to_thread(memory_store.save_message, memory_owner, session_id, "user", query),
        asyncio.to_thread(memory_store.save_message, memory_owner, session_id, "assistant", response),
    )


def _debug_payload(pipeline: PipelineResult) -> dict[str, Any]:
    return {
        "route": pipeline.route,
        "confidence": pipeline.route_confidence,
        "reason": pipeline.route_reason,
        "source": pipeline.route_source,
        "fallback": pipeline.route_fallback,
        "retrieved_docs": [
            {
                "source": citation.get("source", ""),
                "kind": citation.get("kind", ""),
                "score": citation.get("score", 0.0),
                "dense_score": citation.get("dense_score", 0.0),
                "lexical_score": citation.get("lexical_score", 0.0),
            }
            for citation in pipeline.citations
        ],
        "agent": pipeline.agent_plan,
        "bot_name": pipeline.bot_name,
    }


async def run_chat(request: ChatRequest, user_id: str | None = None) -> ChatResponse:
    started = time.perf_counter()
    pipeline = await _plan_pipeline(request, user_id=user_id)
    if pipeline.cached_response is not None:
        return pipeline.cached_response

    if _is_greeting(pipeline.query):
        response = _greeting_response()
        await _persist_memory(pipeline.user_id, pipeline.session_id, pipeline.query, response)
        return ChatResponse(
            response=response,
            corrected_query=pipeline.corrected,
            sources=[],
            citations=[],
            used_rag=False,
            route="direct",
            session_id=pipeline.session_id,
            model=request.model or settings.groq_model,
            role_mode=pipeline.role_mode,
            prompt_template=pipeline.prompt_template,
            usage={},
            retrieval={"matches": 0, "hybrid_search": bool(request.use_hybrid_search), "context_chars": 0, "top_score": 0.0},
            warnings=[],
            debug=_debug_payload(pipeline) if request.debug else {},
        )

    result = await llm_service.complete_async(
        pipeline.prompt,
        history=pipeline.history,
        model=request.model,
        role_mode=pipeline.role_mode,
        prompt_template=pipeline.prompt_template,
    )
    response = result.text.strip() or "I could not generate a response."
    await _persist_memory(pipeline.user_id, pipeline.session_id, pipeline.query, response)
    combined_warnings = list(pipeline.warnings) + list(result.warnings)
    latency_ms = round((time.perf_counter() - started) * 1000, 2)

    await asyncio.to_thread(
        app_logger.log,
        "chat",
        user_id=pipeline.user_id,
        session_id=pipeline.session_id,
        query=pipeline.query,
        corrected_query=pipeline.corrected,
        model=result.model,
        role_mode=pipeline.role_mode,
        prompt_template=pipeline.prompt_template,
        route=pipeline.route,
        route_reason=pipeline.route_reason,
        route_confidence=pipeline.route_confidence,
        route_source=pipeline.route_source,
        fallback=pipeline.route_fallback,
        used_rag=pipeline.used_rag,
        cache_hit=False,
        corrected=bool(pipeline.corrected),
        citations=len(pipeline.citations),
        retrieved_documents=[citation.get("source", "") for citation in pipeline.citations],
        retrieval=pipeline.retrieval,
        response=response,
        latency_ms=latency_ms,
    )

    payload = ChatResponse(
        response=str(response),
        corrected_query=pipeline.corrected,
        sources=pipeline.citations,
        citations=pipeline.citations,
        used_rag=pipeline.used_rag,
        route=pipeline.route,
        session_id=pipeline.session_id,
        model=result.model,
        role_mode=pipeline.role_mode,
        prompt_template=pipeline.prompt_template,
        usage=result.usage,
        retrieval={**pipeline.retrieval, "latency_ms": latency_ms},
        warnings=combined_warnings,
        debug=_debug_payload(pipeline) if request.debug else {},
    )
    if pipeline.cache_key:
        await cache_service.set_response(
            pipeline.cache_key,
            {
                "response": payload.response,
                "citations": payload.citations,
                "used_rag": payload.used_rag,
                "route": payload.route,
                "model": payload.model,
                "usage": payload.usage,
                "retrieval": payload.retrieval,
                "warnings": payload.warnings,
            },
        )
    return payload


async def stream_chat(request: ChatRequest, user_id: str | None = None):
    started = time.perf_counter()
    pipeline = await _plan_pipeline(request, user_id=user_id)
    if pipeline.cached_response is not None:
        done_payload = pipeline.cached_response.model_dump()
        done_payload["type"] = "done"
        done_payload["done"] = True
        yield f"data: {json.dumps(done_payload)}\n\n"
        return

    if _is_greeting(pipeline.query):
        response = _greeting_response()
        await _persist_memory(pipeline.user_id, pipeline.session_id, pipeline.query, response)
        done_payload = {
            "type": "done",
            "done": True,
            "response": response,
            "corrected_query": pipeline.corrected,
            "sources": [],
            "citations": [],
            "used_rag": False,
            "route": "direct",
            "session_id": pipeline.session_id,
            "model": request.model or settings.groq_model,
            "role_mode": pipeline.role_mode,
            "prompt_template": pipeline.prompt_template,
            "usage": {},
            "retrieval": {"matches": 0, "hybrid_search": bool(request.use_hybrid_search), "context_chars": 0, "top_score": 0.0},
            "warnings": [],
            "debug": _debug_payload(pipeline) if request.debug else {},
        }
        yield f"data: {json.dumps(done_payload)}\n\n"
        return

    token_stream, meta = await llm_service.stream_async(
        pipeline.prompt,
        history=pipeline.history,
        model=request.model,
        role_mode=pipeline.role_mode,
        prompt_template=pipeline.prompt_template,
    )

    chunks: list[str] = []
    async for token in _iterate_sync_stream(token_stream):
        chunks.append(token)
        payload = {"type": "token", "token": token, "model": str(meta.get("model", ""))}
        yield f"data: {json.dumps(payload)}\n\n"

    final_text = "".join(chunks).strip() or "I could not generate a response."
    usage = {
        "prompt_tokens": int(meta.get("prompt_tokens", max(1, len(pipeline.prompt) // 4))),
        "completion_tokens": max(1, len(final_text) // 4),
    }
    usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
    await _persist_memory(pipeline.user_id, pipeline.session_id, pipeline.query, final_text)
    warnings = list(pipeline.warnings) + list(meta.get("warnings", []))
    latency_ms = round((time.perf_counter() - started) * 1000, 2)

    await asyncio.to_thread(
        app_logger.log,
        "stream",
        user_id=pipeline.user_id,
        session_id=pipeline.session_id,
        query=pipeline.query,
        corrected_query=pipeline.corrected,
        model=str(meta.get("model", "")),
        role_mode=pipeline.role_mode,
        prompt_template=pipeline.prompt_template,
        route=pipeline.route,
        route_reason=pipeline.route_reason,
        route_confidence=pipeline.route_confidence,
        route_source=pipeline.route_source,
        fallback=pipeline.route_fallback,
        used_rag=pipeline.used_rag,
        cache_hit=False,
        corrected=bool(pipeline.corrected),
        citations=len(pipeline.citations),
        retrieved_documents=[citation.get("source", "") for citation in pipeline.citations],
        retrieval=pipeline.retrieval,
        response=final_text,
        latency_ms=latency_ms,
    )

    if pipeline.cache_key:
        await cache_service.set_response(
            pipeline.cache_key,
            {
                "response": final_text,
                "citations": pipeline.citations,
                "used_rag": pipeline.used_rag,
                "route": pipeline.route,
                "model": str(meta.get("model", "")),
                "usage": usage,
                "retrieval": {**pipeline.retrieval, "latency_ms": latency_ms},
                "warnings": warnings,
            },
        )

    done_payload = {
        "type": "done",
        "done": True,
        "response": final_text,
        "corrected_query": pipeline.corrected,
        "sources": pipeline.citations,
        "citations": pipeline.citations,
        "used_rag": pipeline.used_rag,
        "route": pipeline.route,
        "session_id": pipeline.session_id,
        "model": str(meta.get("model", "")),
        "role_mode": pipeline.role_mode,
        "prompt_template": pipeline.prompt_template,
        "usage": usage,
        "retrieval": {**pipeline.retrieval, "latency_ms": latency_ms},
        "warnings": warnings,
        "debug": _debug_payload(pipeline) if request.debug else {},
    }
    yield f"data: {json.dumps(done_payload)}\n\n"
