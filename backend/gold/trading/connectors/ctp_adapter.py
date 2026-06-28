"""
CTP 适配器 — 封装 CtpClient 为 TradingAdapter 接口

q 与直接使用 CtpClient 的代码完全兼容，
  但新代码应当走 TradingAdapter / create_adapter。
"""
from backend.gold.trading.connectors.base import TradingAdapter
from backend.gold.trading.connectors.ctp_client import CtpClient
from backend.gold.trading.connectors.ctp_config import CtpConfig
from backend.gold.core.models import GoldTickData, SignalDirection


class CtpAdapter(TradingAdapter):
    """CTP 适配器 — 包装 CtpClient"""

    def __init__(self, config: CtpConfig, name: str = None):
        super().__init__()
        self._client = CtpClient(config)
        self._name = name or "simnow"

        # 把 CtpClient 的回调透传到 TradingAdapter
        self._client.on_tick_callback = self._on_client_tick
        self._client.event_callback = self._on_client_event

    def _on_client_tick(self, tick: GoldTickData):
        """CTP client 来的 tick → 走 adapter 的统一回调"""
        self._on_tick(tick)

    def _on_client_event(self, msg: dict):
        self._notify(msg)

    @property
    def client(self) -> CtpClient:
        """暴露底层 CtpClient（旧代码兼容需要）"""
        return self._client

    # ── TradingAdapter 接口 ───────────────────────────────

    @property
    def name(self) -> str:
        return self._name

    def get_main_contract(self) -> str:
        return self._client.get_main_contract()

    async def start(self):
        self._client.on_tick_callback = self._on_client_tick
        self._client.event_callback = self._on_client_event
        await self._client.start()

    async def stop(self):
        await self._client.stop()

    def send_order(self, symbol: str, direction: SignalDirection,
                   price: float, volume: int,
                   order_ref: int = 0) -> int:
        return self._client.send_order(symbol, direction, price, volume, order_ref)

    def cancel_order(self, symbol: str, order_ref: int,
                     front_id: int = 0, session_id: int = 0) -> int:
        return self._client.cancel_order(symbol, order_ref, front_id, session_id)

    async def query_positions(self, symbol: str = "") -> list[dict]:
        return await self._client.query_positions(symbol)

    async def query_account(self) -> dict:
        return await self._client.query_account()

    async def query_orders(self, symbol: str = "") -> list[dict]:
        return await self._client.query_orders(symbol)

    def get_status(self) -> dict:
        s = self._client.get_status()
        s["adapter"] = self._name
        return s
