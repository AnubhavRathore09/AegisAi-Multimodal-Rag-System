from __future__ import annotations

import asyncio

from fastapi import HTTPException
from groq import Groq

from app.config import settings


class SpeechService:
    def __init__(self) -> None:
        self.available = bool(settings.groq_api_key)
        self.client = Groq(api_key=settings.groq_api_key) if self.available else None

    def transcribe(self, filename: str, content: bytes, language: str | None = None) -> str:
        if not self.available or self.client is None:
            raise HTTPException(status_code=503, detail="Voice transcription is not configured.")
        if not content:
            raise HTTPException(status_code=400, detail="Empty audio upload.")

        try:
            response = self.client.audio.transcriptions.create(
                model=settings.groq_speech_model,
                file=(filename or "voice.webm", content),
                language=(language or "").strip() or None,
                response_format="json",
                temperature=0.0,
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Voice transcription failed: {exc}") from exc

        text = str(getattr(response, "text", "") or "").strip()
        if not text:
            raise HTTPException(status_code=422, detail="No speech was detected in the audio.")
        return text

    async def transcribe_async(self, filename: str, content: bytes, language: str | None = None) -> str:
        return await asyncio.to_thread(self.transcribe, filename, content, language)


speech_service = SpeechService()
