from src.config import DATA_DIR, FAISS_DIR, STORAGE_DIR, UPLOAD_DIR, Settings, settings

class Config:
    DATA_DIR = str(DATA_DIR)
    STORAGE_DIR = str(STORAGE_DIR)
    VECTOR_DB_DIR = str(FAISS_DIR)
    UPLOAD_DIR = str(UPLOAD_DIR)
    MODEL_NAME = settings.groq_model
    EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
    OPENAI_API_KEY = ""
    GROQ_API_KEY = settings.groq_api_key
