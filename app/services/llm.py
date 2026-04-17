from __future__ import annotations

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass, field

from groq import Groq

from app.config import settings


BASE_SYSTEM_PROMPT = """You are Adaptive_RAG, a production assistant.

Rules:
- Answer the user's actual question directly.
- Do not use canned greetings unless the user is greeting you.
- If context is provided, use it only when it is relevant.
- If context is weak or irrelevant, answer from general knowledge instead of forcing the context.
- Return plain helpful text, not JSON.
- Prefer clear, calm, natural explanations.
- When evidence is weak, say so briefly instead of inventing facts.
"""

ROLE_INSTRUCTIONS = {
    "assistant": "Be balanced, practical, and conversational.",
    "teacher": "Teach clearly with simple explanations, small examples, and stepwise breakdowns.",
    "researcher": "Be evidence-driven, explicit about uncertainty, and concise with source-grounded claims.",
    "coder": "Be implementation-oriented, precise, and action-focused.",
    "concise": "Keep the answer short, direct, and low on fluff.",
}

TEMPLATE_INSTRUCTIONS = {
    "default": "Answer naturally in short readable paragraphs.",
    "summary": "Summarize the material in a compact, high-signal way.",
    "explain": "Explain the topic clearly, starting from the core idea.",
    "compare": "Compare the relevant options or concepts with direct contrasts.",
    "extract": "Extract the exact requested information before adding a short explanation.",
}


@dataclass
class CompletionResult:
    text: str
    model: str
    usage: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


class GroqService:
    def __init__(self) -> None:
        self.available = bool(settings.groq_api_key)
        self.client = Groq(api_key=settings.groq_api_key) if self.available else None

    def resolve_model(self, requested_model: str | None = None) -> str:
        candidate = (requested_model or settings.groq_model).strip()
        return candidate if candidate in settings.available_models else settings.groq_model

    def _estimate_tokens(self, *parts: str) -> int:
        return max(1, sum(len(part or "") for part in parts) // 4)

    def build_system_prompt(self, role_mode: str, prompt_template: str) -> str:
        role_text = ROLE_INSTRUCTIONS.get(role_mode, ROLE_INSTRUCTIONS["assistant"])
        template_text = TEMPLATE_INSTRUCTIONS.get(prompt_template, TEMPLATE_INSTRUCTIONS["default"])
        return f"{BASE_SYSTEM_PROMPT}\n\nRole mode: {role_text}\nPrompt template: {template_text}"

    def _build_messages(
        self,
        prompt: str,
        history: list[dict[str, str]] | None = None,
        role_mode: str = "assistant",
        prompt_template: str = "default",
    ) -> list[dict[str, str]]:
        messages = [{"role": "system", "content": self.build_system_prompt(role_mode, prompt_template)}]
        for item in (history or [])[-settings.max_history_messages :]:
            messages.append({"role": item["role"], "content": item["content"]})
        messages.append({"role": "user", "content": prompt})
        return messages

    def complete(
        self,
        prompt: str,
        history: list[dict[str, str]] | None = None,
        model: str | None = None,
        role_mode: str = "assistant",
        prompt_template: str = "default",
    ) -> CompletionResult:
        resolved_model = self.resolve_model(model)
        if not self.available or self.client is None:
            text = "The assistant is not configured yet. Set GROQ_API_KEY in .env to enable responses."
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

        try:
            response = self.client.chat.completions.create(
                model=resolved_model,
                messages=self._build_messages(prompt, history, role_mode, prompt_template),
                temperature=0.2,
                max_tokens=1024,
            )
            text = str(response.choices[0].message.content or "").strip()
            usage = getattr(response, "usage", None)
            usage_dict = {
                "prompt_tokens": int(getattr(usage, "prompt_tokens", self._estimate_tokens(prompt))),
                "completion_tokens": int(getattr(usage, "completion_tokens", self._estimate_tokens(text))),
            }
            usage_dict["total_tokens"] = usage_dict["prompt_tokens"] + usage_dict["completion_tokens"]
            return CompletionResult(text=text, model=resolved_model, usage=usage_dict)
        except Exception as exc:
            text = f"Unable to generate a response right now: {exc}"
            return CompletionResult(
                text=text,
                model=resolved_model,
                usage={
                    "prompt_tokens": self._estimate_tokens(prompt),
                    "completion_tokens": self._estimate_tokens(text),
                    "total_tokens": self._estimate_tokens(prompt, text),
                },
                warnings=["completion_error"],
            )

    async def complete_async(
        self,
        prompt: str,
        history: list[dict[str, str]] | None = None,
        model: str | None = None,
        role_mode: str = "assistant",
        prompt_template: str = "default",
    ) -> CompletionResult:
        return await asyncio.to_thread(
            self.complete,
            prompt,
            history,
            model,
            role_mode,
            prompt_template,
        )

    def stream(
        self,
        prompt: str,
        history: list[dict[str, str]] | None = None,
        model: str | None = None,
        role_mode: str = "assistant",
        prompt_template: str = "default",
    ) -> tuple[Iterable[str], dict[str, str | int | list[str]]]:
        resolved_model = self.resolve_model(model)
        meta: dict[str, str | int | list[str]] = {
            "model": resolved_model,
            "prompt_tokens": self._estimate_tokens(prompt),
            "warnings": [],
        }

        if not self.available or self.client is None:
            def disabled() -> Iterable[str]:
                yield "The assistant is not configured yet. Set GROQ_API_KEY in .env to enable responses."

            meta["warnings"] = ["missing_api_key"]
            return disabled(), meta

        def generator() -> Iterable[str]:
            try:
                stream = self.client.chat.completions.create(
                    model=resolved_model,
                    messages=self._build_messages(prompt, history, role_mode, prompt_template),
                    temperature=0.2,
                    max_tokens=1024,
                    stream=True,
                )
                for chunk in stream:
                    token = chunk.choices[0].delta.content or ""
                    if token:
                        yield str(token)
            except Exception as exc:
                meta["warnings"] = ["stream_error"]
                yield f"Unable to stream a response right now: {exc}"

        return generator(), meta

    async def stream_async(
        self,
        prompt: str,
        history: list[dict[str, str]] | None = None,
        model: str | None = None,
        role_mode: str = "assistant",
        prompt_template: str = "default",
    ) -> tuple[Iterable[str], dict[str, str | int | list[str]]]:
        return await asyncio.to_thread(
            self.stream,
            prompt,
            history,
            model,
            role_mode,
            prompt_template,
        )


llm_service = GroqService()
