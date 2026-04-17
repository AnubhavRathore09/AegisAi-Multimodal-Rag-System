from __future__ import annotations

import json
import re
from dataclasses import dataclass

from src.config import settings
from src.services.llm import llm_service

VALID_ROUTES = {"direct", "rag", "memory", "multimodal", "search"}
RAG_KEYWORDS = {
    "document",
    "documents",
    "pdf",
    "file",
    "files",
    "paper",
    "report",
    "notes",
    "receipt",
    "invoice",
    "source",
    "sources",
    "uploaded",
    "upload",
    "doc",
    "docs",
}
MEMORY_KEYWORDS = {"previous", "earlier", "above", "before", "last", "again", "continue", "follow-up", "followup"}
MULTIMODAL_KEYWORDS = {"image", "photo", "picture", "screenshot", "voice", "audio", "mic", "microphone", "scan", "ocr"}
SEARCH_KEYWORDS = {"latest", "live", "breaking", "news", "today", "current", "update", "updates", "headline", "headlines"}


@dataclass(frozen=True)
class RouteDecision:
    route: str
    confidence: float
    reason: str
    source: str
    fallback: bool

    @property
    def use_retrieval(self) -> bool:
        return self.route in {"rag", "multimodal"}

    @property
    def use_memory(self) -> bool:
        return self.route == "memory"

    @property
    def use_multimodal(self) -> bool:
        return self.route == "multimodal"


class LLMRouter:
    def _normalize(self, route: str, confidence: float, reason: str, source: str, fallback: bool) -> RouteDecision:
        value = route if route in VALID_ROUTES else "direct"
        return RouteDecision(
            route=value,
            confidence=max(0.0, min(1.0, float(confidence))),
            reason=(reason or source).strip() or source,
            source=source,
            fallback=fallback,
        )

    def heuristic_route(self, request, history_count: int = 0) -> RouteDecision:
        query = (request.query or "").strip().lower()
        words = [word for word in re.split(r"\s+", query) if word]
        has_files = bool(request.attachments or request.images)

        if has_files or any(keyword in query for keyword in MULTIMODAL_KEYWORDS):
            return self._normalize("multimodal", 0.92, "Current request contains multimodal input.", "heuristic", False)

        if any(keyword in query for keyword in MEMORY_KEYWORDS) or (
            history_count > 0 and len(words) <= 6 and any(token in query for token in {"this", "that", "it", "them"})
        ):
            return self._normalize("memory", 0.82, "Query refers to earlier conversation context.", "heuristic", False)

        if any(keyword in query for keyword in SEARCH_KEYWORDS):
            return self._normalize("search", 0.86, "Query asks for live or current news.", "heuristic", False)

        if any(keyword in query for keyword in RAG_KEYWORDS):
            return self._normalize("rag", 0.8, "Query asks about files or document-grounded knowledge.", "heuristic", False)

        if len(words) <= 3:
            return self._normalize("direct", 0.72, "Short general query without retrieval signals.", "heuristic", False)

        return self._normalize("direct", 0.64, "Default direct route.", "heuristic", False)

    async def classify(self, request, history_count: int = 0) -> RouteDecision:
        heuristic = self.heuristic_route(request, history_count)
        if not settings.router_use_llm or not llm_service.available:
            return heuristic

        prompt = f'''Classify the user request into exactly one route from this list:
direct
rag
memory
multimodal
search

Return JSON only:
{{"route":"direct|rag|memory|multimodal|search","confidence":0.0,"reason":"one line"}}

Query: {request.query}
Has current attachments: {bool(request.attachments)}
Has current images: {bool(request.images)}
Conversation history available: {history_count > 0}
'''
        try:
            result = await llm_service.complete_async(
                prompt,
                history=None,
                model=None,
                role_mode="concise",
                prompt_template="extract",
            )
            raw = (result.text or "").strip()
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            payload = json.loads(match.group(0) if match else raw)
            route = str(payload.get("route", "")).strip().lower()
            confidence = float(payload.get("confidence", 0.0))
            reason = str(payload.get("reason", "LLM route")).strip() or "LLM route"
            if route not in VALID_ROUTES:
                return heuristic
            if confidence < settings.router_llm_confidence_threshold:
                return self._normalize("direct", confidence, reason, "llm", True)
            if bool(request.attachments or request.images) and route != "multimodal":
                return self._normalize("multimodal", max(confidence, 0.9), "Current request contains uploaded multimodal content.", "llm", False)
            return self._normalize(route, confidence, reason, "llm", False)
        except Exception:
            return heuristic


llm_router = LLMRouter()
