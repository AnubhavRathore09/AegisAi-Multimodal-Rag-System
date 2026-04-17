from typing import List
from pydantic import BaseModel, Field


class ImagePayload(BaseModel):
    data: str
    mime_type: str = "image/jpeg"
    filename: str = "image"


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1)
    chat_id: str = "default"
    user: str = "User"
    images: List[ImagePayload] = []
