from __future__ import annotations

import hashlib
import json
import re
import threading
from collections import Counter
from typing import Any

import numpy as np

from src.config import FAISS_DIR, settings

try:
    import faiss  # type: ignore
except Exception:
    faiss = None


class FaissDocumentStore:
    def __init__(self) -> None:
        self.dimension = 1024
        self.index_path = FAISS_DIR / "documents.faiss"
        self.meta_path = FAISS_DIR / "documents.json"
        self.vectors_path = FAISS_DIR / "vectors.npy"
        self.lock = threading.Lock()
        self.index = faiss.IndexFlatIP(self.dimension) if faiss is not None else None
        self.documents: list[dict[str, Any]] = []
        self.vectors = np.empty((0, self.dimension), dtype="float32")
        self._load()

    def _load(self) -> None:
        if faiss is not None and self.index is not None and self.index_path.exists():
            self.index = faiss.read_index(str(self.index_path))
        if self.meta_path.exists():
            self.documents = json.loads(self.meta_path.read_text(encoding="utf-8"))
        if self.vectors_path.exists():
            self.vectors = np.load(self.vectors_path).astype("float32")

    def _save(self) -> None:
        if faiss is not None and self.index is not None:
            faiss.write_index(self.index, str(self.index_path))
        np.save(self.vectors_path, self.vectors)
        self.meta_path.write_text(json.dumps(self.documents, indent=2), encoding="utf-8")

    def _tokenize(self, text: str) -> list[str]:
        words = re.findall(r"\b\w+\b", text.lower())
        bigrams = [f"{words[idx]}_{words[idx + 1]}" for idx in range(len(words) - 1)]
        return words + bigrams

    def _embed_one(self, text: str) -> np.ndarray:
        vector = np.zeros(self.dimension, dtype="float32")
        tokens = self._tokenize(text)
        if not tokens:
            return vector

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
            index = int(digest[:8], 16) % self.dimension
            vector[index] += 1.0

        norm = np.linalg.norm(vector)
        if norm > 0:
            vector /= norm
        return vector

    def _keyword_score(self, query: str, text: str) -> float:
        query_terms = self._tokenize(query)
        doc_terms = self._tokenize(text)
        if not query_terms or not doc_terms:
            return 0.0
        query_counts = Counter(query_terms)
        doc_counts = Counter(doc_terms)
        overlap = sum(min(query_counts[token], doc_counts[token]) for token in query_counts)
        normalizer = max(len(set(query_terms)), 1)
        return float(overlap) / float(normalizer)

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self.dimension), dtype="float32")
        return np.vstack([self._embed_one(text) for text in texts]).astype("float32")

    def add_documents(self, docs: list[dict[str, Any]]) -> int:
        clean_docs = [doc for doc in docs if str(doc.get("text", "")).strip()]
        if not clean_docs:
            return 0

        vectors = self.embed([str(doc["text"]) for doc in clean_docs])

        with self.lock:
            if faiss is not None and self.index is not None:
                self.index.add(vectors)
            self.vectors = np.vstack([self.vectors, vectors])
            self.documents.extend(clean_docs)
            self._save()

        return len(clean_docs)

    def _visible_doc_indices(self, user_id: str | None) -> list[int]:
        visible: list[int] = []
        for idx, document in enumerate(self.documents):
            owner = str(document.get("user_id", "")).strip()
            if not owner or owner == str(user_id or "").strip():
                visible.append(idx)
        return visible

    def search(
        self,
        query: str,
        k: int | None = None,
        use_hybrid: bool = True,
        user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        if not query.strip():
            return []

        k = k or settings.retrieval_k
        with self.lock:
            if not self.documents or self.vectors.size == 0:
                return []
            visible_indices = self._visible_doc_indices(user_id)
            if not visible_indices:
                return []
            query_vector = self.embed([query])
            visible_vectors = self.vectors[visible_indices]
            similarities = np.dot(visible_vectors, query_vector[0])
            sample_k = min(max(k * 3, k), len(visible_indices))
            top_positions = np.argsort(similarities)[::-1][:sample_k]
            scores = np.array([[similarities[idx] for idx in top_positions]], dtype="float32")
            indices = np.array([[visible_indices[idx] for idx in top_positions]], dtype="int64")

        matches: list[dict[str, Any]] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self.documents):
                continue
            dense_score = float(score)
            lexical_score = self._keyword_score(query, str(self.documents[idx].get("text", "")))
            combined_score = (
                settings.hybrid_alpha * dense_score + (1.0 - settings.hybrid_alpha) * lexical_score
                if use_hybrid
                else dense_score
            )
            if combined_score < settings.retrieval_min_score:
                continue
            item = dict(self.documents[idx])
            item["score"] = round(combined_score, 4)
            item["dense_score"] = round(dense_score, 4)
            item["lexical_score"] = round(lexical_score, 4)
            matches.append(item)
        matches.sort(key=lambda item: float(item.get("score", 0.0)), reverse=True)
        return matches[:k]


vector_store = FaissDocumentStore()
