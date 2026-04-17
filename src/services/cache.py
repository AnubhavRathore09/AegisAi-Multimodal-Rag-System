from __future__ import annotations

import json
import time
from collections import OrderedDict
from threading import Lock
from typing import Any

from src.config import settings

try:
    from redis.asyncio import Redis
except Exception:
    Redis = None


class _MemoryCache:
    def __init__(self, max_items: int) -> None:
        self.max_items = max_items
        self._store: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
        self._lock = Lock()

    def get(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            item = self._store.get(key)
            if item is None:
                return None
            expires_at, payload = item
            if time.time() > expires_at:
                self._store.pop(key, None)
                return None
            self._store.move_to_end(key)
            return dict(payload)

    def set(self, key: str, payload: dict[str, Any], ttl_seconds: int) -> None:
        with self._lock:
            self._store[key] = (time.time() + ttl_seconds, dict(payload))
            self._store.move_to_end(key)
            while len(self._store) > self.max_items:
                self._store.popitem(last=False)


class CacheService:
    def __init__(self) -> None:
        self._memory = _MemoryCache(settings.cache_max_items)
        self._redis: Redis | None = None

    async def _client(self) -> Redis | None:
        if Redis is None or not settings.redis_url:
            return None
        if self._redis is not None:
            return self._redis
        try:
            client = Redis.from_url(settings.redis_url, decode_responses=True)
            await client.ping()
            self._redis = client
            return client
        except Exception:
            self._redis = None
            return None

    async def get_json(self, namespace: str, key: str) -> dict[str, Any] | None:
        full_key = f"{namespace}:{key}"
        client = await self._client()
        if client is not None:
            try:
                payload = await client.get(full_key)
                return json.loads(payload) if payload else None
            except Exception:
                pass
        return self._memory.get(full_key)

    async def set_json(self, namespace: str, key: str, payload: dict[str, Any], ttl_seconds: int) -> None:
        full_key = f"{namespace}:{key}"
        client = await self._client()
        if client is not None:
            try:
                await client.set(full_key, json.dumps(payload), ex=ttl_seconds)
                return
            except Exception:
                pass
        self._memory.set(full_key, payload, ttl_seconds)

    async def get_response(self, key: str) -> dict[str, Any] | None:
        return await self.get_json("response", key)

    async def set_response(self, key: str, payload: dict[str, Any]) -> None:
        await self.set_json("response", key, payload, settings.cache_ttl_seconds)

    async def get_retrieval(self, key: str) -> dict[str, Any] | None:
        return await self.get_json("retrieval", key)

    async def set_retrieval(self, key: str, payload: dict[str, Any]) -> None:
        await self.set_json("retrieval", key, payload, settings.retrieval_cache_ttl_seconds)


cache_service = CacheService()

