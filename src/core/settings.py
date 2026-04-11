from pydantic import BaseSettings

class Settings(BaseSettings):
    MONGO_URL: str
    MONGO_DB: str = "adaptive_rag"
    DOCS_COLLECTION: str = "documents"
    CHAT_COLLECTION: str = "chat_history"

    class Config:
        env_file = ".env"

settings = Settings()
