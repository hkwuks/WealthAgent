"""
订单管理器 — 信号 → 订单 → 成交 链路

状态机:
  PENDING → ACCEPTED/REJECTED → PARTIAL/FILLED → CANCELLED
"""

import uuid
from datetime import datetime
from typing import Optional

from backend.gold.core.models import (
    GoldSignal, GoldOrder, GoldTrade,
    OrderStatus, SignalDirection,
)
from backend.gold.data.storage import GoldDataStore
from loguru import logger


class OrderManager:
    """订单管理器 — 管理订单状态流转"""

    def __init__(self, data_store: GoldDataStore = None):
        self.data_store = data_store or GoldDataStore()
        self._orders: dict[str, GoldOrder] = {}
        self._trades: list[GoldTrade] = []

    def create_from_signal(self, signal: GoldSignal,
                           risk_reason: str = None) -> GoldOrder:
        """信号 → 订单（含风控结果）"""
        now = datetime.now()
        order_id = f"ORD_{now.strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"

        status = OrderStatus.REJECTED if risk_reason else OrderStatus.ACCEPTED

        order = GoldOrder(
            order_id=order_id,
            signal_id=signal.signal_id,
            strategy_id=signal.strategy_id,
            strategy_name=signal.strategy_name,
            symbol=signal.symbol,
            direction=signal.direction,
            price=signal.price,
            volume=signal.volume,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            reason=signal.reason,
            status=status,
            risk_check=risk_reason,
            created_at=now,
            updated_at=now,
        )
        self._orders[order_id] = order
        return order

    def fill(self, order_id: str, fill_price: float,
             fill_volume: int = None) -> Optional[GoldTrade]:
        """订单成交（全量或部分）"""
        order = self._orders.get(order_id)
        if not order or order.status in (OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED):
            return None

        fill_vol = fill_volume or order.volume
        remaining = order.volume - order.filled_volume
        fill_vol = min(fill_vol, remaining)

        trade = GoldTrade(
            trade_id=f"TRD_{order_id}_{order.filled_volume}",
            order_id=order_id,
            symbol=order.symbol,
            direction=order.direction,
            price=fill_price,
            volume=fill_vol,
            trade_time=datetime.now(),
        )
        self._trades.append(trade)

        order.filled_volume += fill_vol
        order.status = OrderStatus.FILLED if order.filled_volume >= order.volume else OrderStatus.PARTIAL
        order.updated_at = datetime.now()

        logger.info(f"成交: {order.symbol} {order.direction.value} {fill_vol}手 @{fill_price} "
                    f"({order.filled_volume}/{order.volume})")

        return trade

    def cancel(self, order_id: str, reason: str = "") -> bool:
        """撤销订单"""
        order = self._orders.get(order_id)
        if not order or order.status in (OrderStatus.FILLED, OrderStatus.CANCELLED):
            return False
        order.status = OrderStatus.CANCELLED
        order.updated_at = datetime.now()
        logger.info(f"撤单: {order_id} reason={reason}")
        return True

    def get_order(self, order_id: str) -> Optional[GoldOrder]:
        return self._orders.get(order_id)

    def get_open_orders(self, symbol: str = None) -> list[GoldOrder]:
        """获取未完结订单"""
        return [
            o for o in self._orders.values()
            if o.status in (OrderStatus.PENDING, OrderStatus.ACCEPTED, OrderStatus.PARTIAL)
            and (symbol is None or o.symbol == symbol)
        ]

    def get_trades(self, limit: int = 50) -> list[dict]:
        """获取最近成交"""
        return [t.model_dump() for t in self._trades[-limit:]]
