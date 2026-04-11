from src.llms.groq_client import get_llm_response, analyze_image
from src.memory.chat_memory import get_history_as_messages, save_message
from src.rag.query_rewriter import rewrite_query
from src.core.logger import get_logger

logger = get_logger(__name__)

def is_greeting(query: str):
    greetings = ["hi", "hello", "hii", "hey", "namaste"]
    return query.lower().strip() in greetings

def run_rag(user_query: str, session_id: str, use_docs: bool = False):
    try:
        logger.info(f"Incoming query: {user_query}")

        chat_history = get_history_as_messages(session_id)

        if isinstance(user_query, dict):
            images = user_query.get("images", [])
            query = user_query.get("query", "")

            if images:
                img = images[0]
                response = analyze_image(
                    base64_data=img.get("data"),
                    mime_type=img.get("type"),
                    question=query
                )
                save_message(session_id, "user", query)
                save_message(session_id, "assistant", response)
                return str(response)
        else:
            query = user_query

        original_query = query

        rewritten = rewrite_query(query, chat_history)

        if rewritten and len(rewritten.strip()) > 3:
            query = rewritten

        if is_greeting(query):
            response = "Hey 🙂 I'm your Adaptive RAG AI assistant. How can I help you today?"
            save_message(session_id, "user", original_query)
            save_message(session_id, "assistant", response)
            return response

        prompt = f"""
You are a helpful AI assistant.

Answer clearly and in detail.

User Question:
{query}

Answer:
"""

        response = get_llm_response(prompt, history=chat_history)

        if not response or len(response.strip()) < 3:
            response = "Please ask a more specific question."

        save_message(session_id, "user", original_query)
        save_message(session_id, "assistant", response)

        return str(response)

    except Exception as e:
        logger.error(f"RAG error: {str(e)}")
        return "Error generating response"
