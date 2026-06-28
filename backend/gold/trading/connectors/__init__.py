"""
模拟交易连接器 — 统一适配器模式

支持后端:
  - ctp:      SimNow / openctp TTS（通过 CTP API）

使用:
    from backend.gold.trading.connectors import create_adapter
    adapter = create_adapter("ctp")
    await adapter.start()
"""
from backend.gold.trading.connectors.base import TradingAdapter
from backend.gold.trading.connectors.factory import create_adapter
from backend.gold.trading.connectors.ctp_adapter import CtpAdapter

__all__ = [
    "TradingAdapter", "create_adapter",
    "CtpAdapter",
]
