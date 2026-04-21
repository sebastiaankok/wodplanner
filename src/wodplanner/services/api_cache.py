"""Short TTL in-memory cache for non-user-specific API responses."""

import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)


class ApiCacheService:
    def __init__(self, ttl_seconds: int = 120) -> None:
        self._cache: dict[str, tuple[Any, float]] = {}
        self._ttl = ttl_seconds
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._cache.get(key)
            if entry and time.monotonic() < entry[1]:
                logger.debug("Cache hit: %s", key)
                return entry[0]
            return None

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._cache[key] = (value, time.monotonic() + self._ttl)

    def invalidate(self, key: str) -> None:
        """Remove a cache entry by key."""
        with self._lock:
            self._cache.pop(key, None)
            logger.debug("Cache invalidated: %s", key)
