from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
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
    groq_api_key: str = os.getenv("GROQ_API_KEY", "").strip()
    groq_model: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
    groq_vision_model: str = os.getenv(
        "GROQ_VISION_MODEL",
        "meta-llama/llama-4-scout-17b-16e-instruct",
    ).strip()
    groq_speech_model: str = os.getenv("GROQ_SPEECH_MODEL", "whisper-large-v3-turbo").strip()
    mongodb_uri: str = os.getenv("MONGODB_URI", "mongodb://localhost:27017").strip()
    mongodb_db: str = os.getenv("MONGODB_DB", "aegisai").strip()
    redis_url: str = os.getenv("REDIS_URL", "").strip()
    cors_origins: list[str] = field(
        default_factory=lambda: [origin.strip() for origin in os.getenv("CORS_ORIGINS", "*").split(",") if origin.strip()]
    )
    tesseract_cmd: str = os.getenv("TESSERACT_CMD", "").strip()
    max_history_messages: int = int(os.getenv("MAX_HISTORY_MESSAGES", "10"))
    chunk_size: int = int(os.getenv("CHUNK_SIZE", "900"))
    chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", "180"))
    retrieval_k: int = int(os.getenv("RETRIEVAL_K", "4"))
    retrieval_min_score: float = float(os.getenv("RETRIEVAL_MIN_SCORE", "0.15"))
    hybrid_alpha: float = float(os.getenv("HYBRID_ALPHA", "0.65"))
    max_context_chars: int = int(os.getenv("MAX_CONTEXT_CHARS", "5000"))
    cache_ttl_seconds: int = int(os.getenv("CACHE_TTL_SECONDS", "900"))
    retrieval_cache_ttl_seconds: int = int(os.getenv("RETRIEVAL_CACHE_TTL_SECONDS", "600"))
    cache_max_items: int = int(os.getenv("CACHE_MAX_ITEMS", "256"))
    rate_limit_requests: int = int(os.getenv("RATE_LIMIT_REQUESTS", "10"))
    rate_limit_window_seconds: int = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
    router_use_llm: bool = os.getenv("ROUTER_USE_LLM", "true").strip().lower() in {"1", "true", "yes", "on"}
    router_llm_confidence_threshold: float = float(os.getenv("ROUTER_LLM_CONFIDENCE_THRESHOLD", "0.55"))
    app_log_path: str = str(STORAGE_DIR / "app.log")
    stream_media_type: str = "text/event-stream"
    available_models: list[str] = field(
        default_factory=lambda: [
            model.strip()
            for model in os.getenv(
                "AVAILABLE_MODELS",
                "llama-3.3-70b-versatile,llama-3.1-8b-instant,meta-llama/llama-4-scout-17b-16e-instruct",
            ).split(",")
            if model.strip()
        ]
    )
    role_modes: list[str] = field(
        default_factory=lambda: ["assistant", "teacher", "researcher", "coder", "concise"]
    )
    prompt_templates: list[str] = field(
        default_factory=lambda: ["default", "summary", "explain", "compare", "extract"]
    )


settings = Settings()

for path in (STORAGE_DIR, FAISS_DIR, UPLOAD_DIR, DATA_DIR):
    path.mkdir(parents=True, exist_ok=True)
