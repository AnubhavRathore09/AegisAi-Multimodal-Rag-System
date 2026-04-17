from src.db.mongo import collection
from datetime import datetime


# ==============================
# 💾 Save Message
# ==============================
def save_message(chat_id: str, role: str, content: str):
    try:
        collection.insert_one({
            "chat_id": chat_id,
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow()
        })
    except Exception as e:
        print(f"[Memory Save Error]: {str(e)}")


# ==============================
# 📜 Get Chat History (for LLM)
# ==============================
def get_chat_history(chat_id: str, limit: int = 6) -> str:
    try:
        messages = list(
            collection.find({"chat_id": chat_id})
            .sort("timestamp", -1)
            .limit(limit)
        )

        messages.reverse()

        history_lines = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "user":
                history_lines.append(f"User: {content}")
            elif role == "assistant":
                history_lines.append(f"Assistant: {content}")

        return "\n".join(history_lines)

    except Exception as e:
        print(f"[Memory Fetch Error]: {str(e)}")
        return ""


# ==============================
# 📂 Get All Chats (Sidebar)
# ==============================
def get_all_chat_ids():
    try:
        chat_ids = collection.distinct("chat_id")
        return chat_ids
    except Exception as e:
        print(f"[Chat List Error]: {str(e)}")
        return []


# ==============================
# 🧹 Delete Chat
# ==============================
def delete_chat(chat_id: str):
    try:
        collection.delete_many({"chat_id": chat_id})
        return True
    except Exception as e:
        print(f"[Delete Chat Error]: {str(e)}")
        return False
