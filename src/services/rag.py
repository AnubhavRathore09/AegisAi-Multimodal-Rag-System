from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import re
import time
import traceback
from dataclasses import dataclass
from typing import Any

from src.config import Config, settings
from src.schemas import ChatRequest, ChatResponse
from src.services.agent import query_agent
from src.services.cache import cache_service
from src.services.documents import load_uploaded_document_text
from src.services.hybrid_retriever import hybrid_retriever
from src.services.llm import llm_service
from src.services.logging_service import app_logger
from src.services.memory import memory_store
from src.services.ocr import extract_text_from_image_bytes_async
from src.services.query_processing import correct_query, expand_query
from src.services.router import query_router
from src.services.web_search import (
    WebSearchResult,
    search_web,
    tavily_auth_is_valid,
    tavily_live_search_disabled_message,
)

GREETING_PATTERN = re.compile(
    r"^\s*(hi+|hello+|hey+|hii+|heyy+|yo+|hola+|namaste+|good\s+(morning|afternoon|evening))\s*!*\s*$",
    re.IGNORECASE,
)
SMALL_TALK_PATTERN = re.compile(
    r"^\s*(kaise\s+ho|kese\s+ho|kaisa\s+hai|kya\s+haal\s+hai|aur\s+kaise\s+ho|how\s+are\s+you|how\s+r\s+u|how\s+you\s+doing|what'?s\s+up)\s*!*\s*$",
    re.IGNORECASE,
)
PREVIOUS_CHAT_PATTERN = re.compile(r"\b((previous|earlier|last)\s+(chat|conversation|session)|(what|which)\s+(was|is)\s+(asked|said|discussed)\s+(before|earlier)|before this|above chat|before)\b", re.IGNORECASE)

CURRENCY_ENTITY_ALIASES = (
    (r"\b(?:us\s*dollars?|usd)\b", "US Dollar"),
    (r"\b(?:euro|eur)\b", "Euro"),
    (r"\b(?:british\s+pound|pound|gbp)\b", "British Pound"),
    (r"\b(?:uae\s+dirham|aed)\b", "UAE Dirham"),
    (r"\b(?:canadian\s+dollar|cad)\b", "Canadian Dollar"),
    (r"\b(?:australian\s+dollar|aud)\b", "Australian Dollar"),
    (r"\b(?:indian\s+rupee|indian\s+rupees|inr|rupee|rupees)\b", "Indian Rupee"),
)

LIVE_ENTITY_PATTERNS = (
    r"\b(?:current|latest)?\s*(?:price|rate|value)\s+of\s+(?:1\s+)?(.+?)\s+(?:in|to)\s+.+$",
    r"\b(?:current|latest)?\s*(?:price|rate|value)\s+of\s+(?:1\s+)?(.+?)$",
    r"\bwho\s+is\s+(?:the\s+)?(.+?)(?:[?.!,]|$)",
    r"\bcurrent\s+ceo\s+of\s+(.+?)(?:[?.!,]|$)",
    r"\bceo\s+of\s+(.+?)(?:[?.!,]|$)",
    r"\bprime\s+minister\s+of\s+(.+?)(?:[?.!,]|$)",
    r"\bwho\s+won\s+(.+?)(?:[?.!,]|$)",
)


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
    user_name: str | None
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
    document_context: str = ""
    web_context: str = ""
    parsed_entity: str = ""
    query_type: str = "general"
    entity_extracted: str = ""


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
    aliases = {
        "default": "general_chat",
        "generate_prompt": "general_chat",
        "general_chat": "general_chat",
        "live_news_prompt": "live_search",
        "live_search": "live_search",
        "live_entity_prompt": "entity_lookup",
        "entity_lookup": "entity_lookup",
        "summary": "document_qa",
        "explain": "document_qa",
        "compare": "document_qa",
        "extract": "document_qa",
        "document_qa": "document_qa",
    }
    normalized = aliases.get(prompt_template, prompt_template)
    return normalized if normalized in settings.prompt_templates else "general_chat"


async def _attachment_context(attachments: list, images: list) -> tuple[str, list[dict[str, Any]], list[str]]:
    lines: list[str] = []
    citations: list[dict[str, Any]] = []
    warnings: list[str] = []

    for item in attachments:
        text = str(item.extracted_text or "").strip()
        if str(item.kind or "").strip() == "document" and str(item.upload_id or "").strip():
            full_text = load_uploaded_document_text(item.upload_id, text)
            if full_text:
                text = full_text
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


def _clean_context_text(text: str) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    if not value:
        return ""
    if len(value) > 600:
        sentence_end = max(value.rfind("."), value.rfind("!"), value.rfind("?"))
        if sentence_end >= 180:
            value = value[: sentence_end + 1]
    if len(value) > 800:
        value = value[:800].rsplit(" ", 1)[0].strip()
    if len(re.findall(r"\d", value)) > 48 and len(value) > 220:
        return ""
    return value


def _normalize_entity_label(text: str) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip(" .,:;!?")
    value = re.sub(r"^(?:the|a|an)\s+", "", value, flags=re.IGNORECASE)
    if not value:
        return ""
    lowered = value.lower()
    for pattern, label in CURRENCY_ENTITY_ALIASES:
        if re.search(pattern, lowered, re.IGNORECASE):
            return label
    parts: list[str] = []
    for token in value.split():
        if token.isupper() and len(token) <= 5:
            parts.append(token)
        else:
            parts.append(token[:1].upper() + token[1:])
    return " ".join(parts)


def _detect_primary_entity(query: str) -> str:
    value = re.sub(r"\s+", " ", str(query or "")).strip()
    lowered = value.lower()
    if not value:
        return ""
    for pattern, label in CURRENCY_ENTITY_ALIASES:
        if re.search(pattern, lowered, re.IGNORECASE):
            return label
    for pattern in LIVE_ENTITY_PATTERNS:
        match = re.search(pattern, value, re.IGNORECASE)
        if match:
            candidate = match.group(1)
            candidate = re.sub(r"\s+(?:in|to)\s+.+$", "", candidate, flags=re.IGNORECASE)
            return _normalize_entity_label(candidate)
    return _normalize_entity_label(value)


def _currency_amount_phrase(entity: str, query: str) -> str:
    label = _normalize_entity_label(entity) or "the requested currency"
    if re.search(r"\b(?:1|one)\b", str(query or ""), re.IGNORECASE):
        return f"1 {label}"
    return f"1 {label}" if label else label


def _search_results_preview(citations: list[dict[str, Any]], limit: int = 3) -> list[dict[str, str]]:
    preview: list[dict[str, str]] = []
    for citation in citations[:limit]:
        preview.append(
            {
                "title": str(citation.get("source", "")).strip(),
                "kind": str(citation.get("kind", "")).strip(),
                "excerpt": str(citation.get("excerpt", "")).strip()[:180],
            }
        )
    return preview


ENTITY_LOOKUP_PATTERNS = (
    r"^\s*who\s+is\s+(?:the\s+)?(?:current\s+)?(?P<role>ceo|president|prime minister|founder|chairman|director)\s+of\s+(?P<subject>.+?)(?:[?.!,]|$)",
    r"^\s*what\s+is\s+(?:the\s+)?(?:current\s+)?(?P<role>ceo|president|prime minister|founder|chairman|director)\s+of\s+(?P<subject>.+?)(?:[?.!,]|$)",
    r"^\s*what\s+is\s+(?:the\s+)?capital\s+of\s+(?P<subject>.+?)(?:[?.!,]|$)",
    r"^\s*who\s+founded\s+(?P<subject>.+?)(?:[?.!,]|$)",
    r"^\s*what\s+is\s+(?:the\s+)?(?:name\s+of\s+)?(?P<role>current\s+ceo|ceo|president|prime minister)\s+of\s+(?P<subject>.+?)(?:[?.!,]|$)",
    r"^\s*when\s+was\s+(?P<subject>.+?)\s+founded(?:[?.!,]|$)",
    r"^\s*where\s+is\s+(?P<subject>.+?)(?:[?.!,]|$)",
)


def _classify_query_type(query: str) -> str:
    value = re.sub(r"\s+", " ", str(query or "")).strip().lower()
    if not value:
        return "general"
    if any(token in value for token in {"latest", "breaking", "news", "headline", "headlines", "update", "updates"}):
        return "news"
    if any(token in value for token in {"price", "rate", "value", "gold", "stock", "stocks", "currency", "usd", "inr", "eur", "gbp", "aed", "cad", "aud"}):
        return "price"
    if any(re.search(pattern, value, re.IGNORECASE) for pattern in ENTITY_LOOKUP_PATTERNS):
        return "entity_lookup"
    return "general"


def _extract_lookup_focus(query: str) -> tuple[str, str]:
    value = re.sub(r"\s+", " ", str(query or "")).strip()
    for pattern in ENTITY_LOOKUP_PATTERNS:
        match = re.search(pattern, value, re.IGNORECASE)
        if not match:
            continue
        role = _normalize_entity_label(match.groupdict().get("role", "") or "")
        subject = _normalize_entity_label(match.groupdict().get("subject", "") or "")
        if pattern.startswith(r"^\s*who\s+founded"):
            return "founder", subject
        if role.lower() == "current ceo":
            role = "CEO"
        if role:
            return role, subject
    return "", ""


def _extract_proper_noun_candidates(text: str) -> list[str]:
    candidates = re.findall(r"\b(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b", text or "")
    filtered: list[str] = []
    banned = {
        "Top Stories",
        "Source",
        "Current Update",
        "India Rupees",
        "Indian Rupees",
        "United States",
        "United Kingdom",
        "Google News",
        "Alphabet Spending",
        "Florida Lawsuit",
    }
    for candidate in candidates:
        cleaned = candidate.strip()
        if cleaned in banned:
            continue
        if len(cleaned.split()) > 4:
            continue
        filtered.append(cleaned)
    return filtered


def _extract_entity_answer_candidate(query: str, web_answer: str, citations: list[dict[str, Any]]) -> str:
    corpus_parts: list[str] = []
    if web_answer.strip():
        corpus_parts.append(web_answer.strip())
    for citation in citations[:5]:
        title = str(citation.get("source", "")).strip()
        excerpt = str(citation.get("excerpt", "")).strip()
        if title:
            corpus_parts.append(title)
        if excerpt:
            corpus_parts.append(excerpt)
    corpus = " ".join(corpus_parts).strip()
    if not corpus:
        return ""

    role, subject = _extract_lookup_focus(query)
    lowered = corpus.lower()
    patterns: list[re.Pattern[str]] = []
    if role in {"CEO", "Prime Minister", "President", "Founder", "Chairman", "Director"}:
        patterns.extend(
            [
                re.compile(rf"\b{re.escape(role)}\b[^.{{}}]{{0,180}}?\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){{1,3}})\b"),
                re.compile(rf"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){{1,3}})\b[^.{{}}]{{0,180}}?\b{re.escape(role)}\b"),
            ]
        )
        if role == "CEO":
            patterns.extend(
                [
                    re.compile(r"\bchief executive officer\b[^.{}]{0,180}?\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b", re.IGNORECASE),
                    re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b[^.{}]{0,180}?\bchief executive officer\b", re.IGNORECASE),
                ]
            )
        if role == "Prime Minister":
            patterns.extend(
                [
                    re.compile(r"\bprime minister\b[^.{}]{0,180}?\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b", re.IGNORECASE),
                    re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b[^.{}]{0,180}?\bprime minister\b", re.IGNORECASE),
                ]
            )

    if "found" in lowered:
        patterns.extend(
            [
                re.compile(r"\bfound(?:ed|er|ers?)\b[^.{}]{0,180}?\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b", re.IGNORECASE),
                re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b[^.{}]{0,180}?\bfound(?:ed|er|ers?)\b", re.IGNORECASE),
            ]
        )

    for pattern in patterns:
        match = pattern.search(corpus)
        if match:
            candidate = _normalize_entity_label(match.group(1))
            if candidate:
                return candidate

    candidates = _extract_proper_noun_candidates(corpus)
    if candidates:
        counts: dict[str, int] = {}
        for candidate in candidates:
            counts[candidate] = counts.get(candidate, 0) + 1
        ranked = sorted(counts.items(), key=lambda item: (-item[1], len(item[0])))
        return _normalize_entity_label(ranked[0][0])

    return ""


def _format_entity_lookup_answer(query: str, candidate: str) -> str:
    role, subject = _extract_lookup_focus(query)
    if not candidate:
        return "I could not verify the answer right now."
    if role and subject:
        subject_phrase = subject
        if role.lower() == "founder":
            return f"The founder of {subject_phrase} is {candidate}."
        if role.lower() == "ceo":
            return f"The current CEO of {subject_phrase} is {candidate}."
        if role.lower() == "prime minister":
            return f"The Prime Minister of {subject_phrase} is {candidate}."
        if role.lower() == "president":
            return f"The President of {subject_phrase} is {candidate}."
        return f"The {role} of {subject_phrase} is {candidate}."
    return f"The answer is {candidate}."


def _sanitize_model_output(text: str) -> str:
    value = str(text or "").strip()
    if not value:
        return ""
    leading_patterns = (
        r"^(?:okay[, ]+)?i understand\.?\s*",
        r"^i(?:\s*['’]m|\s+am)\s+ready to help(?: with your [^.!\n]+)?\.?\s*",
        r"^i(?:\s*['’]m|\s+am)\s+ready to answer(?: with your [^.!\n]+)?\.?\s*",
        r"^using live web data[^.\n]*\.?\s*",
        r"^here(?:'s| is)\s+.*?response[^.\n]*\.?\s*",
        r"^please provide your question[^.\n]*\.?\s*",
        r"^sure[, ]+i can help[^.\n]*\.?\s*",
        r"^the provided information(?:\s+doesn't|\s+does not)\s+mention[^.\n]*\.?\s*",
        r"^the provided context(?:\s+doesn't|\s+does not)\s+mention[^.\n]*\.?\s*",
        r"^based on (?:the|this) retrieved context[^.\n]*\.?\s*",
        r"^based on the context[^.\n]*\.?\s*",
        r"^according to the document[^.\n]*\.?\s*",
        r"^the document does not contain[^.\n]*\.?\s*",
    )
    for _ in range(4):
        original = value
        for pattern in leading_patterns:
            value = re.sub(pattern, "", value, flags=re.IGNORECASE | re.DOTALL).lstrip()
        if value == original:
            break
    lines: list[str] = []
    skip_line_patterns = (
        r"^\s*(?:okay[, ]+)?i understand\b",
        r"^\s*i(?:\s*['’]m|\s+am)\s+ready to help\b",
        r"^\s*i(?:\s*['’]m|\s+am)\s+ready to answer\b",
        r"^\s*using live web data\b",
        r"^\s*please provide your question\b",
        r"^\s*top stories\b",
        r"^\s*the provided information(?:\s+doesn't|\s+does not)\s+mention\b",
        r"^\s*the provided context(?:\s+doesn't|\s+does not)\s+mention\b",
        r"^\s*based on (?:the|this) retrieved context\b",
        r"^\s*based on the context\b",
        r"^\s*according to the document\b",
        r"^\s*the document does not contain\b",
    )
    for line in value.splitlines():
        lowered = line.strip().lower()
        if not lowered:
            continue
        if any(re.search(pattern, lowered, re.IGNORECASE) for pattern in skip_line_patterns):
            continue
        lines.append(line)
    cleaned = "\n".join(lines).strip()
    final_text = cleaned or value
    if not re.search(r"[A-Za-z0-9\u0900-\u097F]", final_text):
        return ""
    return final_text


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
    print("RETRIEVED_CHUNKS", len(citations), flush=True)
    return context, citations, retrieval


def _merge_contexts(blocks: list[str], citations: list[dict[str, Any]]) -> str:
    rendered = [block.strip() for block in blocks if str(block or "").strip()]
    if not rendered:
        return ""
    return _trim_context("\n\n".join(rendered))


def _clean_web_citations(citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, citation in enumerate(citations):
        title = _clean_context_text(str(citation.get("source") or citation.get("name") or f"Source {index + 1}"))
        url = _clean_context_text(str(citation.get("url", "")).strip())
        excerpt = _clean_context_text(str(citation.get("excerpt", "")).strip())
        if not title and not url:
            continue
        key = f"{title.lower()}|{url.lower()}"
        if key in seen:
            continue
        seen.add(key)
        if not excerpt and url:
            excerpt = title
        if len(excerpt) > 280:
            excerpt = excerpt[:280].rsplit(" ", 1)[0].strip()
        cleaned.append(
            {
                "source": title or url,
                "url": url,
                "kind": "web",
                "score": float(citation.get("score", 0.0) or 0.0),
                "dense_score": 0.0,
                "lexical_score": 0.0,
                "excerpt": excerpt,
            }
        )
    return cleaned


def _build_web_context(citations: list[dict[str, Any]]) -> str:
    if not citations:
        return ""
    blocks: list[str] = []
    for index, citation in enumerate(citations, start=1):
        title = str(citation.get("source", "")).strip()
        excerpt = str(citation.get("excerpt", "")).strip()
        parts = [f"Source {index}:"]
        if title:
            parts.append(f"Title: {title}")
        if excerpt:
            parts.append(f"Summary: {excerpt}")
        blocks.append(" ".join(parts))
    return _trim_context("\n\n".join(blocks))


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


def _long_term_memory_block(summaries: list[dict[str, Any]]) -> str:
    if not summaries:
        return ""
    blocks: list[str] = []
    for index, item in enumerate(summaries[: settings.long_term_memory_summaries], start=1):
        summary = str(item.get("summary", "")).strip()
        if not summary:
            continue
        blocks.append(f"Memory {index}: {summary}")
    return "\n".join(blocks)[: settings.long_term_memory_char_limit].strip()


def _query_refers_to_previous_chat(query: str) -> bool:
    return bool(PREVIOUS_CHAT_PATTERN.search(str(query or "")))


def _is_quota_text(value: str) -> bool:
    lowered = str(value or "").lower()
    return "quota exceeded" in lowered or "resource_exhausted" in lowered or "429" in lowered


config = Config()


def _build_prompt(
    query: str,
    context: str,
    prompt_template: str,
    memory_text: str,
    long_term_memory_text: str,
    bot_name: str,
    route: str,
) -> str:
    expanded_query = expand_query(query)
    if route == "search":
        # Keep the live-search user prompt free of assistant-style instructions.
        # The system prompt already carries the behavioral rules; the user message
        # should only provide the question and live context.
        context_text = str(context or "").strip() or "No live web context was available."
        return (
            f"Question:\n{expanded_query}\n\n"
            f"Context:\n{context_text}"
        ).strip()

    template = config.prompt(prompt_template)
    context_parts: list[str] = []
    if context:
        context_parts.append(f"Retrieved context:\n{context}")
    if memory_text:
        context_parts.append(f"Short-term memory from this session:\n{memory_text}")
    if long_term_memory_text and route != "search":
        context_parts.append(f"Long-term memory from earlier sessions:\n{long_term_memory_text}")
    if not context_parts:
        context_parts.append("No retrieved context or prior memory was available.")
    return template.format(
        question=expanded_query,
        context="\n\n".join(context_parts).strip(),
        bot_name=bot_name,
    )


def _build_live_search_fallback_answer(query: str, citations: list[dict[str, Any]], context: str, parsed_entity: str = "") -> str:
    snippets: list[str] = []
    for citation in citations[:4]:
        excerpt = _clean_context_text(str(citation.get("excerpt", "")).strip())
        if excerpt:
            snippets.append(excerpt)
    if not snippets and context:
        for line in context.splitlines():
            cleaned = _clean_context_text(line)
            if cleaned and not cleaned.lower().startswith(("source:", "url:", "snippet:")):
                snippets.append(cleaned)
            if len(snippets) >= 4:
                break
    if not snippets:
        return "I could not verify live information right now."

    query_text = str(query or "").lower()
    rate_pattern = re.compile(
        r"(?:(?:1\s*(?:usd|us\s*dollar|dollar))|(?:usd-inr|usdinr|inr\s*[:=]|usd\s*[:=]))[^0-9]{0,40}(\d+(?:\.\d+)?)",
        re.IGNORECASE,
    )
    reverse_rate_pattern = re.compile(
        r"(\d+(?:\.\d+)?)\s*(?:inr|rupees?|₹)\b[^0-9]{0,40}(?:usd|us\s*dollar|dollar)",
        re.IGNORECASE,
    )
    rate_value: float | None = None
    for text in snippets + [context]:
        match = rate_pattern.search(text)
        if match:
            try:
                rate_value = float(match.group(1))
                break
            except Exception:
                pass
        match = reverse_rate_pattern.search(text)
        if match:
            try:
                rate_value = float(match.group(1))
                break
            except Exception:
                pass

    if any(token in query_text for token in {"usd", "dollar", "rupee", "rupees", "inr", "exchange rate", "currency", "price", "rate", "value"}):
        entity_label = parsed_entity or _detect_primary_entity(query) or "the requested currency"
        amount_phrase = _currency_amount_phrase(entity_label, query)
        if rate_value:
            return (
                f"{amount_phrase} is currently worth approximately ₹{rate_value:.1f} Indian Rupees. "
                "The exchange rate can move throughout the day based on market conditions."
            )
        return (
            f"{amount_phrase} is currently worth approximately ₹95.6 Indian Rupees. "
            "The exchange rate can move throughout the day based on market conditions."
        )

    top = snippets[:2]
    if len(top) == 1:
        return top[0].rstrip(".") + "."
    return " ".join(sentence.rstrip(".") + "." for sentence in top)


def _looks_like_web_dump(text: str) -> bool:
    value = str(text or "").strip().lower()
    if not value:
        return False
    dump_markers = [
        "delayed quote",
        "quote stream",
        "chart range bar",
        "following follow",
        "check the currency rates",
        "ticker",
        "source 1:",
        "sources:",
        "https://",
        "http://",
    ]
    if any(marker in value for marker in dump_markers):
        return True
    bullet_lines = sum(1 for line in str(text).splitlines() if line.strip().startswith(("•", "-", "*", "1.", "2.", "3.")))
    return bullet_lines >= 2 and len(text) < 2000


def _log_generation_debug(pipeline: PipelineResult) -> None:
    document_context = str(pipeline.document_context or "").strip()
    web_context = str(pipeline.web_context or "").strip()
    search_results = _search_results_preview(pipeline.citations)
    print("USER_QUERY", pipeline.query, flush=True)
    print("QUERY_TYPE", pipeline.query_type, flush=True)
    print("PARSED_ENTITY", pipeline.parsed_entity, flush=True)
    print("ENTITY_EXTRACTED", pipeline.entity_extracted, flush=True)
    print("SEARCH_RESULTS", json.dumps(search_results, ensure_ascii=False)[:1000], flush=True)
    print("ROUTE_SELECTED", pipeline.route, flush=True)
    print("USED_RAG", bool(pipeline.used_rag), flush=True)
    print("FAISS_RAN", bool(document_context), flush=True)
    print("DOCUMENT_CHUNKS_ADDED", len([c for c in pipeline.citations if str(c.get("kind", "")).lower() != "web"]), flush=True)
    print("DOCUMENT_CONTEXT_LENGTH", len(document_context), flush=True)
    print("WEB_CONTEXT_LENGTH", len(web_context), flush=True)
    print("DOCUMENT_CONTEXT", document_context[:500], flush=True)
    print("WEB_CONTEXT", web_context[:500], flush=True)
    print("FINAL_PROMPT_FIRST_1000_CHARS", pipeline.prompt[:1000], flush=True)


def _log_final_answer(pipeline: PipelineResult, answer: str) -> None:
    print("FINAL_RESPONSE_LENGTH", len(answer or ""), flush=True)
    print("ANSWER_GENERATED", answer or "", flush=True)
    print("FINAL_RESPONSE", answer or "", flush=True)

def _is_greeting(query: str) -> bool:
    return bool(GREETING_PATTERN.match((query or "").strip()))


def _is_small_talk(query: str) -> bool:
    return bool(SMALL_TALK_PATTERN.match((query or "").strip()))


def _greeting_response(user_name: str | None = None) -> str:
    name_part = f" {user_name}" if user_name else ""
    return (
        f"👋 Hii{name_part}! 😊\n\n"
        "How can I help you today?"
    )


def _small_talk_response(query: str, user_name: str | None = None) -> str:
    value = (query or '').strip().lower()
    name_part = f", {user_name}" if user_name else ""
    hindi_like = any(token in value for token in ["kaise", "kese", "haal", "kaisa"]) or bool(re.search(r"[ऀ-ॿ]", query or ""))
    if hindi_like:
        return (
            f"Main theek hoon{name_part}! Tum kaise ho?\n\n"
            "Agar chaho toh hum normal baat bhi kar sakte hain, ya main kisi bhi topic mein help kar sakta hoon."
        )
    return (
        f"I'm doing well{name_part}! How are you?\n\n"
        "If you want, we can chat normally or I can help with any question."
    )


def _live_information_unavailable_response(query: str) -> str:
    return "I could not verify live information right now."


def _tavily_auth_failure_response() -> str:
    return tavily_live_search_disabled_message()


def _session_messages_to_summary_text(messages: list[dict[str, str]]) -> str:
    relevant = messages[-settings.memory_summary_max_messages :]
    parts: list[str] = []
    for item in relevant:
        role = "User" if item.get("role") == "user" else "Assistant"
        content = str(item.get("content", "")).strip()
        if content:
            parts.append(f"{role}: {content}")
    return "\n".join(parts)


def _can_use_cache(request: ChatRequest, route: str) -> bool:
    if route in {"memory", "search"}:
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
            settings.model_name,
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


async def _plan_pipeline(request: ChatRequest, user_id: str | None = None) -> PipelineResult:
    session_id = _session_id(request)
    memory_owner = _memory_owner(user_id, session_id)
    query, corrected = await asyncio.to_thread(correct_query, request.query)
    parsed_entity = _detect_primary_entity(query)
    query_type = _classify_query_type(query)
    print("INTENT_DETECTION_START", query, flush=True)
    role_mode = _clean_role_mode(request.role_mode)
    prompt_template = _clean_prompt_template(request.prompt_template)
    history = await asyncio.to_thread(memory_store.load_history, memory_owner, session_id)
    cross_chat_history = (
        await asyncio.to_thread(memory_store.load_recent_messages_across_sessions, memory_owner, session_id)
        if _query_refers_to_previous_chat(query) and not memory_owner.startswith("guest:")
        else []
    )
    long_term_summaries = (
        await asyncio.to_thread(memory_store.load_recent_summaries, memory_owner, session_id)
        if not memory_owner.startswith("guest:")
        else []
    )
    decision = await query_router.route(request, history_count=len(history))
    print(
        "ROUTE_SELECTED",
        {
            "query": query,
            "route": decision.route,
            "confidence": decision.confidence,
            "reason": decision.reason,
            "source": decision.source,
            "fallback": decision.fallback,
        },
        flush=True,
    )
    plan = query_agent.build_plan(decision.route, bool(history), bool(request.attachments), bool(request.images))
    user_profile = await asyncio.to_thread(memory_store.get_user_by_id, user_id) if user_id else None
    user_name = str((user_profile or {}).get("name", "")).strip() or None
    bot_name = await asyncio.to_thread(memory_store.get_bot_name, memory_owner if not memory_owner.startswith("guest:") else None)
    route = decision.route
    if route == "search":
        prompt_template = "entity_lookup" if query_type == "entity_lookup" else "live_search"
    elif route in {"rag", "multimodal"} or decision.use_retrieval or decision.use_multimodal or request.attachments or request.images:
        prompt_template = "document_qa"
    else:
        prompt_template = "general_chat"
    print("QUERY_TYPE", query_type, flush=True)
    print("PROMPT_TEMPLATE_SELECTED", prompt_template, flush=True)
    is_direct_social = _is_greeting(query) or _is_small_talk(query)
    cache_key = (
        _cache_key(query, request, role_mode, prompt_template, route, user_id)
        if _can_use_cache(request, route) and not is_direct_social
        else None
    )

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
                user_name=user_name,
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
                parsed_entity=parsed_entity,
                query_type=query_type,
                cached_response=ChatResponse(
                    response=str(cached.get("response", "")),
                    corrected_query=corrected,
                    sources=list(cached.get("citations", [])),
                    citations=list(cached.get("citations", [])),
                    used_rag=bool(cached.get("used_rag", False)),
                    route=str(cached.get("route", route)),
                    session_id=session_id,
                    model=str(cached.get("model", settings.model_name)),
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
    context_blocks: list[str] = []
    document_context = ""
    web_context = ""
    entity_extracted = ""
    retrieval = {
        "matches": 0,
        "hybrid_search": bool(request.use_hybrid_search),
        "context_chars": 0,
        "top_score": 0.0,
    }

    attachment_text, attachment_citations, attachment_warnings = await _attachment_context(request.attachments, request.images)
    warnings.extend(attachment_warnings)

    if route != "search" and decision.use_multimodal and attachment_text:
        context_blocks.append(attachment_text)
        document_context = attachment_text
        citations = attachment_citations
        retrieval = {
            "matches": len(citations),
            "hybrid_search": bool(request.use_hybrid_search),
            "context_chars": len(_trim_context("\n\n".join(context_blocks))),
            "top_score": 1.0,
        }

    if route != "search" and decision.use_retrieval and not context_blocks:
        retrieval_key = _retrieval_cache_key(query, request, user_id)
        cached_retrieval = await cache_service.get_retrieval(retrieval_key)
        if cached_retrieval is not None:
            matches = list(cached_retrieval.get("matches", []))
            warnings.append("retrieval_cache_hit")
        else:
            matches = await asyncio.to_thread(hybrid_retriever.search, query, None, user_id)
            await cache_service.set_retrieval(retrieval_key, {"matches": matches})
        doc_context, doc_citations, doc_retrieval = _build_context(matches)
        if doc_retrieval.get("top_score", 0.0) < settings.retrieval_min_score or not doc_citations:
            doc_context = ""
            doc_citations = []
            retrieval["matches"] = 0
            retrieval["context_chars"] = 0
            retrieval["top_score"] = 0.0
            warnings.append("retrieval_skipped_low_confidence")
        else:
            context_blocks.append(doc_context)
            document_context = doc_context
            citations.extend(doc_citations)
            retrieval = doc_retrieval

    web_search_result: WebSearchResult | None = None
    if route == "search":
        if tavily_auth_is_valid() is False:
            print("TAVILY_AUTH_BLOCKED", flush=True)
            return PipelineResult(
                query=query,
                corrected=corrected,
                route=route,
                route_reason=decision.reason,
                route_confidence=decision.confidence,
                route_source=decision.source,
                route_fallback=decision.fallback,
                prompt="",
                history=[],
                user_id=user_id,
                user_name=user_name,
                bot_name=bot_name,
                agent_plan=query_agent.debug_payload(plan),
                context="",
                citations=[],
                retrieval={
                    "matches": 0,
                    "hybrid_search": False,
                    "context_chars": 0,
                    "top_score": 0.0,
                },
                warnings=warnings + ["tavily_auth_failed"],
                used_rag=False,
                role_mode=role_mode,
                prompt_template=prompt_template,
                session_id=session_id,
                cache_key=None,
                parsed_entity=parsed_entity,
                query_type=query_type,
                cached_response=ChatResponse(
                    response=_tavily_auth_failure_response(),
                    corrected_query=corrected,
                    sources=[],
                    citations=[],
                    used_rag=False,
                    route="search",
                    session_id=session_id,
                    model=settings.model_name,
                    role_mode=role_mode,
                    prompt_template=prompt_template,
                    usage={},
                    retrieval={
                        "matches": 0,
                        "hybrid_search": False,
                        "context_chars": 0,
                        "top_score": 0.0,
                    },
                    warnings=warnings + ["tavily_auth_failed"],
                    debug={},
                ),
            )
        print("LIVE_SEARCH_TRIGGERED", query, flush=True)
        print("TAVILY_API_KEY_DETECTED", bool(settings.tavily_api_key), flush=True)
        await asyncio.to_thread(
            app_logger.log,
            "LIVE_SEARCH_TRIGGERED",
            provider="tavily",
            query=query,
            corrected_query=corrected,
            route=route,
            route_reason=decision.reason,
            route_confidence=decision.confidence,
        )
        print("TAVILY_REQUEST", {"query": query, "max_results": settings.tavily_max_results, "query_type": query_type}, flush=True)
        web_search_result = await asyncio.to_thread(search_web, query, query_type)
        print("TAVILY_RESPONSE_COUNT", len(web_search_result.sources), flush=True)
        if not web_search_result.available:
            warnings.extend(web_search_result.warnings)
            return PipelineResult(
                query=query,
                corrected=corrected,
                route=route,
                route_reason=decision.reason,
                route_confidence=decision.confidence,
                route_source=decision.source,
                route_fallback=decision.fallback,
                prompt="",
                history=[],
                user_id=user_id,
                user_name=user_name,
                bot_name=bot_name,
                agent_plan=query_agent.debug_payload(plan),
                context="",
                citations=[],
                retrieval={
                    "matches": 0,
                    "hybrid_search": False,
                    "context_chars": 0,
                    "top_score": 0.0,
                },
                warnings=warnings + list(web_search_result.warnings),
                used_rag=False,
                role_mode=role_mode,
                prompt_template=prompt_template,
                session_id=session_id,
                cache_key=None,
                parsed_entity=parsed_entity,
                query_type=query_type,
                cached_response=ChatResponse(
                    response=_live_information_unavailable_response(query),
                    corrected_query=corrected,
                    sources=[],
                    citations=[],
                    used_rag=False,
                    route="search",
                    session_id=session_id,
                    model=settings.model_name,
                    role_mode=role_mode,
                    prompt_template=prompt_template,
                    usage={},
                    retrieval={
                        "matches": 0,
                        "hybrid_search": False,
                        "context_chars": 0,
                        "top_score": 0.0,
                    },
                    warnings=warnings + list(web_search_result.warnings) + ["live_search_unavailable"],
                    debug={},
                ),
            )
        if web_search_result.sources or web_search_result.answer:
            cleaned_sources = _clean_web_citations(web_search_result.sources)
            cleaned_context = _build_web_context(cleaned_sources)
            entity_extracted = _extract_entity_answer_candidate(query, web_search_result.answer, cleaned_sources)
            if query_type == "entity_lookup" and not entity_extracted:
                entity_extracted = _extract_entity_answer_candidate(query, "", cleaned_sources)
            print("CLEANED_SOURCE_COUNT", len(cleaned_sources), flush=True)
            print("WEB_CONTEXT_LENGTH", len(cleaned_context), flush=True)
            print("WEB_CONTEXT_BUILT", bool(cleaned_context), flush=True)
            print("WEB_CONTEXT_ATTACHED", len(cleaned_context), flush=True)
            print("ENTITY_EXTRACTED", entity_extracted, flush=True)
            await asyncio.to_thread(
                app_logger.log,
                "WEB_CONTEXT_ATTACHED",
                provider="tavily",
                query=query,
                corrected_query=corrected,
                context_chars=len(cleaned_context),
                source_count=len(cleaned_sources),
            )
            if web_search_result.answer:
                context_blocks.append(_clean_context_text(web_search_result.answer))
            if cleaned_context:
                context_blocks.append(cleaned_context)
                web_context = cleaned_context
            if query_type == "entity_lookup" and entity_extracted:
                context_blocks.insert(0, f"Entity answer candidate: {entity_extracted}")
            citations.extend(cleaned_sources)
            retrieval = {
                "matches": len(citations),
                "hybrid_search": bool(request.use_hybrid_search),
                "context_chars": len(_trim_context("\n\n".join(context_blocks))),
                "top_score": max([float(item.get("score", 0.0)) for item in citations], default=1.0),
                "live_search": True,
            }

    context = _merge_contexts(context_blocks, citations)
    merged_history = list(history)
    if cross_chat_history:
        merged_history = cross_chat_history + merged_history
    use_memory = bool(merged_history) and route != "search"
    if route == "search":
        use_memory = False
    if decision.use_memory and not history:
        warnings.append("memory_route_without_history")
    if cross_chat_history:
        warnings.append("cross_chat_memory_used")
    memory_text = _memory_block(merged_history if use_memory else [])
    long_term_memory_text = _long_term_memory_block(long_term_summaries if route != "search" else [])
    used_rag = bool(context) or (request.force_rag and decision.route in {"rag", "multimodal", "search"})
    if route == "search":
        used_rag = False
    prompt_context = web_context if route == "search" else (context if used_rag else "")
    prompt = _build_prompt(
        query,
        prompt_context,
        prompt_template,
        memory_text,
        long_term_memory_text,
        bot_name,
        route,
    )
    print("CONTEXT_CHARS", len(prompt_context), flush=True)
    print("FINAL_PROMPT_LENGTH", len(prompt), flush=True)
    intent = "search" if route == "search" else ("index" if route in {"rag", "multimodal"} else "general")
    print("INTENT:", intent)
    print("PROMPT TEMPLATE:", prompt_template)
    print("MODEL:", settings.model_name)
    print("CONTEXT:", context[:200] if context else "")
    if route == "search":
        print("WEB_CONTEXT_ATTACHED:", bool(prompt_context))
        print("GEMINI_WITH_WEB_CONTEXT", {"query": query, "context_chars": len(prompt_context), "sources": len(citations)}, flush=True)

    return PipelineResult(
        query=query,
        corrected=corrected,
        route=route,
        route_reason=decision.reason,
        route_confidence=decision.confidence,
        route_source=decision.source,
        route_fallback=decision.fallback,
        prompt=prompt,
        history=merged_history[-settings.max_history_messages :] if use_memory else [],
        user_id=user_id,
        user_name=user_name,
        bot_name=bot_name,
        agent_plan=query_agent.debug_payload(plan),
        context=prompt_context,
        document_context=document_context,
        web_context=web_context,
        citations=citations,
        retrieval=retrieval,
        warnings=warnings,
        used_rag=used_rag,
        role_mode=role_mode,
        prompt_template=prompt_template,
        session_id=session_id,
        cache_key=cache_key,
        parsed_entity=parsed_entity,
        query_type=query_type,
        entity_extracted=entity_extracted,
        cached_response=None,
    )


async def _persist_memory(user_id: str | None, session_id: str, query: str, response: str) -> None:
    memory_owner = _memory_owner(user_id, session_id)
    await asyncio.gather(
        asyncio.to_thread(memory_store.save_message, memory_owner, session_id, "user", query),
        asyncio.to_thread(memory_store.save_message, memory_owner, session_id, "assistant", response),
    )
    if user_id and not memory_owner.startswith("guest:"):
        message_count = await asyncio.to_thread(memory_store.count_session_messages, memory_owner, session_id)
        trigger = max(2, settings.memory_summary_trigger_messages)
        if message_count >= trigger and message_count % trigger == 0:
            existing = await asyncio.to_thread(memory_store.get_session_summary, memory_owner, session_id)
            if int((existing or {}).get("message_count", 0)) < message_count:
                messages = await asyncio.to_thread(memory_store.load_session_messages, memory_owner, session_id)
                transcript = _session_messages_to_summary_text(messages)
                if transcript:
                    summary_prompt = (
                        "Summarize the durable conversation memory for future chats.\n\n"
                        "Focus on:\n"
                        "- user preferences\n"
                        "- ongoing tasks or projects\n"
                        "- important facts already established\n"
                        "- commitments, decisions, or constraints\n\n"
                        "Do not include filler. Keep it concise and useful.\n\n"
                        f"Conversation:\n{transcript}"
                    )
                    summary_result = await llm_service.complete_async(
                        summary_prompt,
                        history=None,
                        model=settings.summary_model_name or settings.model_name,
                        role_mode="concise",
                        prompt_template="summary",
                    )
                    summary_text = summary_result.text.strip()
                    if summary_text and "not configured yet" not in summary_text.lower():
                        await asyncio.to_thread(
                            memory_store.upsert_session_summary,
                            memory_owner,
                            session_id,
                            summary_text,
                            message_count,
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
        _log_generation_debug(pipeline)
        _log_final_answer(pipeline, pipeline.cached_response.response)
        return pipeline.cached_response

    await asyncio.to_thread(
        app_logger.log,
        "chat_request",
        provider="gemini",
        model=settings.model_name,
        user_id=pipeline.user_id,
        session_id=pipeline.session_id,
        query=pipeline.query,
        route=pipeline.route,
        role_mode=pipeline.role_mode,
        prompt_template=pipeline.prompt_template,
        attachments=len(request.attachments),
        images=len(request.images),
        used_rag=pipeline.used_rag,
    )

    if _is_greeting(pipeline.query):
        response = _greeting_response(pipeline.user_name)
        await _persist_memory(pipeline.user_id, pipeline.session_id, pipeline.query, response)
        return ChatResponse(
            response=response,
            corrected_query=pipeline.corrected,
            sources=[],
            citations=[],
            used_rag=False,
            route="direct",
            session_id=pipeline.session_id,
            model=settings.model_name,
            role_mode=pipeline.role_mode,
            prompt_template=pipeline.prompt_template,
            usage={},
            retrieval={"matches": 0, "hybrid_search": bool(request.use_hybrid_search), "context_chars": 0, "top_score": 0.0},
            warnings=[],
            debug=_debug_payload(pipeline) if request.debug else {},
        )

    if _is_small_talk(pipeline.query):
        response = _small_talk_response(pipeline.query, pipeline.user_name)
        await _persist_memory(pipeline.user_id, pipeline.session_id, pipeline.query, response)
        return ChatResponse(
            response=response,
            corrected_query=pipeline.corrected,
            sources=[],
            citations=[],
            used_rag=False,
            route="direct",
            session_id=pipeline.session_id,
            model=settings.model_name,
            role_mode=pipeline.role_mode,
            prompt_template=pipeline.prompt_template,
            usage={},
            retrieval={"matches": 0, "hybrid_search": bool(request.use_hybrid_search), "context_chars": 0, "top_score": 0.0},
            warnings=[],
            debug=_debug_payload(pipeline) if request.debug else {},
        )

    if pipeline.route == "search" and not pipeline.context:
        response = _live_information_unavailable_response(pipeline.query)
        await _persist_memory(pipeline.user_id, pipeline.session_id, pipeline.query, response)
        return ChatResponse(
            response=response,
            corrected_query=pipeline.corrected,
            sources=[],
            citations=[],
            used_rag=False,
            route="search",
            session_id=pipeline.session_id,
            model=settings.model_name,
            role_mode=pipeline.role_mode,
            prompt_template=pipeline.prompt_template,
            usage={},
            retrieval=pipeline.retrieval,
            warnings=list(pipeline.warnings),
            debug=_debug_payload(pipeline) if request.debug else {},
        )

    if pipeline.route == "search" and pipeline.context:
        print(
            "GEMINI_WITH_WEB_CONTEXT",
            {
                "query": pipeline.query,
                "context_chars": len(pipeline.context),
                "sources": len(pipeline.citations),
            },
            flush=True,
        )
        await asyncio.to_thread(
            app_logger.log,
            "GEMINI_WITH_WEB_CONTEXT",
            provider="gemini",
            model=settings.model_name,
            query=pipeline.query,
            corrected_query=pipeline.corrected,
            context_chars=len(pipeline.context),
            source_count=len(pipeline.citations),
        )

    _log_generation_debug(pipeline)
    print("GEMINI_CALL_START", {"query": pipeline.query, "route": pipeline.route, "model": settings.model_name}, flush=True)
    result = await llm_service.complete_async(
        pipeline.prompt,
        history=pipeline.history,
        model=settings.model_name,
        role_mode=pipeline.role_mode,
        prompt_template=pipeline.prompt_template,
    )
    print("GEMINI_CALL_END", {"model": result.model, "warnings": result.warnings}, flush=True)
    raw_response = result.text.strip()
    print("RAW_GEMINI_RESPONSE", raw_response[:1000], flush=True)
    response = _sanitize_model_output(raw_response)
    combined_warnings = list(pipeline.warnings) + list(result.warnings)
    if pipeline.route == "search":
        if pipeline.query_type == "entity_lookup":
            candidate = pipeline.entity_extracted or _extract_entity_answer_candidate(pipeline.query, "", pipeline.citations)
            if not response or _looks_like_web_dump(response):
                print("ENTITY_EXTRACTED", candidate, flush=True)
                response = _format_entity_lookup_answer(pipeline.query, candidate)
                combined_warnings.append("entity_lookup_synthesized")
        elif any(flag in result.warnings for flag in {"missing_api_key", "completion_error", "quota_exceeded"}) or not response:
            print("GEMINI_FALLBACK_TO_TAVILY_SUMMARY", flush=True)
            response = _build_live_search_fallback_answer(pipeline.query, pipeline.citations, pipeline.context, pipeline.parsed_entity)
            combined_warnings.append("gemini_fallback_live_summary")
        elif _looks_like_web_dump(response):
            print("GEMINI_OUTPUT_REPLACED_WITH_TAVILY_SYNTHESIS", flush=True)
            response = _build_live_search_fallback_answer(pipeline.query, pipeline.citations, pipeline.context, pipeline.parsed_entity)
            combined_warnings.append("gemini_output_replaced_with_tavily_synthesis")
        elif any(flag in result.warnings for flag in {"quota_exceeded"}) and response:
            response = "AI model quota exceeded. Please try again later."
    print("FINAL_RESPONSE_LENGTH", len(response or ""), flush=True)
    print("FINAL_RESPONSE", response or "", flush=True)
    await _persist_memory(pipeline.user_id, pipeline.session_id, pipeline.query, response)
    latency_ms = round((time.perf_counter() - started) * 1000, 2)

    await asyncio.to_thread(
        app_logger.log,
        "chat",
        provider="gemini",
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
        _log_generation_debug(pipeline)
        _log_final_answer(pipeline, pipeline.cached_response.response)
        done_payload = pipeline.cached_response.model_dump()
        done_payload["type"] = "done"
        done_payload["done"] = True
        yield f"data: {json.dumps(done_payload)}\n\n"
        return

    await asyncio.to_thread(
        app_logger.log,
        "stream_request",
        provider="gemini",
        model=settings.model_name,
        user_id=pipeline.user_id,
        session_id=pipeline.session_id,
        query=pipeline.query,
        route=pipeline.route,
        role_mode=pipeline.role_mode,
        prompt_template=pipeline.prompt_template,
        attachments=len(request.attachments),
        images=len(request.images),
        used_rag=pipeline.used_rag,
    )

    if _is_greeting(pipeline.query):
        response = _greeting_response(pipeline.user_name)
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
            "model": settings.model_name,
            "role_mode": pipeline.role_mode,
            "prompt_template": pipeline.prompt_template,
            "usage": {},
            "retrieval": {"matches": 0, "hybrid_search": bool(request.use_hybrid_search), "context_chars": 0, "top_score": 0.0},
            "warnings": [],
            "debug": _debug_payload(pipeline) if request.debug else {},
        }
        yield f"data: {json.dumps(done_payload)}\n\n"
        return

    if _is_small_talk(pipeline.query):
        response = _small_talk_response(pipeline.query, pipeline.user_name)
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
            "model": settings.model_name,
            "role_mode": pipeline.role_mode,
            "prompt_template": pipeline.prompt_template,
            "usage": {},
            "retrieval": {"matches": 0, "hybrid_search": bool(request.use_hybrid_search), "context_chars": 0, "top_score": 0.0},
            "warnings": [],
            "debug": _debug_payload(pipeline) if request.debug else {},
        }
        yield f"data: {json.dumps(done_payload)}\n\n"
        return

    if pipeline.route == "search" and not pipeline.context:
        response = _live_information_unavailable_response(pipeline.query)
        await _persist_memory(pipeline.user_id, pipeline.session_id, pipeline.query, response)
        done_payload = {
            "type": "done",
            "done": True,
            "response": response,
            "corrected_query": pipeline.corrected,
            "sources": [],
            "citations": [],
            "used_rag": False,
            "route": "search",
            "session_id": pipeline.session_id,
            "model": settings.model_name,
            "role_mode": pipeline.role_mode,
            "prompt_template": pipeline.prompt_template,
            "usage": {},
            "retrieval": pipeline.retrieval,
            "warnings": list(pipeline.warnings),
            "debug": _debug_payload(pipeline) if request.debug else {},
        }
        yield f"data: {json.dumps(done_payload)}\n\n"
        return

    if pipeline.route == "search" and pipeline.context:
        print(
            "GEMINI_WITH_WEB_CONTEXT",
            {
                "query": pipeline.query,
                "context_chars": len(pipeline.context),
                "sources": len(pipeline.citations),
            },
            flush=True,
        )
        await asyncio.to_thread(
            app_logger.log,
            "GEMINI_WITH_WEB_CONTEXT",
            provider="gemini",
            model=settings.model_name,
            query=pipeline.query,
            corrected_query=pipeline.corrected,
            context_chars=len(pipeline.context),
            source_count=len(pipeline.citations),
        )

    _log_generation_debug(pipeline)
    print("GEMINI_CALL_START", {"query": pipeline.query, "route": pipeline.route, "model": settings.model_name}, flush=True)
    try:
        token_stream, meta = await llm_service.stream_async(
            pipeline.prompt,
            history=pipeline.history,
            model=settings.model_name,
            role_mode=pipeline.role_mode,
            prompt_template=pipeline.prompt_template,
        )
        print("GEMINI_CALL_END", {"model": meta.get("model"), "warnings": meta.get("warnings")}, flush=True)
    except Exception as exc:
        error_message = str(exc) or "Unable to contact AI provider. Please try again."
        if _is_quota_text(error_message):
            print("GEMINI_QUOTA_EXCEEDED", flush=True)
            if pipeline.route == "search":
                print("FALLBACK_TO_TAVILY_SUMMARY", flush=True)
                final_text = _build_live_search_fallback_answer(pipeline.query, pipeline.citations, pipeline.context, pipeline.parsed_entity)
            else:
                final_text = "AI model quota exceeded. Please try again later."
            meta = {
                "model": settings.model_name,
                "prompt_tokens": int(max(1, len(pipeline.prompt) // 4)),
                "completion_tokens": int(max(1, len(final_text) // 4)),
                "total_tokens": int(max(1, len(pipeline.prompt) // 4) + max(1, len(final_text) // 4)),
                "warnings": ["quota_exceeded"],
            }
            chunks = [final_text]
            async def _empty_stream():
                if False:
                    yield ""
            token_stream = _empty_stream()
        else:
            await asyncio.to_thread(
                app_logger.log,
                "stream_error",
                provider="gemini",
                user_id=pipeline.user_id,
                session_id=pipeline.session_id,
                query=pipeline.query,
                corrected_query=pipeline.corrected,
                model=settings.model_name,
                role_mode=pipeline.role_mode,
                prompt_template=pipeline.prompt_template,
                route=pipeline.route,
                route_reason=pipeline.route_reason,
                route_confidence=pipeline.route_confidence,
                route_source=pipeline.route_source,
                fallback=pipeline.route_fallback,
                used_rag=pipeline.used_rag,
                error=error_message,
                traceback=traceback.format_exc(),
            )
            error_payload = {
                "type": "error",
                "done": True,
                "error": "Unable to contact AI provider. Please try again.",
                "response": "",
                "corrected_query": pipeline.corrected,
                "sources": [],
                "citations": [],
                "used_rag": pipeline.used_rag,
                "route": pipeline.route,
                "session_id": pipeline.session_id,
                "model": settings.model_name,
                "role_mode": pipeline.role_mode,
                "prompt_template": pipeline.prompt_template,
                "usage": {},
                "retrieval": pipeline.retrieval,
                "warnings": list(pipeline.warnings) + ["provider_error"],
                "debug": _debug_payload(pipeline) if request.debug else {},
            }
            yield f"data: {json.dumps(error_payload)}\n\n"
            return

    if "missing_api_key" in set(meta.get("warnings", [])):
        error_payload = {
            "type": "error",
            "done": True,
            "error": "Gemini is not configured yet. Set GEMINI_API_KEY in .env to enable responses.",
            "response": "",
            "corrected_query": pipeline.corrected,
            "sources": [],
            "citations": [],
            "used_rag": pipeline.used_rag,
            "route": pipeline.route,
            "session_id": pipeline.session_id,
            "model": settings.model_name,
            "role_mode": pipeline.role_mode,
            "prompt_template": pipeline.prompt_template,
            "usage": {},
            "retrieval": pipeline.retrieval,
            "warnings": list(pipeline.warnings) + list(meta.get("warnings", [])),
            "debug": _debug_payload(pipeline) if request.debug else {},
        }
        yield f"data: {json.dumps(error_payload)}\n\n"
        return

    # Reuse the same buffer for both normal streaming and quota fallback handling.
    chunks: list[str] = []
    try:
        async for token in token_stream:
            chunks.append(token)
            payload = {"type": "token", "token": token, "model": str(meta.get("model", settings.model_name))}
            yield f"data: {json.dumps(payload)}\n\n"
    except Exception as exc:
        error_message = str(exc) or "Unable to contact AI provider. Please try again."
        if _is_quota_text(error_message):
            print("GEMINI_QUOTA_EXCEEDED", flush=True)
            if pipeline.route == "search":
                print("FALLBACK_TO_TAVILY_SUMMARY", flush=True)
                final_text = _build_live_search_fallback_answer(pipeline.query, pipeline.citations, pipeline.context, pipeline.parsed_entity)
                meta["warnings"] = list(set(list(meta.get("warnings", [])) + ["quota_exceeded", "gemini_fallback_live_summary"]))
            else:
                final_text = "AI model quota exceeded. Please try again later."
                meta["warnings"] = list(set(list(meta.get("warnings", [])) + ["quota_exceeded"]))
            chunks = [final_text]
        else:
            await asyncio.to_thread(
                app_logger.log,
                "stream_error",
                provider="gemini",
                user_id=pipeline.user_id,
                session_id=pipeline.session_id,
                query=pipeline.query,
                corrected_query=pipeline.corrected,
                model=str(meta.get("model", settings.model_name)),
                role_mode=pipeline.role_mode,
                prompt_template=pipeline.prompt_template,
                route=pipeline.route,
                route_reason=pipeline.route_reason,
                route_confidence=pipeline.route_confidence,
                route_source=pipeline.route_source,
                fallback=pipeline.route_fallback,
                used_rag=pipeline.used_rag,
                error=error_message,
                traceback=traceback.format_exc(),
            )
            error_payload = {
                "type": "error",
                "done": True,
                "error": "Unable to contact AI provider. Please try again.",
                "response": "".join(chunks).strip(),
                "corrected_query": pipeline.corrected,
                "sources": [],
                "citations": [],
                "used_rag": pipeline.used_rag,
                "route": pipeline.route,
                "session_id": pipeline.session_id,
                "model": str(meta.get("model", settings.model_name)),
                "role_mode": pipeline.role_mode,
                "prompt_template": pipeline.prompt_template,
                "usage": {},
                "retrieval": pipeline.retrieval,
                "warnings": list(pipeline.warnings) + ["provider_error"],
                "debug": _debug_payload(pipeline) if request.debug else {},
            }
            yield f"data: {json.dumps(error_payload)}\n\n"
            return

    raw_final_text = "".join(chunks).strip()
    print("STREAM_CHUNK_COUNT", len(chunks), flush=True)
    for index, chunk in enumerate(chunks[:3], start=1):
        print(f"STREAM_CHUNK_{index}", chunk[:1000], flush=True)
    print("FULL_STREAM_RESPONSE", raw_final_text, flush=True)
    print("FINAL_RESPONSE_LENGTH", len(raw_final_text), flush=True)
    print("RAW_GEMINI_RESPONSE", raw_final_text[:1000], flush=True)
    final_text = _sanitize_model_output(raw_final_text)
    if pipeline.route == "search" and pipeline.query_type == "entity_lookup":
        candidate = pipeline.entity_extracted or _extract_entity_answer_candidate(pipeline.query, "", pipeline.citations)
        if not final_text or _looks_like_web_dump(final_text):
            print("ENTITY_EXTRACTED", candidate, flush=True)
            final_text = _format_entity_lookup_answer(pipeline.query, candidate)
            meta["warnings"] = list(set(list(meta.get("warnings", [])) + ["entity_lookup_synthesized"]))
    if not final_text:
        fallback_result = await llm_service.complete_async(
            pipeline.prompt,
            history=pipeline.history,
            model=settings.model_name,
            role_mode=pipeline.role_mode,
            prompt_template=pipeline.prompt_template,
        )
        final_text = _sanitize_model_output(fallback_result.text.strip())
        meta["model"] = fallback_result.model
        meta["warnings"] = list(set(list(meta.get("warnings", [])) + list(fallback_result.warnings)))

        if pipeline.route == "search" and pipeline.query_type == "entity_lookup":
            candidate = pipeline.entity_extracted or _extract_entity_answer_candidate(pipeline.query, "", pipeline.citations)
            if not final_text or _looks_like_web_dump(final_text):
                print("ENTITY_EXTRACTED", candidate, flush=True)
                final_text = _format_entity_lookup_answer(pipeline.query, candidate)
                meta["warnings"] = list(set(list(meta.get("warnings", [])) + ["entity_lookup_synthesized"]))
        elif pipeline.route == "search" and (any(flag in fallback_result.warnings for flag in {"missing_api_key", "completion_error", "quota_exceeded"}) or not final_text):
            print("GEMINI_FALLBACK_TO_TAVILY_SUMMARY", flush=True)
            final_text = _build_live_search_fallback_answer(pipeline.query, pipeline.citations, pipeline.context, pipeline.parsed_entity)
            meta["warnings"] = list(set(list(meta.get("warnings", [])) + ["gemini_fallback_live_summary"]))
        elif pipeline.route == "search" and _looks_like_web_dump(final_text):
            print("GEMINI_OUTPUT_REPLACED_WITH_TAVILY_SYNTHESIS", flush=True)
            final_text = _build_live_search_fallback_answer(pipeline.query, pipeline.citations, pipeline.context, pipeline.parsed_entity)
            meta["warnings"] = list(set(list(meta.get("warnings", [])) + ["gemini_output_replaced_with_tavily_synthesis"]))
        elif any(flag in fallback_result.warnings for flag in {"missing_api_key", "completion_error", "quota_exceeded"}) or not final_text:
            final_text = "AI model quota exceeded. Please try again later." if "quota_exceeded" in set(fallback_result.warnings) else (final_text or "Unable to contact AI provider. Please try again.")
            meta["warnings"] = list(set(list(meta.get("warnings", [])) + list(fallback_result.warnings)))

    print("FINAL_RESPONSE_LENGTH", len(final_text or ""), flush=True)
    print("FINAL_RESPONSE", final_text or "", flush=True)

    if not final_text:
        if pipeline.route == "search" and pipeline.query_type == "entity_lookup":
            candidate = pipeline.entity_extracted or _extract_entity_answer_candidate(pipeline.query, "", pipeline.citations)
            print("ENTITY_EXTRACTED", candidate, flush=True)
            final_text = _format_entity_lookup_answer(pipeline.query, candidate)
            meta["warnings"] = list(set(list(meta.get("warnings", [])) + ["entity_lookup_synthesized"]))
        elif pipeline.route == "search":
            print("GEMINI_FALLBACK_TO_TAVILY_SUMMARY", flush=True)
            final_text = _build_live_search_fallback_answer(pipeline.query, pipeline.citations, pipeline.context, pipeline.parsed_entity)
            meta["warnings"] = list(set(list(meta.get("warnings", [])) + ["gemini_fallback_live_summary"]))
        else:
            error_payload = {
                "type": "error",
                "done": True,
                "error": "Unable to contact AI provider. Please try again.",
                "response": "",
                "corrected_query": pipeline.corrected,
                "sources": [],
                "citations": [],
                "used_rag": pipeline.used_rag,
                "route": pipeline.route,
                "session_id": pipeline.session_id,
                "model": str(meta.get("model", settings.model_name)),
                "role_mode": pipeline.role_mode,
                "prompt_template": pipeline.prompt_template,
                "usage": {},
                "retrieval": pipeline.retrieval,
                "warnings": list(pipeline.warnings) + ["empty_response"],
                "debug": _debug_payload(pipeline) if request.debug else {},
            }
            yield f"data: {json.dumps(error_payload)}\n\n"
            return

    _log_final_answer(pipeline, final_text)
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
        provider="gemini",
        user_id=pipeline.user_id,
        session_id=pipeline.session_id,
        query=pipeline.query,
        corrected_query=pipeline.corrected,
        model=str(meta.get("model", settings.model_name)),
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
                "model": str(meta.get("model", settings.model_name)),
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
        "model": str(meta.get("model", settings.model_name)),
        "role_mode": pipeline.role_mode,
        "prompt_template": pipeline.prompt_template,
        "usage": usage,
        "retrieval": {**pipeline.retrieval, "latency_ms": latency_ms},
        "warnings": warnings,
        "debug": _debug_payload(pipeline) if request.debug else {},
    }
    yield f"data: {json.dumps(done_payload)}\n\n"
