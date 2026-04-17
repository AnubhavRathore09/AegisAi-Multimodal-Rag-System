from __future__ import annotations

import asyncio
import io

import numpy as np
from PIL import Image, ImageOps

from src.config import settings


def _preprocess_image(image_bytes: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    image = ImageOps.exif_transpose(image)
    image = ImageOps.autocontrast(image)
    try:
        import cv2  # type: ignore

        array = np.array(image)
        gray = cv2.cvtColor(array, cv2.COLOR_RGB2GRAY)
        blur = cv2.GaussianBlur(gray, (3, 3), 0)
        processed = cv2.adaptiveThreshold(
            blur,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            11,
        )
        return Image.fromarray(processed)
    except Exception:
        return ImageOps.grayscale(image)


def _easyocr_text(image: Image.Image) -> str:
    try:
        import easyocr  # type: ignore
    except ModuleNotFoundError:
        return ""
    try:
        reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        lines = reader.readtext(np.array(image), detail=0, paragraph=True)
        return " ".join(str(line).strip() for line in lines if str(line).strip()).strip()
    except Exception:
        return ""


def _tesseract_text(image: Image.Image) -> str:
    try:
        import pytesseract
    except ModuleNotFoundError:
        return ""
    if settings.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd
    text = pytesseract.image_to_string(image) or ""
    return " ".join(text.split()).strip()


def extract_text_from_image_bytes(image_bytes: bytes) -> str:
    image = _preprocess_image(image_bytes)
    text = _easyocr_text(image)
    if text:
        return text
    text = _tesseract_text(image)
    if text:
        return text
    return ""


async def extract_text_from_image_bytes_async(image_bytes: bytes) -> str:
    return await asyncio.to_thread(extract_text_from_image_bytes, image_bytes)
