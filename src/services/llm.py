from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from openai import APITimeoutError, APIConnectionError, APIStatusError, AsyncOpenAI, OpenAI

from src.config import settings
from src.services.logging_service import app_logger


PROMPT_FILE = Path(__file__).resolve().parents[2] / "prompt.yaml"

DEFAULT_SYSTEM_PROMPT = """You are Aegis AI, a grounded, context-aware AI assistant.

Core behavior:
- Be intelligent, conversational, and directly helpful.
- Answer the user's question directly first.
- Do not repeat the user's question.
- Write naturally, like a strong expert assistant in a real conversation.
- Use retrieved context and memory as supporting evidence, but do not talk about them explicitly unless the user asks.
- If the answer depends on missing facts, say so clearly instead of guessing.
- Do not invent citations, events, statistics, or quotes.
- When the user asks a follow-up, use prior conversation naturally.
- Avoid template language, filler phrases, and repetitive openings.
- Never start with phrases like "Based on...", "According to the retrieved context...", or "Here is the latest verified update...".

Grounding rules:
- Separate retrieved facts from background knowledge.
- If the retrieved context is weak, incomplete, or conflicting, acknowledge that.
- For current events or live-news questions, only answer from provided live context.
- When live-web context is provided, use it for grounding only and never reveal URLs, citations, snippets, or raw retrieval text in the final answer.
- For file/document questions, stay anchored to the retrieved document context.

Response style:
- Be concise first, then expand if useful.
- Prefer short paragraphs over rigid headings.
- Use headings or bullets only when they genuinely improve readability.
- Sound like a thoughtful assistant, not a search engine or a document parser.
"""

DEFAULT_TEMPLATE_INSTRUCTIONS = {
    "default": "Answer naturally and directly. Keep the tone human, concise, and useful. Use context when available, but do not mention it unless necessary.",
    "general_chat": "Answer naturally and directly. Start with the answer. Keep the tone conversational, useful, and human. Avoid template-like wording and repetitive sectioning.",
    "entity_lookup": "Answer entity lookup questions directly and concisely. Return the entity or name immediately. Avoid disclaimers, document language, and repeated phrasing.",
    "live_search": "Answer live or time-sensitive questions naturally. Start with the direct answer. Use the live context for grounding, but never reveal URLs, snippets, or raw retrieval text.",
    "document_qa": "Answer document and OCR questions naturally. Start with the direct answer. Summarize clearly without document-parser language or disclaimer phrasing.",
    "generate_prompt": "Answer naturally and directly. Keep the tone human, concise, and useful. Use context when available, but do not mention it unless necessary.",
    "live_news_prompt": "Answer naturally from live context only. Start with the direct answer and never reveal URLs, snippets, or raw retrieval text.",
    "live_entity_prompt": "Answer entity lookup questions directly and concisely. Return the entity or name immediately. Avoid disclaimers, document language, and repeated phrasing.",
    "summary": "Write a clear, human-friendly summary focused on the main ideas, not a document-parser style outline.",
    "explain": "Explain the concept clearly and naturally, with examples when they genuinely help.",
    "compare": "Compare the items clearly and naturally. Use a table only if it improves readability.",
    "extract": "Return exactly what the user asked for, then add only a very short note if it helps.",
}

ROLE_INSTRUCTIONS = {
    "assistant": "Balanced, practical, conversational, and user-friendly.",
    "teacher": "Clear, patient, example-driven, and easy to follow.",
    "researcher": "Evidence-driven, careful with uncertainty, and explicit about what is grounded.",
    "coder": "Implementation-oriented, precise, and technically rigorous.",
    "concise": "Short, direct, and high-signal.",
}


def _load_prompt_config() -> dict[str, Any]:
    if not PROMPT_FILE.exists():
        return {}
    try:
        payload = yaml.safe_load(PROMPT_FILE.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


PROMPT_CONFIG = _load_prompt_config()
PROMPTS = PROMPT_CONFIG.get("prompts", PROMPT_CONFIG) if isinstance(PROMPT_CONFIG, dict) else {}
BASE_SYSTEM_PROMPT = str(PROMPTS.get("system_prompt") or DEFAULT_SYSTEM_PROMPT).strip()
TEMPLATE_INSTRUCTIONS = {
    **DEFAULT_TEMPLATE_INSTRUCTIONS,
    **{k: str(v).strip() for k, v in PROMPTS.items() if k in DEFAULT_TEMPLATE_INSTRUCTIONS},
}


@dataclass
class CompletionResult:
    text: str
    model: str
    usage: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


class GeminiLLMService:
    def __init__(self) -> None:
        self.primary_model = (settings.model_name or "gemini-2.5-flash").strip()
        self.fallback_model = (settings.fallback_model_name or "").strip()
        self.available = bool(settings.gemini_api_key)
        client_kwargs = {
            "api_key": settings.gemini_api_key,
            "base_url": settings.gemini_base_url,
            "timeout": settings.llm_timeout_seconds,
            "default_headers": {
                "X-Title": settings.app_name,
            },
        }
        self.client = OpenAI(**client_kwargs) if self.available else None
        self.async_client = AsyncOpenAI(**client_kwargs) if self.available else None

    def resolve_model(self, requested_model: str | None = None) -> str:
        # The backend is authoritative: the active model always comes from .env.
        return self.primary_model

    def _candidate_models(self) -> list[str]:
        ordered = [self.primary_model]
        if self.fallback_model and self.fallback_model != self.primary_model:
            ordered.append(self.fallback_model)
        return ordered

    def _is_quota_error(self, exc: Exception) -> bool:
        message = str(exc or "").lower()
        if "quota" in message or "resource_exhausted" in message or "429" in message:
            return True
        status = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
        return int(status or 0) == 429

    def _estimate_tokens(self, *parts: str) -> int:
        return max(1, sum(len(part or "") for part in parts) // 4)

    def _format_provider_error(self, exc: Exception) -> str:
        message = str(exc or "").strip()
        lowered = message.lower()
        if self._is_quota_error(exc) or "resource_exhausted" in lowered:
            return "AI model quota exceeded. Please try again later."
        if "401" in lowered or "unauthor" in lowered or "api key" in lowered:
            return "Gemini authentication failed. Please check GEMINI_API_KEY in .env."
        if "404" in lowered or "not found" in lowered or "model" in lowered and "unavailable" in lowered:
            return "The selected Gemini model is currently unavailable. Please try again shortly or change MODEL_NAME in .env."
        if "timeout" in lowered or "timed out" in lowered:
            return "Unable to contact AI provider. Please try again."
        return "Unable to contact AI provider. Please try again."

    def _print_gemini_exception(self, exc: Exception) -> None:
        print("GEMINI_EXCEPTION", repr(exc), flush=True)
        if self._is_quota_error(exc):
            print("GEMINI_QUOTA_EXCEEDED", flush=True)
        if isinstance(exc, APIStatusError):
            status = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
            body = ""
            response = getattr(exc, "response", None)
            if response is not None:
                try:
                    body = getattr(response, "text", "") or ""
                except Exception:
                    try:
                        body = response.read().decode("utf-8", errors="replace")
                    except Exception:
                        body = ""
            print("GEMINI_HTTP_STATUS", status, flush=True)
            print("GEMINI_RESPONSE_BODY", body[:1000], flush=True)
        elif isinstance(exc, APIConnectionError):
            print("GEMINI_HTTP_STATUS", None, flush=True)
            print("GEMINI_RESPONSE_BODY", str(exc)[:1000], flush=True)
        elif isinstance(exc, APITimeoutError):
            print("GEMINI_HTTP_STATUS", None, flush=True)
            print("GEMINI_RESPONSE_BODY", "timeout", flush=True)

    async def healthcheck_async(self) -> bool:
        if not self.available or self.async_client is None:
            print("GEMINI_HEALTHCHECK_FAILED", "missing_api_key", flush=True)
            return False
        try:
            print(
                "GEMINI_CALL_START",
                {"phase": "healthcheck", "model": self.primary_model, "base_url": settings.gemini_base_url},
                flush=True,
            )
            response = await self.async_client.chat.completions.create(
                model=self.primary_model,
                messages=[
                    {"role": "system", "content": "Reply with a single word: ok"},
                    {"role": "user", "content": "ping"},
                ],
                temperature=0,
                max_completion_tokens=1,
            )
            print("GEMINI_HTTP_STATUS", getattr(response, "status_code", 200), flush=True)
            print("GEMINI_HEALTHCHECK_OK", flush=True)
            return True
        except Exception as exc:
            self._print_gemini_exception(exc)
            print("GEMINI_HEALTHCHECK_FAILED", flush=True)
            return False

    def build_system_prompt(self, role_mode: str, prompt_template: str) -> str:
        role_text = ROLE_INSTRUCTIONS.get(role_mode, ROLE_INSTRUCTIONS["assistant"])
        template_key = prompt_template if prompt_template in TEMPLATE_INSTRUCTIONS else "default"
        template_text = TEMPLATE_INSTRUCTIONS.get(template_key, TEMPLATE_INSTRUCTIONS["default"])
        return (
            f"{BASE_SYSTEM_PROMPT}\n\n"
            f"Role mode:\n{role_text}\n\n"
            f"Style guide:\n{template_text}"
        )

    def _build_messages(
        self,
        prompt: str,
        history: list[dict[str, str]] | None = None,
        role_mode: str = "assistant",
        prompt_template: str = "default",
    ) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": self.build_system_prompt(role_mode, prompt_template)}
        ]
        for item in (history or [])[-settings.max_history_messages :]:
            role = str(item.get("role", "user")).strip() or "user"
            content = str(item.get("content", "")).strip()
            if content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": prompt})
        return messages

    def _usage_dict(self, usage: Any, prompt: str, text: str) -> dict[str, int]:
        prompt_tokens = int(getattr(usage, "prompt_tokens", self._estimate_tokens(prompt)))
        completion_tokens = int(getattr(usage, "completion_tokens", self._estimate_tokens(text)))
        total_tokens = int(getattr(usage, "total_tokens", prompt_tokens + completion_tokens))
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }

    def complete(
        self,
        prompt: str,
        history: list[dict[str, str]] | None = None,
        model: str | None = None,
        role_mode: str = "assistant",
        prompt_template: str = "default",
    ) -> CompletionResult:
        ordered_models = self._candidate_models()
        resolved_model = ordered_models[0]
        if not self.available or self.client is None:
            text = "Gemini is not configured yet. Set GEMINI_API_KEY in .env to enable responses."
            return CompletionResult(
                text=text,
                model=resolved_model,
                usage={
                    "prompt_tokens": self._estimate_tokens(prompt),
                    "completion_tokens": self._estimate_tokens(text),
                    "total_tokens": self._estimate_tokens(prompt, text),
                },
                warnings=["missing_api_key"],
            )

        last_exc: Exception | None = None
        for candidate_model in ordered_models:
            try:
                print(
                    "GEMINI_CALL_START",
                    {"model": candidate_model, "base_url": settings.gemini_base_url, "mode": "complete_sync"},
                    flush=True,
                )
                response = self.client.chat.completions.create(
                    model=candidate_model,
                    messages=self._build_messages(prompt, history, role_mode, prompt_template),
                    temperature=0.2,
                    max_completion_tokens=1400,
                )
                print("GEMINI_HTTP_STATUS", getattr(response, "status_code", 200), flush=True)
                body_preview = str(getattr(response.choices[0].message, "content", "") or "")
                print("GEMINI_RESPONSE_BODY", body_preview[:1000], flush=True)
                text = str(response.choices[0].message.content or "").strip()
                warnings: list[str] = []
                if candidate_model != resolved_model:
                    warnings.append("fallback_model_used")
                if not text:
                    warnings.append("empty_response")
                return CompletionResult(
                    text=text or "Unable to contact AI provider. Please try again.",
                    model=str(candidate_model),
                    usage=self._usage_dict(None, prompt, text),
                    warnings=warnings,
                )
            except Exception as exc:
                self._print_gemini_exception(exc)
                last_exc = exc
                continue

        text = self._format_provider_error(last_exc or Exception("Unknown provider error"))
        warnings = ["completion_error"]
        if last_exc and self._is_quota_error(last_exc):
            warnings.append("quota_exceeded")
        return CompletionResult(
            text=text,
            model=resolved_model,
            usage={
                "prompt_tokens": self._estimate_tokens(prompt),
                "completion_tokens": self._estimate_tokens(text),
                "total_tokens": self._estimate_tokens(prompt, text),
            },
            warnings=warnings,
        )

    async def complete_async(
        self,
        prompt: str,
        history: list[dict[str, str]] | None = None,
        model: str | None = None,
        role_mode: str = "assistant",
        prompt_template: str = "default",
    ) -> CompletionResult:
        ordered_models = self._candidate_models()
        resolved_model = ordered_models[0]
        if not self.available or self.async_client is None:
            text = "Gemini is not configured yet. Set GEMINI_API_KEY in .env to enable responses."
            return CompletionResult(
                text=text,
                model=resolved_model,
                usage={
                    "prompt_tokens": self._estimate_tokens(prompt),
                    "completion_tokens": self._estimate_tokens(text),
                    "total_tokens": self._estimate_tokens(prompt, text),
                },
                warnings=["missing_api_key"],
            )

        last_exc: Exception | None = None
        for candidate_model in ordered_models:
            try:
                print(
                    "GEMINI_CALL_START",
                    {"model": candidate_model, "base_url": settings.gemini_base_url, "mode": "complete"},
                    flush=True,
                )
                stream = await self.async_client.chat.completions.create(
                    model=candidate_model,
                    messages=self._build_messages(prompt, history, role_mode, prompt_template),
                    temperature=0.2,
                    max_completion_tokens=1400,
                    stream=True,
                )
                collected: list[str] = []
                chunk_debug: list[str] = []
                async for chunk in stream:
                    delta = chunk.choices[0].delta.content if chunk.choices else ""
                    token = str(delta or "")
                    if token:
                        collected.append(token)
                        if len(chunk_debug) < 3:
                            chunk_debug.append(token)
                text = "".join(collected).strip()
                print("STREAM_CHUNK_COUNT", len(collected), flush=True)
                for idx, chunk_text in enumerate(chunk_debug, start=1):
                    print(f"STREAM_CHUNK_{idx}", chunk_text[:500], flush=True)
                print("FULL_STREAM_RESPONSE", text[:1000], flush=True)
                print("FINAL_RESPONSE_LENGTH", len(text), flush=True)
                print("GEMINI_HTTP_STATUS", 200, flush=True)
                print("GEMINI_RESPONSE_BODY", text[:1000], flush=True)
                warnings: list[str] = []
                if candidate_model != resolved_model:
                    warnings.append("fallback_model_used")
                if not text:
                    warnings.append("empty_response")
                return CompletionResult(
                    text=text or "Unable to contact AI provider. Please try again.",
                    model=str(candidate_model),
                    usage=self._usage_dict(None, prompt, text),
                    warnings=warnings,
                )
            except Exception as exc:
                self._print_gemini_exception(exc)
                last_exc = exc
                continue

        text = self._format_provider_error(last_exc or Exception("Unknown provider error"))
        warnings = ["completion_error"]
        if last_exc and self._is_quota_error(last_exc):
            warnings.append("quota_exceeded")
        return CompletionResult(
            text=text,
            model=resolved_model,
            usage={
                "prompt_tokens": self._estimate_tokens(prompt),
                "completion_tokens": self._estimate_tokens(text),
                "total_tokens": self._estimate_tokens(prompt, text),
            },
            warnings=warnings,
        )

    def stream(
        self,
        prompt: str,
        history: list[dict[str, str]] | None = None,
        model: str | None = None,
        role_mode: str = "assistant",
        prompt_template: str = "default",
    ) -> tuple[Iterable[str], dict[str, str | int | list[str]]]:
        ordered_models = self._candidate_models()
        resolved_model = ordered_models[0]
        meta: dict[str, str | int | list[str]] = {
            "model": resolved_model,
            "prompt_tokens": self._estimate_tokens(prompt),
            "completion_tokens": 0,
            "total_tokens": 0,
            "warnings": [],
        }

        if not self.available or self.client is None:
            def disabled() -> Iterable[str]:
                yield "Gemini is not configured yet. Set GEMINI_API_KEY in .env to enable responses."

            meta["warnings"] = ["missing_api_key"]
            return disabled(), meta

        def generator() -> Iterable[str]:
            last_exc: Exception | None = None
            for candidate_model in ordered_models:
                collected: list[str] = []
                try:
                    meta["model"] = candidate_model
                    meta["warnings"] = ["fallback_model_used"] if candidate_model != resolved_model else []
                    stream = self.client.chat.completions.create(
                        model=candidate_model,
                        messages=self._build_messages(prompt, history, role_mode, prompt_template),
                        temperature=0.2,
                        max_completion_tokens=1400,
                        stream=True,
                    )
                    for chunk in stream:
                        usage = getattr(chunk, "usage", None)
                        if usage:
                            usage_dict = self._usage_dict(usage, prompt, "".join(collected))
                            meta["prompt_tokens"] = usage_dict["prompt_tokens"]
                            meta["completion_tokens"] = usage_dict["completion_tokens"]
                            meta["total_tokens"] = usage_dict["total_tokens"]
                        delta = chunk.choices[0].delta.content if chunk.choices else ""
                        token = str(delta or "")
                        if token:
                            collected.append(token)
                            yield token
                    if not meta.get("total_tokens"):
                        usage_dict = self._usage_dict(None, prompt, "".join(collected))
                        meta["prompt_tokens"] = usage_dict["prompt_tokens"]
                        meta["completion_tokens"] = usage_dict["completion_tokens"]
                        meta["total_tokens"] = usage_dict["total_tokens"]
                    return
                except Exception as exc:
                    last_exc = exc
                    if collected:
                        raise RuntimeError(self._format_provider_error(exc)) from exc
                    continue
            raise RuntimeError(self._format_provider_error(last_exc or Exception("Unknown provider error")))

        return generator(), meta

    async def stream_async(
        self,
        prompt: str,
        history: list[dict[str, str]] | None = None,
        model: str | None = None,
        role_mode: str = "assistant",
        prompt_template: str = "default",
    ) -> tuple[AsyncIterator[str], dict[str, str | int | list[str]]]:
        ordered_models = self._candidate_models()
        resolved_model = ordered_models[0]
        meta: dict[str, str | int | list[str]] = {
            "model": resolved_model,
            "prompt_tokens": self._estimate_tokens(prompt),
            "completion_tokens": 0,
            "total_tokens": 0,
            "warnings": [],
        }

        if not self.available or self.async_client is None:
            async def disabled() -> AsyncIterator[str]:
                yield "Gemini is not configured yet. Set GEMINI_API_KEY in .env to enable responses."

            meta["warnings"] = ["missing_api_key"]
            return disabled(), meta

        async def generator() -> AsyncIterator[str]:
            last_exc: Exception | None = None
            for candidate_model in ordered_models:
                collected: list[str] = []
                chunk_debug: list[str] = []
                try:
                    print(
                        "GEMINI_CALL_START",
                        {"model": candidate_model, "base_url": settings.gemini_base_url, "mode": "stream"},
                        flush=True,
                    )
                    meta["model"] = candidate_model
                    meta["warnings"] = ["fallback_model_used"] if candidate_model != resolved_model else []
                    stream = await self.async_client.chat.completions.create(
                        model=candidate_model,
                        messages=self._build_messages(prompt, history, role_mode, prompt_template),
                        temperature=0.2,
                        max_completion_tokens=1400,
                        stream=True,
                    )
                    async for chunk in stream:
                        usage = getattr(chunk, "usage", None)
                        if usage:
                            usage_dict = self._usage_dict(usage, prompt, "".join(collected))
                            meta["prompt_tokens"] = usage_dict["prompt_tokens"]
                            meta["completion_tokens"] = usage_dict["completion_tokens"]
                            meta["total_tokens"] = usage_dict["total_tokens"]
                        delta = chunk.choices[0].delta.content if chunk.choices else ""
                        token = str(delta or "")
                        if token:
                            collected.append(token)
                            if len(chunk_debug) < 3:
                                chunk_debug.append(token)
                            yield token
                    full_stream_response = "".join(collected)
                    print("STREAM_CHUNK_COUNT", len(collected), flush=True)
                    for idx, chunk_text in enumerate(chunk_debug, start=1):
                        print(f"STREAM_CHUNK_{idx}", chunk_text[:500], flush=True)
                    print("GEMINI_HTTP_STATUS", 200, flush=True)
                    print("FULL_STREAM_RESPONSE", full_stream_response[:1000], flush=True)
                    print("FINAL_RESPONSE_LENGTH", len(full_stream_response), flush=True)
                    print("GEMINI_RESPONSE_BODY", full_stream_response[:1000], flush=True)
                    if not meta.get("total_tokens"):
                        usage_dict = self._usage_dict(None, prompt, full_stream_response)
                        meta["prompt_tokens"] = usage_dict["prompt_tokens"]
                        meta["completion_tokens"] = usage_dict["completion_tokens"]
                        meta["total_tokens"] = usage_dict["total_tokens"]
                    return
                except Exception as exc:
                    self._print_gemini_exception(exc)
                    last_exc = exc
                    if collected:
                        raise RuntimeError(self._format_provider_error(exc)) from exc
                    continue
            raise RuntimeError(self._format_provider_error(last_exc or Exception("Unknown provider error")))

        return generator(), meta


llm_service = GeminiLLMService()
