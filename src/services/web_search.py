from __future__ import annotations

import json
import ssl
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen

from src.config import settings
from src.services.logging_service import app_logger


TAVILY_ENDPOINT = "https://api.tavily.com/search"
TAVILY_KEY_PATTERN = re.compile(r"^tvly-[A-Za-z0-9_-]{10,}$")
TAVILY_AUTH_VALID: bool | None = None
TAVILY_AUTH_ERROR: str = ""


@dataclass
class WebSearchResult:
    query: str
    context: str = ""
    sources: list[dict[str, Any]] = field(default_factory=list)
    answer: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def available(self) -> bool:
        return bool(self.context or self.sources or self.answer)


def _ssl_context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _set_auth_status(valid: bool | None, error: str = "") -> None:
    global TAVILY_AUTH_VALID, TAVILY_AUTH_ERROR
    TAVILY_AUTH_VALID = valid
    TAVILY_AUTH_ERROR = error


def tavily_auth_is_valid() -> bool | None:
    return TAVILY_AUTH_VALID


def tavily_auth_error_message() -> str:
    return TAVILY_AUTH_ERROR


def tavily_healthcheck() -> bool:
    api_key = (settings.tavily_api_key or "").strip()
    if not api_key:
        _set_auth_status(False, "Invalid Tavily API key. Please update TAVILY_API_KEY in .env")
        print("TAVILY_HEALTHCHECK_FAILED", "missing_api_key", flush=True)
        return False
    if not TAVILY_KEY_PATTERN.match(api_key):
        _set_auth_status(False, "Invalid Tavily API key. Please update TAVILY_API_KEY in .env")
        print("TAVILY_HEALTHCHECK_FAILED", "invalid_key_format", flush=True)
        return False

    payload = {
        "query": "Tavily health check",
        "search_depth": "basic",
        "topic": "general",
        "max_results": 1,
        "include_answer": False,
        "include_raw_content": False,
        "include_images": False,
    }
    request = Request(
        TAVILY_ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "AegisAI/1.0",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=settings.web_search_timeout_seconds, context=_ssl_context()) as response:
            status = getattr(response, "status", None)
            raw_text = response.read().decode("utf-8")
        print("TAVILY_HEALTHCHECK_HTTP_STATUS", status, flush=True)
        print("TAVILY_HEALTHCHECK_RESPONSE_BODY", raw_text[:1000], flush=True)
        data = json.loads(raw_text)
        results = _normalize_results(data)
        if 200 <= int(status or 0) < 300 and isinstance(results, list):
            print("TAVILY_HEALTHCHECK_OK", flush=True)
            _set_auth_status(True, "")
            return True
        _set_auth_status(False, "Invalid Tavily API key. Please update TAVILY_API_KEY in .env")
        print("TAVILY_HEALTHCHECK_FAILED", "unexpected_response", flush=True)
        return False
    except HTTPError as exc:
        try:
            raw_error = exc.read().decode("utf-8", errors="replace")
        except Exception:
            raw_error = ""
        print("TAVILY_HEALTHCHECK_HTTP_STATUS", getattr(exc, "code", None), flush=True)
        print("TAVILY_HEALTHCHECK_RESPONSE_BODY", raw_error[:1000], flush=True)
        print("TAVILY_HEALTHCHECK_FAILED", repr(exc), flush=True)
        _set_auth_status(False, "Invalid Tavily API key. Please update TAVILY_API_KEY in .env")
        return False
    except Exception as exc:
        print("TAVILY_HEALTHCHECK_FAILED", repr(exc), flush=True)
        _set_auth_status(False, "Invalid Tavily API key. Please update TAVILY_API_KEY in .env")
        return False


def tavily_live_search_disabled_message() -> str:
    return TAVILY_AUTH_ERROR or "Invalid Tavily API key. Please update TAVILY_API_KEY in .env"


def _normalize_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
    results = payload.get("results", [])
    return results if isinstance(results, list) else []


def _infer_topic(query: str) -> str:
    value = (query or "").lower()
    finance_terms = {"stock", "stocks", "share", "shares", "market", "gold", "price", "prices", "nifty", "sensex", "crypto", "bitcoin", "nvidia", "apple", "tesla"}
    news_terms = {"latest", "live", "breaking", "news", "today", "current", "recent", "update", "updates", "headline", "headlines", "election", "elections", "ipl", "match", "score", "scores", "winner", "won", "win", "weather", "forecast", "temperature"}
    if any(term in value for term in finance_terms):
        return "finance"
    if any(term in value for term in news_terms):
        return "news"
    return "general"


def _infer_country(query: str) -> str | None:
    value = (query or "").lower()
    if "india" in value or "indian" in value or "delhi" in value or "mumbai" in value or "bangalore" in value or "bengaluru" in value:
        return "india"
    return None


def _result_to_citation(item: dict[str, Any], index: int) -> dict[str, Any]:
    title = str(item.get("title") or item.get("url") or f"Source {index + 1}").strip()
    url = str(item.get("url") or "").strip()
    content = str(item.get("content") or item.get("raw_content") or item.get("snippet") or "").strip()
    score = float(item.get("score", 0.0) or 0.0)
    return {
        "source": title,
        "url": url,
        "kind": "web",
        "score": score,
        "dense_score": 0.0,
        "lexical_score": 0.0,
        "excerpt": content[:220],
    }


def _build_context(citations: list[dict[str, Any]], answer: str = "") -> str:
    blocks: list[str] = []
    if answer.strip():
        blocks.append(f"Tavily answer:\n{answer.strip()}")
    for citation in citations:
        lines = [f"Source: {citation['source']}"]
        url = str(citation.get("url", "")).strip()
        excerpt = str(citation.get("excerpt", "")).strip()
        if url:
            lines.append(f"URL: {url}")
        if excerpt:
            lines.append(f"Snippet: {excerpt}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks).strip()


def search_web(query: str, query_type: str = "general") -> WebSearchResult:
    api_key = (settings.tavily_api_key or "").strip()
    raw_query = str(query or "").strip()
    if not raw_query:
        return WebSearchResult(query=raw_query, warnings=["empty_query"])
    if not api_key:
        return WebSearchResult(query=raw_query, warnings=["missing_api_key"])
    if TAVILY_AUTH_VALID is False:
        return WebSearchResult(query=raw_query, warnings=["tavily_auth_failed"])

    try:
        app_logger.log(
            "TAVILY_API_KEY_DETECTED",
            provider="tavily",
            enabled=True,
            query=raw_query,
        )
    except Exception:
        pass

    print("TAVILY_API_URL", TAVILY_ENDPOINT, flush=True)

    payload = {
        "query": raw_query,
        "search_depth": "advanced",
        "topic": _infer_topic(raw_query),
        "max_results": int(settings.tavily_max_results),
        "include_answer": query_type == "entity_lookup",
        "include_raw_content": False,
        "include_images": False,
    }
    country = _infer_country(raw_query)
    if country:
        payload["country"] = country

    request = Request(
        TAVILY_ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "AegisAI/1.0",
        },
        method="POST",
    )

    try:
        try:
            app_logger.log(
                "TAVILY_REQUEST",
                provider="tavily",
                query=raw_query,
                max_results=int(settings.tavily_max_results),
                search_depth=payload["search_depth"],
                topic=payload["topic"],
                country=payload.get("country"),
            )
        except Exception:
            pass
        print("TAVILY_REQUEST", payload, flush=True)
        with urlopen(request, timeout=settings.web_search_timeout_seconds, context=_ssl_context()) as response:
            status = getattr(response, "status", None)
            print("TAVILY_HTTP_STATUS", status, flush=True)
            raw_text = response.read().decode("utf-8")
        print("TAVILY_RESPONSE_BODY", raw_text[:1000], flush=True)
        data = json.loads(raw_text)
    except HTTPError as exc:
        try:
            raw_error = exc.read().decode("utf-8", errors="replace")
        except Exception:
            raw_error = ""
        print("TAVILY_HTTP_STATUS", getattr(exc, "code", None), flush=True)
        print("TAVILY_RESPONSE_BODY", raw_error[:1000], flush=True)
        print("TAVILY_EXCEPTION", repr(exc), flush=True)
        try:
            app_logger.log("TAVILY_RESPONSE_COUNT", provider="tavily", query=raw_query, count=0, error=str(exc))
        except Exception:
            pass
        return WebSearchResult(query=raw_query, warnings=[f"request_failed:{exc}"])
    except (URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        print("TAVILY_EXCEPTION", repr(exc), flush=True)
        try:
            app_logger.log("TAVILY_RESPONSE_COUNT", provider="tavily", query=raw_query, count=0, error=str(exc))
        except Exception:
            pass
        return WebSearchResult(query=raw_query, warnings=[f"request_failed:{exc}"])
    except Exception as exc:
        print("TAVILY_EXCEPTION", repr(exc), flush=True)
        try:
            app_logger.log("TAVILY_RESPONSE_COUNT", provider="tavily", query=raw_query, count=0, error=str(exc))
        except Exception:
            pass
        return WebSearchResult(query=raw_query, warnings=[f"request_failed:{exc}"])

    results = _normalize_results(data)
    print("TAVILY_RESULTS_COUNT", len(results), flush=True)
    citations = [_result_to_citation(item, idx) for idx, item in enumerate(results) if isinstance(item, dict)]
    answer = str(data.get("answer") or "").strip()
    context = _build_context(citations, answer=answer)
    warnings: list[str] = []
    if not citations and not answer:
        warnings.append("no_results")
    try:
        app_logger.log(
            "TAVILY_RESPONSE_COUNT",
            provider="tavily",
            query=raw_query,
            count=len(citations),
            has_answer=bool(answer),
        )
    except Exception:
        pass
    print("TAVILY_RESPONSE_COUNT", len(citations), flush=True)
    if citations:
        print("TAVILY_FIRST_RESULT_TITLE", citations[0]["source"], flush=True)
    return WebSearchResult(query=raw_query, context=context, sources=citations, answer=answer, warnings=warnings)
