from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.1-8b-instant"
    LLM_TEMPERATURE: float = 0.7
    VISION_MODEL: str = "llama-3.2-11b-vision-preview"
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    MONGO_URL: str = Field(
        default="mongodb://localhost:27017/",
        validation_alias=AliasChoices("MONGO_URL", "MONGO_URI"),
    )
    MONGO_DB: str = "adaptive_rag"
    DOCS_COLLECTION: str = "documents"
    CHAT_COLLECTION: str = "chat_history"
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 100
    MAX_HISTORY_MESSAGES: int = 8

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
