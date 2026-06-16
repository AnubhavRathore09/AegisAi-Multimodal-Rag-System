from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]
STORAGE_DIR = BASE_DIR / "storage"
FAISS_DIR = STORAGE_DIR / "faiss"
UPLOAD_DIR = STORAGE_DIR / "uploads"
DATA_DIR = BASE_DIR / "data"

load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    app_name: str = "AegisAI"
    jwt_secret: str = os.getenv("JWT_SECRET", "aegisai-dev-secret").strip()
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256").strip()
    jwt_expiry_minutes: int = int(os.getenv("JWT_EXPIRY_MINUTES", "10080"))
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "").strip()
    gemini_base_url: str = os.getenv(
        "GEMINI_BASE_URL",
        "https://generativelanguage.googleapis.com/v1beta/openai/",
    ).strip()
    model_name: str = os.getenv("MODEL_NAME", "gemini-2.5-flash").strip()
    fallback_model_name: str = os.getenv("FALLBACK_MODEL_NAME", "").strip()
    router_model_name: str = os.getenv("ROUTER_MODEL_NAME", "").strip()
    summary_model_name: str = os.getenv("SUMMARY_MODEL_NAME", "").strip()
    transcription_model_name: str = os.getenv("TRANSCRIPTION_MODEL_NAME", "").strip()
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "").strip()
    tavily_max_results: int = int(os.getenv("TAVILY_MAX_RESULTS", "5"))
    web_search_timeout_seconds: float = float(os.getenv("WEB_SEARCH_TIMEOUT_SECONDS", "12"))
    mongodb_uri: str = os.getenv("MONGODB_URI") or os.getenv("MONGO_URI", "mongodb://localhost:27017")
    mongodb_db: str = os.getenv("MONGODB_DB") or os.getenv("MONGO_DB", "aegisai")
    redis_url: str = os.getenv("REDIS_URL", "").strip()
    cors_origins: list[str] = field(
        default_factory=lambda: [origin.strip() for origin in os.getenv("CORS_ORIGINS", "*").split(",") if origin.strip()]
    )
    tesseract_cmd: str = os.getenv("TESSERACT_CMD", "").strip()
    max_history_messages: int = int(os.getenv("MAX_HISTORY_MESSAGES", "8"))
    chunk_size: int = int(os.getenv("CHUNK_SIZE", "800"))
    chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", "100"))
    retrieval_k: int = int(os.getenv("RETRIEVAL_K", "3"))
    retrieval_min_score: float = float(os.getenv("RETRIEVAL_MIN_SCORE", "0.15"))
    hybrid_alpha: float = float(os.getenv("HYBRID_ALPHA", "0.65"))
    max_context_chars: int = int(os.getenv("MAX_CONTEXT_CHARS", "4000"))
    cache_ttl_seconds: int = int(os.getenv("CACHE_TTL_SECONDS", "900"))
    retrieval_cache_ttl_seconds: int = int(os.getenv("RETRIEVAL_CACHE_TTL_SECONDS", "600"))
    cache_max_items: int = int(os.getenv("CACHE_MAX_ITEMS", "256"))
    rate_limit_requests: int = int(os.getenv("RATE_LIMIT_REQUESTS", "10"))
    rate_limit_window_seconds: int = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
    router_use_llm: bool = os.getenv("ROUTER_USE_LLM", "true").strip().lower() in {"1", "true", "yes", "on"}
    router_llm_confidence_threshold: float = float(os.getenv("ROUTER_LLM_CONFIDENCE_THRESHOLD", "0.55"))
    llm_timeout_seconds: float = float(os.getenv("LLM_TIMEOUT_SECONDS", "60"))
    app_log_path: str = str(STORAGE_DIR / "app.log")
    stream_media_type: str = "text/event-stream"
    memory_summary_trigger_messages: int = int(os.getenv("MEMORY_SUMMARY_TRIGGER_MESSAGES", "8"))
    memory_summary_max_messages: int = int(os.getenv("MEMORY_SUMMARY_MAX_MESSAGES", "20"))
    long_term_memory_summaries: int = int(os.getenv("LONG_TERM_MEMORY_SUMMARIES", "4"))
    long_term_memory_char_limit: int = int(os.getenv("LONG_TERM_MEMORY_CHAR_LIMIT", "2000"))
    role_modes: list[str] = field(
        default_factory=lambda: ["assistant", "teacher", "researcher", "coder", "concise"]
    )
    prompt_templates: list[str] = field(
        default_factory=lambda: [
            "general_chat",
            "entity_lookup",
            "live_search",
            "document_qa",
        ]
    )


settings = Settings()

for path in (STORAGE_DIR, FAISS_DIR, UPLOAD_DIR, DATA_DIR):
    path.mkdir(parents=True, exist_ok=True)


PROMPT_FILE = BASE_DIR / "prompt.yaml"


class Config:
    DATA_DIR = str(DATA_DIR)
    STORAGE_DIR = str(STORAGE_DIR)
    VECTOR_DB_DIR = str(FAISS_DIR)
    UPLOAD_DIR = str(UPLOAD_DIR)
    MODEL_NAME = settings.model_name
    GEMINI_API_KEY = settings.gemini_api_key
    GEMINI_BASE_URL = settings.gemini_base_url
    EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
    MODEL_FALLBACK = settings.fallback_model_name

    def prompt(self, prompt_template: str) -> str:
        template = self._load_prompt(prompt_template)
        if template:
            return template
        return (
            "Assistant name: {bot_name}\n\n"
            "Question:\n{question}\n\n"
            "Context:\n{context}\n"
        )

    def _load_prompt(self, prompt_template: str) -> str:
        if not PROMPT_FILE.exists():
            return ""
        try:
            import yaml

            payload = yaml.safe_load(PROMPT_FILE.read_text(encoding="utf-8"))
        except Exception:
            return ""
        if not isinstance(payload, dict):
            return ""
        prompts = payload.get("prompts", payload)
        if not isinstance(prompts, dict):
            return ""
        template_aliases = {
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
        allowed_template = template_aliases.get(prompt_template, "general_chat")
        value = prompts.get(allowed_template) or prompts.get("general_chat")
        return str(value).strip() if value else ""
