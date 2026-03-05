import hashlib
import logging
import re
from collections import OrderedDict
from time import time

from app.config import get_settings

logger = logging.getLogger(__name__)


class LRUCache:
    """In-memory LRU cache with TTL support and optional Redis backend."""

    def __init__(self, max_size: int = 1000, ttl_seconds: int = 3600) -> None:
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._store: OrderedDict[str, tuple[str, float]] = OrderedDict()
        self._hits: int = 0
        self._misses: int = 0
        self._redis = None
        self._use_redis = False
        self._try_redis()

    def _try_redis(self) -> None:
        import os

        redis_url = os.environ.get("REDIS_URL")
        if not redis_url:
            return
        try:
            import redis  # type: ignore[import-untyped]

            client = redis.from_url(redis_url)
            client.ping()
            self._redis = client
            self._use_redis = True
            logger.info("Redis cache backend connected at %s", redis_url)
        except Exception as exc:
            logger.warning("Redis unavailable, using in-memory LRU cache: %s", exc)

    def get(self, key: str) -> str | None:
        if self._use_redis and self._redis is not None:
            try:
                value = self._redis.get(key)
                if value is not None:
                    self._hits += 1
                    return value.decode("utf-8") if isinstance(value, bytes) else value
                self._misses += 1
                return None
            except Exception as exc:
                logger.warning("Redis get error: %s", exc)

        entry = self._store.get(key)
        if entry is None:
            self._misses += 1
            return None
        value, ts = entry
        if time() - ts > self._ttl:
            del self._store[key]
            self._misses += 1
            return None
        self._store.move_to_end(key)
        self._hits += 1
        return value

    def set(self, key: str, value: str) -> None:
        if self._use_redis and self._redis is not None:
            try:
                self._redis.setex(key, self._ttl, value)
                return
            except Exception as exc:
                logger.warning("Redis set error: %s", exc)

        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = (value, time())
        while len(self._store) > self._max_size:
            self._store.popitem(last=False)

    def make_key(self, repo_id: str, prompt: str) -> str:
        """Create a cache key from repo_id and prompt."""
        normalized = re.sub(r"\s+", " ", prompt.strip().lower())
        raw = repo_id + "|" + normalized
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def stats(self) -> dict:
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0.0
        return {
            "hits": self._hits,
            "misses": self._misses,
            "size": len(self._store),
            "hit_rate": round(hit_rate, 4),
        }


_cache_instance: LRUCache | None = None


def get_cache() -> LRUCache:
    """Return the singleton LRUCache instance."""
    global _cache_instance
    if _cache_instance is None:
        settings = get_settings()
        _cache_instance = LRUCache(
            max_size=settings.cache_max_size,
            ttl_seconds=settings.cache_ttl_seconds,
        )
    return _cache_instance
