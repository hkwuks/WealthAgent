"""
模拟交易适配器 — 统一接口，支持 SimNow / openctp TTS 无缝切换

使用方式:
    adapter = create_adapter("simnow")
    adapter = create_adapter("openctp")
    await adapter.start()
    adapter.send_order(...)
    await adapter.stop()
"""

import abc
import asyncio
from typing import Callable, Optional

from backend.gold.core.models import GoldTickData, SignalDirection


class TradingAdapter(abc.ABC):
    """交易适配器抽象基类 — 所有模拟交易后端的统一接口"""

    def __init__(self):
        # 行情队列（asyncio 消费者从中取 tick）
        self.tick_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        # 事件回调（连接状态、订单、成交等通知）
        self.event_callback: Optional[Callable] = None
        # 行情回调挂钩（给 BarAssembler 用）
        self.on_tick_callback: Optional[Callable] = None

    # ── 行情 ──────────────────────────────────────────────

    @abc.abstractmethod
    def get_main_contract(self) -> str:
        """返回当前主力合约代码"""
        ...

    # ── 生命周期 ──────────────────────────────────────────

    @abc.abstractmethod
    async def start(self):
        """启动连接"""
        ...

    @abc.abstractmethod
    async def stop(self):
        """关闭连接"""
        ...

    # ── 下单 ──────────────────────────────────────────────

    @abc.abstractmethod
    def send_order(self, symbol: str, direction: SignalDirection,
                   price: float, volume: int,
                   order_ref: int = 0) -> int:
        """
        下单

        Returns:
            order_ref (正数=成功, -1=失败)
        """
        ...

    @abc.abstractmethod
    def cancel_order(self, symbol: str, order_ref: int,
                     front_id: int = 0, session_id: int = 0) -> int:
        """撤单"""
        ...

    # ── 查询 ──────────────────────────────────────────────

    @abc.abstractmethod
    async def query_positions(self, symbol: str = "") -> list[dict]:
        """查询持仓"""
        ...

    @abc.abstractmethod
    async def query_account(self) -> dict:
        """查询资金"""
        ...

    @abc.abstractmethod
    async def query_orders(self, symbol: str = "") -> list[dict]:
        """查询当日委托"""
        ...

    # ── 状态 ──────────────────────────────────────────────

    @abc.abstractmethod
    def get_status(self) -> dict:
        """获取连接状态"""
        ...

    # ── 内部回调（子类在收到行情时调用） ──────────────────

    def _on_tick(self, tick: GoldTickData):
        """行情回调 — 入队列 + 回调"""
        try:
            self.tick_queue.put_nowait(tick)
        except asyncio.QueueFull:
            pass
        if self.on_tick_callback:
            try:
                self.on_tick_callback(tick)
            except Exception as e:
                import logging
                logging.getLogger(__name__).debug(f"tick callback error: {e}")

    def _notify(self, msg: dict):
        """事件通知 → 异步回调"""
        if self.event_callback:
            loop = asyncio.get_event_loop()
            loop.call_soon_threadsafe(self.event_callback, msg)

    # ── 属性 ──────────────────────────────────────────────

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """适配器名称: ctp / xtquant"""
        ...
