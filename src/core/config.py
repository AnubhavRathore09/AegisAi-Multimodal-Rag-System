import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings:
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.7"))

    VISION_MODEL: str = os.getenv("VISION_MODEL", "llama-3.2-11b-vision-preview")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

    QDRANT_URL: str = os.getenv("QDRANT_URL", "")
    QDRANT_API_KEY: str = os.getenv("QDRANT_API_KEY", "")
    CODE_COLLECTION: str = os.getenv("QDRANT_CODE_COLLECTION", "codebase")
    DOCS_COLLECTION: str = os.getenv("QDRANT_DOCS_COLLECTION", "guidelines")

    MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
    MONGO_DB: str = os.getenv("MONGO_DB", "adaptive_rag")
    CHAT_COLLECTION: str = os.getenv("CHAT_COLLECTION", "chat_history")

    TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")

    RETRIEVAL_TOP_K: int = int(os.getenv("RETRIEVAL_TOP_K", "5"))
    SIMILARITY_THRESHOLD: float = float(os.getenv("SIMILARITY_THRESHOLD", "0.25"))
    CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "500"))
    CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "100"))
    MAX_HISTORY_MESSAGES: int = int(os.getenv("MAX_HISTORY_MESSAGES", "8"))

    ALLOWED_ORIGINS: list = os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:5500,http://localhost:5500,http://localhost:8080"
    ).split(",")

    PROMPTS_PATH: Path = BASE_DIR / "config" / "prompts.yaml"

    def validate(self):
        if not (self.GROQ_API_KEY or self.OPENAI_API_KEY):
            raise EnvironmentError("No LLM API key found")
        return self

settings = Settings().validate()

def get_settings():
    return settings
