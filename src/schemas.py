from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class UploadedAttachment(BaseModel):
    upload_id: str | None = None
    filename: str
    content_type: str = "application/octet-stream"
    kind: Literal["document", "image"] = "document"
    extracted_text: str = ""


class UploadedImage(BaseModel):
    data: str
    mime_type: str = "image/png"
    filename: str = "image.png"


class ChatRequest(BaseModel):
    query: str = Field(default="", max_length=8000)
    session_id: str = Field(default="default", max_length=200)
    chat_id: str | None = Field(default=None, max_length=200)
    attachments: list[UploadedAttachment] = Field(default_factory=list)
    images: list[UploadedImage] = Field(default_factory=list)
    force_rag: bool = False
    role_mode: str = Field(default="assistant", max_length=40)
    model: str | None = Field(default=None, max_length=120)
    prompt_template: str = Field(default="default", max_length=40)
    use_hybrid_search: bool = True
    debug: bool = False


class AuthUser(BaseModel):
    id: str
    name: str
    email: str
    bot_name: str = "Aegis AI"


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=3, max_length=200)


class SignupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=6, max_length=200)


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: AuthUser


class ChatResponse(BaseModel):
    response: str
    corrected_query: str | None = None
    sources: list[dict] = Field(default_factory=list)
    citations: list[dict] = Field(default_factory=list)
    used_rag: bool = False
    route: str = "direct"
    session_id: str = "default"
    model: str = ""
    role_mode: str = "assistant"
    prompt_template: str = "default"
    usage: dict = Field(default_factory=dict)
    retrieval: dict = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    debug: dict = Field(default_factory=dict)


class UploadResponse(BaseModel):
    upload_id: str
    kind: Literal["document", "image"]
    filename: str
    extracted_text: str = ""
    chunks_indexed: int = 0
    chunks: int = 0
    message: str
    processing: dict = Field(default_factory=dict)


class EvaluationSamplePayload(BaseModel):
    query: str
    retrieved_docs: list[str] = Field(default_factory=list)
    answer: str = ""
    expected: str = ""
    reference_docs: list[str] = Field(default_factory=list)


class BatchEvaluationRequest(BaseModel):
    samples: list[EvaluationSamplePayload] = Field(default_factory=list)
