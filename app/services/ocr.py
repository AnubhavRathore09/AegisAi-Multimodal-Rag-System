from __future__ import annotations

import asyncio
import io

from PIL import Image

from app.config import settings


def extract_text_from_image_bytes(image_bytes: bytes) -> str:
    try:
        import pytesseract
    except ModuleNotFoundError:
        return ""

    if settings.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd

    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    text = pytesseract.image_to_string(image) or ""
    return " ".join(text.split()).strip()


async def extract_text_from_image_bytes_async(image_bytes: bytes) -> str:
    return await asyncio.to_thread(extract_text_from_image_bytes, image_bytes)
