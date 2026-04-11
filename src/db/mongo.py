from pymongo import MongoClient
from pymongo.collection import Collection
from src.core.settings import settings
from src.core.logger import get_logger

logger = get_logger(__name__)

_client = None


def get_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(
            settings.MONGO_URL,
            serverSelectionTimeoutMS=5000
        )
        logger.info(f"MongoDB connected to {settings.MONGO_URL}")
    return _client


def get_db():
    return get_client()[settings.MONGO_DB]


def get_docs_collection() -> Collection:
    return get_db()[settings.DOCS_COLLECTION]


def get_chat_collection() -> Collection:
    return get_db()[settings.CHAT_COLLECTION]
