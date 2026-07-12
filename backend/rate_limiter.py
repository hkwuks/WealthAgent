"""
速率限制器 — 控制对外部API的并发数和请求频率，避免反爬

用法：
    # 简单限流
    limiter = RateLimiter(max_concurrent=3, min_interval=0.3)
    async with limiter:
        await do_request()

    # 按host自动分组限流（推荐用于多数据源场景）
    group = RateLimiterGroup(max_concurrent=3, min_interval=0.3)
    async with group.limit("https://push2.eastmoney.com/api..."):
        await do_request()
    async with group.limit("https://hq.sinajs.cn/api..."):  # 不同host，不阻塞
        await do_request()
"""

import asyncio
import time
from contextlib import asynccontextmanager


class RateLimiter:
    """异步速率限制器 — 信号量 + 最小请求间隔"""

    def __init__(self, max_concurrent: int = 3, min_interval: float = 0.3):
        self._sem = asyncio.Semaphore(max_concurrent)
        self._min_interval = min_interval
        self._last_call = 0.0

    async def __aenter__(self):
        await self._sem.acquire()
        now = time.monotonic()
        wait = self._min_interval - (now - self._last_call)
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_call = time.monotonic()
        return self

    async def __aexit__(self, *args):
        self._sem.release()


class RateLimiterGroup:
    """按 host 自动分组的速率限制器

    不同 host 有各自的 RateLimiter，互不阻塞；
    同一 host 的请求受同一 RateLimiter 控制。
    避免跨标签页加载不同数据源时互相阻塞。
    """

    def __init__(self, max_concurrent: int = 3, min_interval: float = 0.3):
        self._max_concurrent = max_concurrent
        self._min_interval = min_interval
        self._limiters: dict[str, RateLimiter] = {}
        self._lock = asyncio.Lock()

    def _get_limiter(self, host: str) -> RateLimiter:
        if host not in self._limiters:
            self._limiters[host] = RateLimiter(self._max_concurrent, self._min_interval)
        return self._limiters[host]

    @asynccontextmanager
    async def limit(self, url: str):
        """根据 URL 自动提取 host，使用对应的 RateLimiter"""
        from urllib.parse import urlparse
        host = urlparse(url).hostname or "default"
        limiter = self._get_limiter(host)
        async with limiter:
            yield
