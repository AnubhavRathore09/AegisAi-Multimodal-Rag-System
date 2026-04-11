from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pymongo import MongoClient
from pymongo.collection import Collection

from app.config import settings


class ChatMemoryStore:
    def __init__(self) -> None:
        self._fallback: dict[str, list[dict[str, Any]]] = {}
        self._collection: Collection | None = None

        try:
            client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=1500)
            client.admin.command("ping")
            self._collection = client[settings.mongodb_db]["chat_history"]
        except Exception:
            self._collection = None

    def save_message(self, session_id: str, role: str, content: str) -> None:
        record = {
            "session_id": session_id,
            "role": role,
            "content": str(content),
            "created_at": datetime.now(timezone.utc),
        }

        if self._collection is not None:
            self._collection.insert_one(record)
            return

        self._fallback.setdefault(session_id, []).append(record)

    def load_history(self, session_id: str, limit: int | None = None) -> list[dict[str, str]]:
        limit = limit or settings.max_history_messages

        if self._collection is not None:
            docs = list(
                self._collection.find({"session_id": session_id}, {"_id": 0})
                .sort("created_at", -1)
                .limit(limit)
            )
            docs.reverse()
        else:
            docs = self._fallback.get(session_id, [])[-limit:]

        return [
            {"role": str(doc.get("role", "user")), "content": str(doc.get("content", ""))}
            for doc in docs
        ]

    def list_sessions(self, limit: int = 100) -> list[dict[str, Any]]:
        sessions: list[dict[str, Any]] = []

        if self._collection is not None:
            session_ids = self._collection.distinct("session_id")
            for session_id in session_ids[:limit]:
                docs = list(
                    self._collection.find({"session_id": session_id}, {"_id": 0})
                    .sort("created_at", 1)
                )
                if not docs:
                    continue
                first_user = next((doc for doc in docs if doc.get("role") == "user"), docs[0])
                created_at = docs[0].get("created_at")
                updated_at = docs[-1].get("created_at")
                sessions.append(
                    {
                        "id": session_id,
                        "title": str(first_user.get("content", "Chat"))[:80],
                        "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else "",
                        "updated_at": updated_at.isoformat() if hasattr(updated_at, "isoformat") else "",
                    }
                )
        else:
            for session_id, docs in self._fallback.items():
                if not docs:
                    continue
                first_user = next((doc for doc in docs if doc.get("role") == "user"), docs[0])
                sessions.append(
                    {
                        "id": session_id,
                        "title": str(first_user.get("content", "Chat"))[:80],
                        "created_at": docs[0]["created_at"].isoformat(),
                        "updated_at": docs[-1]["created_at"].isoformat(),
                    }
                )

        sessions.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
        return sessions[:limit]

    def load_session_messages(self, session_id: str) -> list[dict[str, str]]:
        if self._collection is not None:
            docs = list(
                self._collection.find({"session_id": session_id}, {"_id": 0})
                .sort("created_at", 1)
            )
        else:
            docs = self._fallback.get(session_id, [])

        return [
            {
                "role": str(doc.get("role", "user")),
                "content": str(doc.get("content", "")),
                "timestamp": doc.get("created_at").isoformat() if hasattr(doc.get("created_at"), "isoformat") else "",
            }
            for doc in docs
        ]

    def delete_session(self, session_id: str) -> None:
        if self._collection is not None:
            self._collection.delete_many({"session_id": session_id})
            return
        self._fallback.pop(session_id, None)


memory_store = ChatMemoryStore()
