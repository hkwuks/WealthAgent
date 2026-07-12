"""
实盘执行器 — 信号 → 风控 → TradingAdapter 下单 → 成交跟踪

流程:
  GoldSignal → RiskCheck → OrderManager.create_from_signal
    → TradingAdapter.send_order → 等待回报 → OrderManager.fill
"""
import time
from typing import Optional

from backend.gold.core.models import (
    GoldSignal, GoldOrder, GoldTrade, OrderStatus,
)
from backend.gold.risk.order_manager import OrderManager
from backend.gold.trading.connectors import TradingAdapter
from backend.gold.trading.execution.sim_account import InternalSimAccount
from loguru import logger


class LiveExecutor:
    """实盘执行器"""

    def __init__(self, adapter: TradingAdapter,
                 order_manager: OrderManager,
                 sim_account: InternalSimAccount = None):
        self.adapter = adapter
        self.om = order_manager
        self.sim = sim_account or InternalSimAccount()
        self._ref_counter: int = 0

    def execute(self, signal: GoldSignal, market_price: float = 0) -> dict:
        """
        执行信号

        1. 创建订单
        2. 发送到交易后端（CTP / QMT）
        3. 运行内部模拟
        4. 返回执行结果

        Args:
            signal: 已通过风控的信号
            market_price: 当前市场价（用于内部模拟）

        Returns:
            执行结果 dict
        """
        order = self.om.create_from_signal(signal)

        if order.status == OrderStatus.REJECTED:
            return {"order": order, "executed": False, "reason": "风控拒绝"}

        # 发送到交易后端
        self._ref_counter += 1
        ref = self.adapter.send_order(
            symbol=signal.symbol,
            direction=signal.direction,
            price=signal.price,
            volume=signal.volume,
            order_ref=self._ref_counter,
        )

        executed = ref > 0
        ctp_status = "sent" if executed else "failed"

        # 内部模拟
        sim_trade = None
        if executed and market_price > 0:
            sim_trade = self.sim.simulate_fill(signal, market_price)
            if sim_trade:
                self.om.fill(order.order_id, sim_trade.price, sim_trade.volume)

        return {
            "order": order.model_dump(),
            "executed": executed,
            "ctp_ref": ref,
            "ctp_status": ctp_status,
            "sim_trade": sim_trade.model_dump() if sim_trade else None,
        }
