from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.collection import Collection

from app.config import settings

BOT_NAME_PATTERN = re.compile(
    r"\b(?:your name is|you are|call yourself|i will call you)\s+([A-Za-z][A-Za-z0-9 _-]{1,40})",
    re.IGNORECASE,
)


class ChatMemoryStore:
    def __init__(self) -> None:
        self._fallback_messages: dict[str, dict[str, list[dict[str, Any]]]] = {}
        self._fallback_profiles: dict[str, dict[str, Any]] = {}
        self._messages: Collection | None = None
        self._profiles: Collection | None = None

        try:
            client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=1500)
            client.admin.command("ping")
            db = client[settings.mongodb_db]
            self._messages = db["chat_history"]
            self._profiles = db["user_profiles"]
            self._messages.create_index([("user_id", ASCENDING), ("session_id", ASCENDING), ("created_at", ASCENDING)])
            self._profiles.create_index([("email", ASCENDING)], unique=True)
            self._profiles.create_index([("user_id", ASCENDING)], unique=True)
        except Exception:
            self._messages = None
            self._profiles = None

    def create_user(self, name: str, email: str, password_hash: str) -> dict[str, Any]:
        normalized_email = str(email or "").strip().lower()
        profile = {
            "user_id": uuid.uuid4().hex,
            "name": str(name or "User").strip() or "User",
            "email": normalized_email,
            "password_hash": password_hash,
            "bot_name": "Aegis AI",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        if self._profiles is not None:
            self._profiles.insert_one(profile)
            return profile
        self._fallback_profiles[normalized_email] = dict(profile)
        return profile

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        normalized_email = str(email or "").strip().lower()
        if self._profiles is not None:
            return self._profiles.find_one({"email": normalized_email}, {"_id": 0})
        return self._fallback_profiles.get(normalized_email)

    def get_user_by_id(self, user_id: str) -> dict[str, Any] | None:
        user_id = str(user_id or "").strip()
        if not user_id:
            return None
        if self._profiles is not None:
            return self._profiles.find_one({"user_id": user_id}, {"_id": 0})
        return next((profile for profile in self._fallback_profiles.values() if profile.get("user_id") == user_id), None)

    def update_bot_name(self, user_id: str, bot_name: str) -> None:
        clean_name = str(bot_name or "").strip()[:40]
        if not clean_name:
            return
        if self._profiles is not None:
            self._profiles.update_one(
                {"user_id": user_id},
                {"$set": {"bot_name": clean_name, "updated_at": datetime.now(timezone.utc)}},
            )
            return
        profile = self.get_user_by_id(user_id)
        if profile is not None:
            profile["bot_name"] = clean_name
            profile["updated_at"] = datetime.now(timezone.utc)

    def detect_and_store_bot_name(self, user_id: str, content: str) -> str | None:
        match = BOT_NAME_PATTERN.search(str(content or ""))
        if not match:
            return None
        bot_name = " ".join(match.group(1).split()).strip(" .,!?:;")
        if not bot_name:
            return None
        self.update_bot_name(user_id, bot_name)
        return bot_name

    def get_bot_name(self, user_id: str | None) -> str:
        if not user_id:
            return "Aegis AI"
        profile = self.get_user_by_id(user_id)
        value = str((profile or {}).get("bot_name", "")).strip()
        return value or "Aegis AI"

    def save_message(self, user_id: str, session_id: str, role: str, content: str) -> None:
        if not user_id:
            return
        record = {
            "user_id": user_id,
            "session_id": session_id,
            "role": role,
            "content": str(content),
            "created_at": datetime.now(timezone.utc),
        }
        if role == "user":
            self.detect_and_store_bot_name(user_id, content)

        if self._messages is not None:
            self._messages.insert_one(record)
            return

        self._fallback_messages.setdefault(user_id, {}).setdefault(session_id, []).append(record)

    def load_history(self, user_id: str, session_id: str, limit: int | None = None) -> list[dict[str, str]]:
        limit = limit or settings.max_history_messages
        if not user_id:
            return []

        if self._messages is not None:
            docs = list(
                self._messages.find({"user_id": user_id, "session_id": session_id}, {"_id": 0})
                .sort("created_at", DESCENDING)
                .limit(limit)
            )
            docs.reverse()
        else:
            docs = self._fallback_messages.get(user_id, {}).get(session_id, [])[-limit:]

        return [{"role": str(doc.get("role", "user")), "content": str(doc.get("content", ""))} for doc in docs]

    def list_sessions(self, user_id: str, limit: int = 100) -> list[dict[str, Any]]:
        if not user_id:
            return []

        sessions: list[dict[str, Any]] = []
        if self._messages is not None:
            session_ids = self._messages.distinct("session_id", {"user_id": user_id})
            for session_id in session_ids[:limit]:
                docs = list(
                    self._messages.find({"user_id": user_id, "session_id": session_id}, {"_id": 0})
                    .sort("created_at", ASCENDING)
                )
                if not docs:
                    continue
                first_user = next((doc for doc in docs if doc.get("role") == "user"), docs[0])
                created_at = docs[0].get("created_at")
                updated_at = docs[-1].get("created_at")
                sessions.append(
                    {
                        "id": session_id,
                        "title": str(first_user.get("content", "New chat"))[:80] or "New chat",
                        "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else "",
                        "updated_at": updated_at.isoformat() if hasattr(updated_at, "isoformat") else "",
                    }
                )
        else:
            for session_id, docs in self._fallback_messages.get(user_id, {}).items():
                if not docs:
                    continue
                first_user = next((doc for doc in docs if doc.get("role") == "user"), docs[0])
                sessions.append(
                    {
                        "id": session_id,
                        "title": str(first_user.get("content", "New chat"))[:80] or "New chat",
                        "created_at": docs[0]["created_at"].isoformat(),
                        "updated_at": docs[-1]["created_at"].isoformat(),
                    }
                )

        sessions.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
        return sessions[:limit]

    def load_session_messages(self, user_id: str, session_id: str) -> list[dict[str, str]]:
        if not user_id:
            return []
        if self._messages is not None:
            docs = list(
                self._messages.find({"user_id": user_id, "session_id": session_id}, {"_id": 0})
                .sort("created_at", ASCENDING)
            )
        else:
            docs = self._fallback_messages.get(user_id, {}).get(session_id, [])

        return [
            {
                "role": str(doc.get("role", "user")),
                "content": str(doc.get("content", "")),
                "timestamp": doc.get("created_at").isoformat() if hasattr(doc.get("created_at"), "isoformat") else "",
            }
            for doc in docs
        ]

    def load_recent_messages_across_sessions(
        self,
        user_id: str,
        current_session_id: str,
        session_limit: int = 3,
        message_limit: int = 12,
    ) -> list[dict[str, str]]:
        if not user_id:
            return []

        docs: list[dict[str, Any]] = []
        if self._messages is not None:
            session_ids = [
                session_id
                for session_id in self._messages.distinct("session_id", {"user_id": user_id})
                if session_id != current_session_id
            ]
            ordered_sessions: list[tuple[str, datetime | Any]] = []
            for session_id in session_ids:
                latest = self._messages.find_one(
                    {"user_id": user_id, "session_id": session_id},
                    {"_id": 0, "created_at": 1},
                    sort=[("created_at", DESCENDING)],
                )
                if latest is None:
                    continue
                ordered_sessions.append((session_id, latest.get("created_at")))
            ordered_sessions.sort(key=lambda item: item[1] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
            chosen_ids = [item[0] for item in ordered_sessions[:session_limit]]
            if chosen_ids:
                docs = list(
                    self._messages.find({"user_id": user_id, "session_id": {"$in": chosen_ids}}, {"_id": 0})
                    .sort("created_at", DESCENDING)
                    .limit(message_limit)
                )
                docs.reverse()
        else:
            sessions = self._fallback_messages.get(user_id, {})
            ordered = sorted(
                [
                    (session_id, messages[-1].get("created_at"))
                    for session_id, messages in sessions.items()
                    if session_id != current_session_id and messages
                ],
                key=lambda item: item[1] or datetime.min.replace(tzinfo=timezone.utc),
                reverse=True,
            )
            chosen_ids = [item[0] for item in ordered[:session_limit]]
            for session_id in reversed(chosen_ids):
                docs.extend(sessions.get(session_id, [])[-message_limit:])

        return [
            {
                "role": str(doc.get("role", "user")),
                "content": str(doc.get("content", "")),
            }
            for doc in docs[-message_limit:]
        ]

    def delete_session(self, user_id: str, session_id: str) -> None:
        if not user_id:
            return
        if self._messages is not None:
            self._messages.delete_many({"user_id": user_id, "session_id": session_id})
            return
        self._fallback_messages.get(user_id, {}).pop(session_id, None)


memory_store = ChatMemoryStore()
