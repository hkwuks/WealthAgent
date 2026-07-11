"""
通用 TTL 缓存 — per-entry TTL + maxsize FIFO 淘汰

用法::
    cache = TtlCache(default_ttl=60, maxsize=1024)
    cache.set("key", value)           # 使用 default_ttl
    cache.set("key", value, ttl=30)   # 指定 TTL
    val = cache.get("key")            # 过期返回 None
    cache.delete("key")
    cache.clear()
"""

import time
from typing import Any, Optional


class TtlCache:
    """泛型 TTL 缓存，非线程安全。asyncio 单线程下无需锁。"""

    def __init__(self, default_ttl: Optional[float] = 60, maxsize: int = 1024):
        """
        Args:
            default_ttl: 默认过期秒数。None 表示永不过期（仅 maxsize 淘汰）。
            maxsize: 最大条目数，超出后淘汰最早插入的条目。
        """
        self._default_ttl = default_ttl
        self._maxsize = maxsize
        self._data: dict[str, Any] = {}
        self._expires: dict[str, float] = {}  # key → deadline(montonic)

    def get(self, key: str) -> Optional[Any]:
        """获取缓存，过期或不存在返回 None"""
        if key not in self._data:
            return None
        expires = self._expires.get(key)
        if expires is not None and time.monotonic() > expires:
            self._data.pop(key, None)
            self._expires.pop(key, None)
            return None
        return self._data[key]

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        """写入缓存。ttl 覆盖 default_ttl，None 表示按 default_ttl。"""
        if key not in self._data:
            self._evict_if_full()
        effective_ttl = ttl if ttl is not None else self._default_ttl
        self._data[key] = value
        if effective_ttl is not None:
            self._expires[key] = time.monotonic() + effective_ttl
        else:
            self._expires.pop(key, None)

    def delete(self, key: str) -> None:
        self._data.pop(key, None)
        self._expires.pop(key, None)

    def clear(self) -> None:
        self._data.clear()
        self._expires.clear()

    @property
    def size(self) -> int:
        return len(self._data)

    def _evict_if_full(self) -> None:
        if len(self._data) < self._maxsize:
            return
        # FIFO: 淘汰最旧的条目（Python 3.7+ dict 保持插入顺序）
        oldest = next(iter(self._data))
        self._data.pop(oldest, None)
        self._expires.pop(oldest, None)
