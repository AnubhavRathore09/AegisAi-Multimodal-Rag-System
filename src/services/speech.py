from __future__ import annotations

import asyncio
import io

from fastapi import HTTPException
from openai import OpenAI

from src.config import settings
from src.services.logging_service import app_logger


class SpeechService:
    def __init__(self) -> None:
        self.available = bool(settings.gemini_api_key and settings.transcription_model_name)
        self.client = (
            OpenAI(
                api_key=settings.gemini_api_key,
                base_url=settings.gemini_base_url,
                timeout=settings.llm_timeout_seconds,
                default_headers={
                    "X-Title": settings.app_name,
                },
            )
            if self.available
            else None
        )

    def transcribe(self, filename: str, content: bytes, language: str | None = None) -> str:
        if not self.available or self.client is None:
            raise HTTPException(
                status_code=503,
                detail="Voice transcription is not configured. Set GEMINI_API_KEY and TRANSCRIPTION_MODEL_NAME in .env.",
            )
        if not content:
            raise HTTPException(status_code=400, detail="Empty audio upload.")

        try:
            print("TRANSCRIPTION_START", filename or "voice.webm", flush=True)
            print("AUDIO_RECEIVED", len(content), flush=True)
            try:
                app_logger.log("AUDIO_RECEIVED", filename=filename or "voice.webm", bytes=len(content))
            except Exception:
                pass
            file_like = io.BytesIO(content)
            file_like.name = filename or "voice.webm"
            response = self.client.audio.transcriptions.create(
                model=settings.transcription_model_name,
                file=file_like,
                language=(language or "").strip() or None,
            )
        except Exception as exc:
            print("TRANSCRIPTION_FAILED", repr(exc), flush=True)
            try:
                app_logger.log("TRANSCRIPTION_FAILED", filename=filename or "voice.webm", error=str(exc))
            except Exception:
                pass
            raise HTTPException(status_code=502, detail=f"Voice transcription failed: {exc}") from exc

        text = str(getattr(response, "text", "") or "").strip()
        if not text:
            print("TRANSCRIPTION_FAILED", "no_speech", flush=True)
            try:
                app_logger.log("TRANSCRIPTION_FAILED", filename=filename or "voice.webm", error="no_speech")
            except Exception:
                pass
            raise HTTPException(status_code=422, detail="No speech detected.")
        print("TRANSCRIPTION_SUCCESS", len(text), flush=True)
        try:
            app_logger.log("TRANSCRIPTION_SUCCESS", filename=filename or "voice.webm", chars=len(text))
        except Exception:
            pass
        return text

    async def transcribe_async(self, filename: str, content: bytes, language: str | None = None) -> str:
        return await asyncio.to_thread(self.transcribe, filename, content, language)


speech_service = SpeechService()
