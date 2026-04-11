from functools import lru_cache
from sentence_transformers import SentenceTransformer
from src.core.config import settings
from src.core.logger import get_logger

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def _model() -> SentenceTransformer:
    logger.info("Loading embedding model: %s", settings.EMBEDDING_MODEL)
    return SentenceTransformer(settings.EMBEDDING_MODEL)


def get_embedding(text: str) -> list[float]:
    return _model().encode(text, show_progress_bar=False).tolist()


@lru_cache(maxsize=1000)
def get_embedding_cached(text: str):
    return tuple(get_embedding(text))
