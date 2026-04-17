from datetime import datetime, timezone
from src.db.mongo import get_chat_collection
from src.core.config import settings
from src.core.logger import get_logger

logger = get_logger(__name__)


def save_message(chat_id: str, role: str, content: str) -> None:
    try:
        get_chat_collection().insert_one({
            "chat_id": chat_id,
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc)
        })
    except Exception as e:
        logger.error(f"Memory save error: {str(e)}")


def get_chat_history(chat_id: str, limit: int | None = None) -> list[dict]:
    try:
        lim = limit or settings.MAX_HISTORY_MESSAGES

        docs = list(
            get_chat_collection()
            .find(
                {"chat_id": chat_id},
                {"_id": 0, "role": 1, "content": 1, "timestamp": 1}
            )
            .sort("timestamp", -1)
            .limit(lim)
        )

        return list(reversed(docs))

    except Exception as e:
        logger.error(f"Memory fetch error: {str(e)}")
        return []


def get_history_as_messages(chat_id: str) -> list[dict]:
    msgs = get_chat_history(chat_id)

    return [
        {
            "role": m["role"],
            "content": m["content"]
        }
        for m in msgs
    ]


def format_history_for_prompt(chat_id: str) -> str:
    msgs = get_chat_history(chat_id)

    if not msgs:
        return ""

    lines = [
        f"{m['role'].capitalize()}: {m['content']}"
        for m in msgs
    ]

    return "\n".join(lines)


def clear_history(chat_id: str) -> int:
    try:
        result = get_chat_collection().delete_many({"chat_id": chat_id})
        logger.info(f"Cleared {result.deleted_count} msgs for {chat_id}")
        return result.deleted_count

    except Exception as e:
        logger.error(f"Memory delete error: {str(e)}")
        return 0
