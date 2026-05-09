import hashlib
import logging
import threading
from collections import OrderedDict
from typing import Any, Dict, Optional

from app import get_settings

logger = logging.getLogger(__name__)


class CacheManager:
    def __init__(self):
        settings = get_settings()
        cache_cfg = settings.cache
        self.enabled = cache_cfg.get("enabled", True)
        self.backend = cache_cfg.get("backend", "memory")
        self.ttl_seconds = cache_cfg.get("ttl_seconds", 3600)
        self._memory_cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._lock = threading.Lock()
        self._max_size = 1000
        self._redis_client = None

        if self.backend == "redis" and self.enabled:
            self._init_redis(cache_cfg.get("redis_url", "redis://localhost:6379/0"))

    def _init_redis(self, redis_url: str) -> None:
        try:
            import redis
            self._redis_client = redis.from_url(redis_url, decode_responses=True)
            self._redis_client.ping()
            logger.info(f"Redis cache initialized: {redis_url}")
        except Exception as e:
            logger.warning(f"Redis init failed, falling back to memory cache: {e}")
            self.backend = "memory"
            self._redis_client = None

    def _make_key(self, question: str, mode: Optional[str] = None) -> str:
        raw = f"{question}:{mode or 'default'}"
        return hashlib.md5(raw.encode()).hexdigest()

    def get(self, question: str, mode: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None

        key = self._make_key(question, mode)

        if self.backend == "redis" and self._redis_client:
            return self._get_redis(key)
        return self._get_memory(key)

    def set(self, question: str, result: Dict[str, Any], mode: Optional[str] = None) -> None:
        if not self.enabled:
            return

        key = self._make_key(question, mode)

        if self.backend == "redis" and self._redis_client:
            self._set_redis(key, result)
        else:
            self._set_memory(key, result)

    def _get_memory(self, key: str) -> Optional[Dict[str, Any]]:
        import time
        with self._lock:
            if key in self._memory_cache:
                entry = self._memory_cache[key]
                if time.time() - entry["timestamp"] < self.ttl_seconds:
                    self._memory_cache.move_to_end(key)
                    return entry["data"]
                else:
                    del self._memory_cache[key]
        return None

    def _set_memory(self, key: str, data: Dict[str, Any]) -> None:
        import time
        with self._lock:
            if len(self._memory_cache) >= self._max_size:
                self._memory_cache.popitem(last=False)
            self._memory_cache[key] = {"data": data, "timestamp": time.time()}

    def _get_redis(self, key: str) -> Optional[Dict[str, Any]]:
        try:
            import json
            data = self._redis_client.get(f"rag_cache:{key}")
            if data:
                return json.loads(data)
        except Exception as e:
            logger.warning(f"Redis get failed: {e}")
        return None

    def _set_redis(self, key: str, data: Dict[str, Any]) -> None:
        try:
            import json
            self._redis_client.setex(
                f"rag_cache:{key}", self.ttl_seconds, json.dumps(data, default=str)
            )
        except Exception as e:
            logger.warning(f"Redis set failed: {e}")

    def clear(self) -> None:
        if self.backend == "redis" and self._redis_client:
            try:
                for key in self._redis_client.scan_iter("rag_cache:*"):
                    self._redis_client.delete(key)
            except Exception as e:
                logger.warning(f"Redis clear failed: {e}")
        else:
            with self._lock:
                self._memory_cache.clear()
