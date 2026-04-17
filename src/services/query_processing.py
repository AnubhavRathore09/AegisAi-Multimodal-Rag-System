from __future__ import annotations

import re
from difflib import SequenceMatcher

from src.services.llm import llm_service


ENTITY_ALIASES = {
    "naredar mudi": "Narendra Modi",
    "narendar mudi": "Narendra Modi",
    "narendra mudi": "Narendra Modi",
    "narendar modi": "Narendra Modi",
    "modiji": "Narendra Modi",
    "solman khen": "Salman Khan",
    "salman khen": "Salman Khan",
    "solman khan": "Salman Khan",
    "salmaan khan": "Salman Khan",
    "sallman khan": "Salman Khan",
    "sharukh khan": "Shah Rukh Khan",
    "shahruk khan": "Shah Rukh Khan",
    "srk": "Shah Rukh Khan",
}

KNOWN_ENTITIES = (
    "Narendra Modi",
    "Salman Khan",
    "Shah Rukh Khan",
    "Amitabh Bachchan",
    "Virat Kohli",
    "Sachin Tendulkar",
    "Elon Musk",
    "Bill Gates",
    "Sundar Pichai",
)

CREATIVE_PREFIXES = (
    "tell me a story",
    "write a story",
    "tell a story",
    "write a poem",
    "generate",
    "create",
    "draft",
)

EXPLANATION_PREFIXES = (
    "what is ",
    "who is ",
    "tell me about ",
    "explain ",
    "define ",
)


def normalize_query(query: str) -> str:
    return re.sub(r"\s+", " ", (query or "").strip())


def looks_creative(query: str) -> bool:
    lowered = normalize_query(query).lower()
    return any(lowered.startswith(prefix) for prefix in CREATIVE_PREFIXES)


def apply_alias_corrections(query: str) -> str:
    updated = normalize_query(query)
    lowered = updated.lower()
    for alias, canonical in ENTITY_ALIASES.items():
        if alias in lowered:
            pattern = re.compile(re.escape(alias), re.IGNORECASE)
            updated = pattern.sub(canonical, updated)
            lowered = updated.lower()
    return updated


def normalize_entity_text(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", text.lower()).strip()


def replace_fuzzy_entity_spans(query: str) -> str:
    words = query.split()
    if not words:
        return query

    updated = words[:]

    for entity in KNOWN_ENTITIES:
        entity_words = entity.split()
        span_length = len(entity_words)
        normalized_entity = normalize_entity_text(entity)

        best_ratio = 0.0
        best_start = -1
        for start in range(0, len(updated) - span_length + 1):
            candidate_words = updated[start : start + span_length]
            candidate = " ".join(candidate_words)
            normalized_candidate = normalize_entity_text(candidate)
            ratio = SequenceMatcher(None, normalized_candidate, normalized_entity).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_start = start

        if best_start >= 0 and best_ratio >= 0.74:
            candidate = " ".join(updated[best_start : best_start + span_length])
            if normalize_entity_text(candidate) != normalized_entity:
                updated[best_start : best_start + span_length] = entity_words

    return " ".join(updated)


def safe_llm_correction(query: str) -> str:
    if looks_creative(query):
        return query

    prompt = f"""Correct only obvious spelling mistakes in this user query.

Rules:
- Preserve the user's original intent.
- Do not expand, summarize, or rewrite the query.
- If the query is already acceptable, return it unchanged.
- Return only the corrected query.

Query: {query}
"""

    result = llm_service.complete(prompt)
    candidate = normalize_query(result.text)
    original = normalize_query(query)

    if not candidate:
        return original
    if candidate.lower().startswith("the assistant is not configured"):
        return original
    if abs(len(candidate.split()) - len(original.split())) > 1:
        return original

    similarity = SequenceMatcher(None, original.lower(), candidate.lower()).ratio()
    return candidate if similarity >= 0.68 else original


def expand_query(query: str) -> str:
    original = normalize_query(query)
    lowered = original.lower()

    if looks_creative(original):
        return original

    if lowered.startswith("what is "):
        subject = original[8:].strip().rstrip("?.!")
        if subject and len(subject.split()) <= 6:
            return f"Explain what {subject} is in detail."

    if lowered.startswith("who is "):
        subject = original[7:].strip().rstrip("?.!")
        if subject and len(subject.split()) <= 6:
            return f"Explain who {subject} is with the most important background details."

    if lowered.startswith("tell me about "):
        subject = original[14:].strip().rstrip("?.!")
        if subject and len(subject.split()) <= 8:
            return f"Tell me about {subject} in a clear and detailed way."

    if lowered.startswith("define "):
        subject = original[7:].strip().rstrip("?.!")
        if subject:
            return f"Define {subject} clearly and explain the main idea."

    if len(original.split()) <= 3 and any(lowered.startswith(prefix) for prefix in EXPLANATION_PREFIXES):
        return f"Answer this clearly and directly: {original}"

    return original


def correct_query(query: str) -> tuple[str, str | None]:
    original = normalize_query(query)
    if not original:
        return "", None

    alias_corrected = apply_alias_corrections(original)
    fuzzy_corrected = replace_fuzzy_entity_spans(alias_corrected)
    final = safe_llm_correction(fuzzy_corrected)
    if final == original:
        return original, None
    return final, final
