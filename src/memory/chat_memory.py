from src.db.mongo import get_chat_collection
from src.core.logger import get_logger

logger = get_logger(__name__)

MAX_HISTORY = 10


def save_message(session_id: str, role: str, content: str):
    try:
        col = get_chat_collection()
        col.insert_one({
            "session_id": session_id,
            "role": role,
            "content": content
        })
    except Exception as e:
        logger.error(f"Memory save error: {str(e)}")


def get_chat_history(session_id: str):
    try:
        col = get_chat_collection()
        history = list(
            col.find({"session_id": session_id})
            .sort("_id", -1)
            .limit(MAX_HISTORY)
        )

        history.reverse()
        return history

    except Exception as e:
        logger.error(f"Memory fetch error: {str(e)}")
        return []


def get_history_as_messages(session_id: str):
    history = get_chat_history(session_id)

    messages = []
    for msg in history:
        messages.append({
            "role": msg["role"],
            "content": msg["content"]
        })

    return messages


def clear_memory(session_id: str):
    try:
        col = get_chat_collection()
        col.delete_many({"session_id": session_id})
    except Exception as e:
        logger.error(f"Memory clear error: {str(e)}")
