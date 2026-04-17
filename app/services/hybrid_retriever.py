from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Any

from app.config import settings
from app.services.vector_store import vector_store


class HybridRetriever:
    def _tokenize(self, text: str) -> list[str]:
        return re.findall(r"\b\w+\b", str(text or "").lower())

    def _bm25(self, query: str, documents: list[dict[str, Any]]) -> dict[int, float]:
        query_terms = self._tokenize(query)
        if not query_terms or not documents:
            return {}

        doc_terms = [self._tokenize(doc.get("text", "")) for doc in documents]
        avgdl = sum(len(terms) for terms in doc_terms) / max(len(doc_terms), 1)
        frequencies = [Counter(terms) for terms in doc_terms]
        doc_freq = defaultdict(int)
        for terms in doc_terms:
            for token in set(terms):
                doc_freq[token] += 1

        k1 = 1.5
        b = 0.75
        scores: dict[int, float] = {}
        total_docs = len(documents)
        for idx, freq in enumerate(frequencies):
            score = 0.0
            doc_len = len(doc_terms[idx]) or 1
            for token in query_terms:
                term_freq = freq.get(token, 0)
                if term_freq == 0:
                    continue
                inverse_doc_freq = math.log(1 + (total_docs - doc_freq[token] + 0.5) / (doc_freq[token] + 0.5))
                numerator = term_freq * (k1 + 1)
                denominator = term_freq + k1 * (1 - b + b * (doc_len / max(avgdl, 1.0)))
                score += inverse_doc_freq * (numerator / denominator)
            if score > 0:
                scores[idx] = score
        return scores

    def _rerank(self, query: str, docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        query_tokens = set(self._tokenize(query))
        reranked: list[dict[str, Any]] = []
        for item in docs:
            text_tokens = set(self._tokenize(item.get("text", "")))
            overlap = len(query_tokens & text_tokens) / max(len(query_tokens), 1)
            rerank_score = round(0.8 * float(item.get("score", 0.0)) + 0.2 * overlap, 4)
            updated = dict(item)
            updated["rerank_score"] = rerank_score
            reranked.append(updated)
        reranked.sort(key=lambda entry: float(entry.get("rerank_score", entry.get("score", 0.0))), reverse=True)
        return reranked[: settings.retrieval_k]

    def search(self, query: str, k: int | None = None, user_id: str | None = None) -> list[dict[str, Any]]:
        k = k or settings.retrieval_k
        dense_matches = vector_store.search(query, max(k * 3, k), use_hybrid=False, user_id=user_id)
        if not dense_matches:
            return []

        bm25_scores = self._bm25(query, dense_matches)
        merged: list[dict[str, Any]] = []
        for idx, item in enumerate(dense_matches):
            dense_score = float(item.get("dense_score", item.get("score", 0.0)))
            bm25_score = float(bm25_scores.get(idx, item.get("lexical_score", 0.0)))
            final_score = settings.hybrid_alpha * dense_score + (1.0 - settings.hybrid_alpha) * bm25_score
            merged_item = dict(item)
            merged_item["dense_score"] = round(dense_score, 4)
            merged_item["bm25_score"] = round(bm25_score, 4)
            merged_item["lexical_score"] = round(bm25_score, 4)
            merged_item["score"] = round(final_score, 4)
            merged.append(merged_item)

        merged.sort(key=lambda entry: float(entry.get("score", 0.0)), reverse=True)
        return self._rerank(query, merged[: max(k * 2, k)])


hybrid_retriever = HybridRetriever()
