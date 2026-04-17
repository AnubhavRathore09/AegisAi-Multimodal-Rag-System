from __future__ import annotations

import time
from collections import defaultdict, deque

from src.config import settings

try:
    from redis.asyncio import Redis
except Exception:
    Redis = None


class RateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[str, deque[float]] = defaultdict(deque)
        self._redis = None

    async def _client(self):
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

    async def allow(self, key: str, limit: int | None = None, window_seconds: int | None = None) -> tuple[bool, int]:
        limit = limit or settings.rate_limit_requests
        window_seconds = window_seconds or settings.rate_limit_window_seconds
        client = await self._client()
        if client is not None:
            redis_key = f"ratelimit:{key}"
            try:
                current = await client.incr(redis_key)
                if current == 1:
                    await client.expire(redis_key, window_seconds)
                ttl = await client.ttl(redis_key)
                return current <= limit, max(int(ttl or window_seconds), 1)
            except Exception:
                pass

        now = time.time()
        bucket = self._buckets[key]
        while bucket and now - bucket[0] >= window_seconds:
            bucket.popleft()
        if len(bucket) >= limit:
            retry_after = max(1, int(window_seconds - (now - bucket[0])))
            return False, retry_after
        bucket.append(now)
        return True, window_seconds


rate_limiter = RateLimiter()

