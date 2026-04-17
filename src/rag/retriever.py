import os
from typing import Any

import numpy as np

try:
    import faiss  # type: ignore
except Exception:
    faiss = None

from src.services.embedding import get_embedding_cached
from src.db.mongo import get_docs_collection
from src.core.logger import get_logger

logger = get_logger(__name__)

index = None
doc_store: list[dict[str, Any]] = []
embeddings_matrix = np.empty((0, 0), dtype="float32")


def _new_index(dimension: int):
    if faiss is None:
        return None
    return faiss.IndexFlatL2(dimension)


def _safe_vector(value) -> np.ndarray:
    arr = np.array(value, dtype="float32")
    if arr.ndim == 1:
        return arr
    return arr.reshape(-1).astype("float32")


def load_faiss_index():
    global index, doc_store, embeddings_matrix
    try:
        if (
            faiss is not None
            and os.path.exists("vector_db/index.faiss")
            and os.path.exists("vector_db/docs.npy")
        ):
            index = faiss.read_index("vector_db/index.faiss")
            raw_docs = np.load("vector_db/docs.npy", allow_pickle=True).tolist()
            doc_store = [
                item if isinstance(item, dict) else {"text": str(item), "source": "local"}
                for item in raw_docs
            ]
            embeddings_matrix = np.empty((0, 0), dtype="float32")
            return

        index = _new_index(768)
        doc_store = []
        embeddings_matrix = np.empty((0, 0), dtype="float32")
    except Exception as e:
        logger.error(f"Retriever load error: {str(e)}")
        index = _new_index(768)
        doc_store = []
        embeddings_matrix = np.empty((0, 0), dtype="float32")


def sync_from_mongo():
    global index, doc_store, embeddings_matrix
    try:
        docs = list(get_docs_collection().find({}, {"_id": 0}))
        if not docs:
            doc_store = []
            embeddings_matrix = np.empty((0, 0), dtype="float32")
            index = _new_index(768)
            return

        normalized_docs = []
        vectors = []
        for doc in docs:
            text = str(doc.get("text", "") or "").strip()
            if not text:
                continue
            emb = _safe_vector(doc.get("embedding") or get_embedding_cached(text))
            normalized_docs.append(
                {
                    "text": text,
                    "source": doc.get("source", "document"),
                    "file_hash": doc.get("file_hash"),
                }
            )
            vectors.append(emb)

        if not vectors:
            doc_store = []
            embeddings_matrix = np.empty((0, 0), dtype="float32")
            index = _new_index(768)
            return

        embeddings_matrix = np.vstack(vectors).astype("float32")
        doc_store = normalized_docs

        if faiss is not None:
            index = _new_index(embeddings_matrix.shape[1])
            index.add(embeddings_matrix)
        else:
            index = None

    except Exception as e:
        logger.error(f"Mongo sync error: {str(e)}")


def retrieve_documents(query, k=3):
    try:
        if not query or not doc_store:
            return []

        query_embedding = _safe_vector(get_embedding_cached(query))
        sample_k = min(max(k, 1), len(doc_store))

        if faiss is not None and index is not None:
            distances, indices = index.search(np.array([query_embedding]).astype("float32"), sample_k)
            ordered = indices[0]
            scores = distances[0]
        else:
            if embeddings_matrix.size == 0:
                return []
            diffs = embeddings_matrix - query_embedding
            scores = np.linalg.norm(diffs, axis=1)
            ordered = np.argsort(scores)[:sample_k]

        results = []
        for pos, idx in enumerate(ordered):
            idx = int(idx)
            if idx < 0 or idx >= len(doc_store):
                continue
            item = dict(doc_store[idx])
            item["score"] = float(scores[pos] if pos < len(scores) else 0.0)
            results.append(item)

        return results

    except Exception as e:
        logger.error(f"Retriever error: {str(e)}")
        return []


def build_context_with_citations(docs):
    if not docs:
        return "", []

    context_parts = []
    sources = []
    for doc in docs:
        text = str(doc.get("text", "") or "").strip()
        source = str(doc.get("source", "document") or "document")
        if text:
            context_parts.append(f"Source: {source}\n{text}")
            sources.append(source)

    return "\n\n".join(context_parts), sources


def get_all_sources():
    try:
        docs = list(get_docs_collection().find({}, {"_id": 0, "source": 1}))
        seen = []
        for doc in docs:
            source = str(doc.get("source", "") or "").strip()
            if source and source not in seen:
                seen.append(source)
        return seen
    except Exception as e:
        logger.error(f"Get sources error: {str(e)}")
        return []
