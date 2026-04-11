from typing import List
from src.rag.retriever import retrieve_documents, build_context_with_citations
from src.llms.groq_client import get_llm_response, analyze_image
from src.memory.chat_history_mongo import get_history_as_messages, save_message
from src.core.logger import get_logger

logger = get_logger(__name__)


def _rewrite_query(query: str, history: List[dict]) -> str:
    if not history or len(query.split()) > 8:
        return query

    history_text = "\n".join(f"{m['role']}: {m['content']}" for m in history[-4:])

    prompt = f"""
Given this conversation:
{history_text}

Rewrite this question to be self-contained:
{query}

Only output rewritten question.
"""

    try:
        rewritten = get_llm_response(prompt).strip()
        if rewritten and len(rewritten) < 300:
            return rewritten
    except Exception:
        pass

    return query


def run_rag(query: str, chat_id: str = "default", images: List = None) -> dict:
    try:
        history = get_history_as_messages(chat_id)

        image_context = ""
        if images:
            results = []
            for img in images:
                try:
                    desc = analyze_image(
                        img.get("data", ""),
                        img.get("mime_type", "image/jpeg"),
                        query or "Describe this image"
                    )
                    if desc:
                        results.append(desc)
                except Exception:
                    continue

            if results:
                image_context = "\n\n".join(results)

        effective_query = _rewrite_query(query, history) if history else query

        docs = retrieve_documents(effective_query)
        context, sources = build_context_with_citations(docs)

        prompt_parts = []

        if image_context:
            prompt_parts.append(f"Image Context:\n{image_context}")

        if context:
            prompt_parts.append(f"Document Context:\n{context}")

        prompt_parts.append(f"Question:\n{query}")

        if context or image_context:
            prompt_parts.append(
                "IMPORTANT:\n"
                "- Answer using provided context\n"
                "- Always include citations like [1], [2]\n"
                "- If answer not found, say you don't know"
            )

        final_prompt = "\n\n".join(prompt_parts)

        if image_context and context:
            route = "image+rag"
        elif image_context:
            route = "image"
        elif context:
            route = "rag"
        else:
            route = "general"

        answer = get_llm_response(final_prompt, history)

        save_message(chat_id, "user", query)
        save_message(chat_id, "assistant", answer)

        return {
            "response": answer.strip(),
            "chat_id": chat_id,
            "sources": sources,
            "route": route
        }

    except Exception as e:
        logger.error("RAG pipeline error: %s", str(e))
        return {
            "response": "Something went wrong",
            "chat_id": chat_id,
            "sources": [],
            "route": "error"
        }
