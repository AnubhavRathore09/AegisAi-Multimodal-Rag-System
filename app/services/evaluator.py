from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.llm import llm_service
from app.services.vector_store import vector_store


def _tokenize(text: str) -> set[str]:
    return {token for token in re.findall(r"\b\w+\b", (text or "").lower()) if token}


def _overlap(a: str, b: str) -> float:
    left = _tokenize(a)
    right = _tokenize(b)
    if not left or not right:
        return 0.0
    return len(left & right) / max(len(left | right), 1)


def _cosine_similarity(a: str, b: str) -> float:
    if not a.strip() or not b.strip():
        return 0.0
    vectors = vector_store.embed([a, b])
    if len(vectors) != 2:
        return 0.0
    value = float(vectors[0] @ vectors[1])
    return max(0.0, min(1.0, value))


@dataclass
class EvaluationSample:
    query: str
    retrieved_docs: list[str]
    answer: str
    reference_answer: str = ""
    reference_docs: list[str] | None = None


@dataclass
class EvaluationResult:
    accuracy: float
    response_similarity: float
    precision: float
    recall: float
    context_relevance: float
    answer_correctness: float
    avg_score: float
    details: dict


class RAGEvaluator:
    async def _llm_correctness(self, sample: EvaluationSample) -> float:
        if not llm_service.available or not sample.reference_answer.strip():
            return max(_overlap(sample.answer, sample.reference_answer), _cosine_similarity(sample.answer, sample.reference_answer))

        prompt = f'''Score the candidate answer against the reference answer from 0 to 1.
Return only a number.

Question: {sample.query}
Reference answer: {sample.reference_answer}
Candidate answer: {sample.answer}
'''
        try:
            result = await llm_service.complete_async(
                prompt,
                role_mode="researcher",
                prompt_template="extract",
            )
            value = float(re.findall(r"\d+(?:\.\d+)?", result.text)[0])
            return max(0.0, min(1.0, value))
        except Exception:
            return max(_overlap(sample.answer, sample.reference_answer), _cosine_similarity(sample.answer, sample.reference_answer))

    async def evaluate_sample(self, sample: EvaluationSample) -> EvaluationResult:
        retrieved = sample.retrieved_docs or []
        reference_docs = sample.reference_docs or []

        precision_hits = [doc for doc in retrieved if max(_overlap(doc, ref) for ref in reference_docs or [sample.reference_answer or sample.query]) >= 0.15]
        recall_hits = [doc for doc in reference_docs if max(_overlap(doc, ret) for ret in retrieved or [sample.answer or sample.query]) >= 0.15]

        precision = len(precision_hits) / max(len(retrieved), 1)
        recall = len(recall_hits) / max(len(reference_docs), 1) if reference_docs else precision
        context_relevance = sum(max(_overlap(sample.query, doc), _cosine_similarity(sample.query, doc)) for doc in retrieved) / len(retrieved) if retrieved else 0.0
        response_similarity = max(_overlap(sample.answer, sample.reference_answer), _cosine_similarity(sample.answer, sample.reference_answer))
        answer_correctness = await self._llm_correctness(sample)
        accuracy = 1.0 if answer_correctness >= 0.7 else 0.0
        avg_score = (response_similarity + context_relevance + answer_correctness) / 3.0

        return EvaluationResult(
            accuracy=round(accuracy, 4),
            response_similarity=round(response_similarity, 4),
            precision=round(precision, 4),
            recall=round(recall, 4),
            context_relevance=round(context_relevance, 4),
            answer_correctness=round(answer_correctness, 4),
            avg_score=round(avg_score, 4),
            details={
                "query": sample.query,
                "retrieved_count": len(retrieved),
                "reference_count": len(reference_docs),
                "expected": sample.reference_answer,
                "answer": sample.answer,
            },
        )

    async def evaluate_batch(self, samples: list[EvaluationSample]) -> dict:
        results = [await self.evaluate_sample(sample) for sample in samples]
        if not results:
            return {"results": [], "summary": {}}

        summary = {
            "accuracy": round(sum(item.accuracy for item in results) / len(results), 4),
            "avg_score": round(sum(item.avg_score for item in results) / len(results), 4),
            "response_similarity": round(sum(item.response_similarity for item in results) / len(results), 4),
            "precision": round(sum(item.precision for item in results) / len(results), 4),
            "recall": round(sum(item.recall for item in results) / len(results), 4),
            "context_relevance": round(sum(item.context_relevance for item in results) / len(results), 4),
            "answer_correctness": round(sum(item.answer_correctness for item in results) / len(results), 4),
        }
        return {
            "results": [
                {
                    "accuracy": item.accuracy,
                    "avg_score": item.avg_score,
                    "response_similarity": item.response_similarity,
                    "precision": item.precision,
                    "recall": item.recall,
                    "context_relevance": item.context_relevance,
                    "answer_correctness": item.answer_correctness,
                    "details": item.details,
                }
                for item in results
            ],
            "summary": summary,
        }


rag_evaluator = RAGEvaluator()
