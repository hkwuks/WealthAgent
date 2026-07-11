"""
数据缓存服务

只保留内存缓存（TtlCache）+ 历史价格持久化。
去掉 JSON 文件持久化（60s TTL 不值得写盘）。
"""

import asyncio
import json
from typing import Dict, Any, Optional, List
from datetime import datetime
from loguru import logger
from pathlib import Path

from backend.ttl_cache import TtlCache


class DataCacheService:
    """数据缓存服务 — 统一的市场数据缓存 + 历史价格持久化"""

    def __init__(self, data_dir: str = None):
        if data_dir is None:
            project_root = Path(__file__).parent.parent
            data_dir = project_root / "data" / "backend"

        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.price_history_file = self.data_dir / "price_history.json"
        self.price_history_days = 30

        # 价格历史文件操作锁
        self._price_lock = asyncio.Lock()

        # 统一的市场数据缓存（60s TTL，最多 2048 条目）
        self._cache = TtlCache(default_ttl=60, maxsize=2048)

        logger.info(f"数据缓存服务初始化完成，数据目录: {self.data_dir.absolute()}")

    # ── 市场数据缓存 ──

    async def get_cached_market_data(self, code: str, data_type: str = "index",
                                     ttl: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """获取单个市场数据的缓存"""
        return self._cache.get(f"{data_type}:{code}")

    async def update_market_cache(self, code: str, data: Dict[str, Any],
                                  data_type: str = "index"):
        """更新单个市场数据的缓存"""
        self._cache.set(f"{data_type}:{code}", data)

    async def clear_cache(self, cache_type: Optional[str] = None):
        """清除缓存（cache_type 参数保留兼容，统一清空）"""
        self._cache.clear()
        logger.info("市场数据缓存已清除")

    def get_cache_info(self) -> Dict[str, Any]:
        """获取缓存信息"""
        return {
            "default_ttl": self._cache._default_ttl,
            "maxsize": self._cache._maxsize,
            "size": self._cache.size,
        }

    # ── 历史价格持久化（保留，是数据而非缓存）──

    async def save_price_history(self, code: str, price: float, data_type: str = "index"):
        """保存价格到历史记录"""
        async with self._price_lock:
            try:
                history_data = await self._load_price_history_from_file()
                key = f"{data_type}:{code}"
                if key not in history_data:
                    history_data[key] = []

                today = datetime.now().strftime("%Y-%m-%d")
                now_iso = datetime.now().isoformat()

                existing_index = None
                for i, item in enumerate(history_data[key]):
                    item_date = datetime.fromisoformat(item["timestamp"]).strftime("%Y-%m-%d")
                    if item_date == today:
                        existing_index = i
                        break

                if existing_index is not None:
                    history_data[key][existing_index]["price"] = price
                    history_data[key][existing_index]["timestamp"] = now_iso
                else:
                    history_data[key].append({
                        "timestamp": now_iso,
                        "price": price
                    })

                cutoff = datetime.now().timestamp() - (self.price_history_days * 86400)
                history_data[key] = [
                    item for item in history_data[key]
                    if datetime.fromisoformat(item["timestamp"]).timestamp() > cutoff
                ]
                history_data[key].sort(key=lambda x: x["timestamp"])
                await self._save_price_history_to_file(history_data)
            except Exception as e:
                logger.error(f"保存历史价格失败 {code}: {e}")

    async def get_price_history(self, code: str, data_type: str = "index",
                                days: int = 30) -> List[Dict[str, Any]]:
        """获取价格历史记录"""
        async with self._price_lock:
            try:
                history = await self._load_price_history_from_file()
                key = f"{data_type}:{code}"
                if key not in history:
                    return []
                cutoff = datetime.now().timestamp() - (days * 86400)
                return [
                    item for item in history[key]
                    if datetime.fromisoformat(item["timestamp"]).timestamp() > cutoff
                ]
            except Exception as e:
                logger.error(f"获取历史价格失败 {code}: {e}")
                return []

    async def get_all_price_history_codes(self) -> Dict[str, List[str]]:
        async with self._price_lock:
            try:
                history = await self._load_price_history_from_file()
                result: Dict[str, List[str]] = {"index": [], "stock": [], "etf": [], "global_index": []}
                for key in history:
                    if ":" in key:
                        t, c = key.split(":", 1)
                        if t in result:
                            result[t].append(c)
                return result
            except Exception:
                return {"index": [], "stock": [], "etf": [], "global_index": []}

    async def clear_price_history(self, code: str = None, data_type: str = None):
        async with self._price_lock:
            try:
                if code and data_type:
                    key = f"{data_type}:{code}"
                    history = await self._load_price_history_from_file()
                    history.pop(key, None)
                    await self._save_price_history_to_file(history)
                else:
                    if self.price_history_file.exists():
                        self.price_history_file.unlink()
            except Exception as e:
                logger.error(f"清除历史价格缓存失败: {e}")

    # ── 文件 I/O（仅 price_history）──

    async def _load_price_history_from_file(self) -> Dict[str, List[Dict]]:
        return await asyncio.to_thread(self._load_price_history_sync)

    def _load_price_history_sync(self) -> Dict[str, List[Dict]]:
        if not self.price_history_file.exists():
            return {}
        try:
            with open(self.price_history_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}

    async def _save_price_history_to_file(self, data: Dict[str, List[Dict]]):
        await asyncio.to_thread(self._save_price_history_sync, data)

    def _save_price_history_sync(self, data: Dict[str, List[Dict]]):
        try:
            with open(self.price_history_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存历史价格文件失败: {e}")


# 全局缓存服务实例
data_cache_service = DataCacheService()
