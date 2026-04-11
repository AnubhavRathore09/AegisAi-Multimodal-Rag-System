"""Chat history endpoints."""
from fastapi import APIRouter
from pymongo import DESCENDING
from src.db.mongo import get_chat_collection
from src.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get("/history")
def list_sessions():
    col = get_chat_collection()

    pipeline = [
        {"$sort": {"timestamp": DESCENDING}},
        {"$group": {
            "_id": "$chat_id",
            "latest": {"$first": "$timestamp"},
        }},
        {"$sort": {"latest": DESCENDING}},
        {"$limit": 100},
    ]

    results = list(col.aggregate(pipeline))
    sessions = []

    for r in results:
        cid = r["_id"]

        first = col.find_one(
            {"chat_id": cid, "role": "user"},
            sort=[("timestamp", 1)]
        )

        title = (
            first["content"][:47] + "…"
            if first and len(first["content"]) > 50
            else (first["content"] if first else "Chat")
        )

        sessions.append({
            "id": cid,
            "title": title,
            "updated_at": r["latest"].isoformat() if r.get("latest") else None,
            "created_at": r["latest"].isoformat() if r.get("latest") else None,
        })

    return sessions


@router.get("/history/{chat_id}")
def get_session(chat_id: str):
    col = get_chat_collection()

    docs = list(col.find(
        {"chat_id": chat_id},
        {"_id": 0, "role": 1, "content": 1, "timestamp": 1}
    ).sort("timestamp", 1))

    return [
        {
            "role": d["role"],
            "content": d["content"],
            "timestamp": d["timestamp"].isoformat() if d.get("timestamp") else None
        }
        for d in docs
    ]


@router.delete("/history/{chat_id}")
def delete_session(chat_id: str):
    result = get_chat_collection().delete_many({"chat_id": chat_id})

    return {
        "status": "deleted",
        "count": result.deleted_count
    }
