"""FundQuant 信号输出与SSE推送"""

import asyncio
import json
import uuid
from datetime import datetime, timedelta
from typing import AsyncGenerator, Optional, List, Dict
from loguru import logger

from ..core.enums import Direction
from ..core.models import FundSignal, FusionSignal
from ..data.storage import save_signal


class SignalOutputService:
    """信号输出服务"""

    def __init__(self):
        self._subscribers: List[asyncio.Queue] = []
        self._recent_signals: Dict[str, datetime] = {}  # fund_code -> 上次推送时间
        self._cooldown_seconds = 300  # 5分钟冷却

    def emit_signal(self, signal: FundSignal) -> str:
        """发射信号（持久化+推送）"""
        if not signal.signal_id:
            signal.signal_id = f"sig_{uuid.uuid4().hex[:12]}"
        signal.timestamp = datetime.now()

        # 冷却去重
        key = f"{signal.fund_code}:{signal.signal_type}"
        last = self._recent_signals.get(key)
        if last and (datetime.now() - last).total_seconds() < self._cooldown_seconds:
            return signal.signal_id

        self._recent_signals[key] = datetime.now()

        # 持久化
        try:
            save_signal(signal)
        except Exception as e:
            logger.warning(f"信号持久化失败: {e}")

        # 推送到所有订阅者
        payload = signal.model_dump_json()
        dead_queues = []
        for q in self._subscribers:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                dead_queues.append(q)
        for q in dead_queues:
            self._subscribers.remove(q)

        return signal.signal_id

    def emit_fusion(self, fusion: FusionSignal) -> Optional[str]:
        """发射融合信号"""
        signal = FundSignal(
            signal_id=f"fusion_{uuid.uuid4().hex[:12]}",
            fund_code=fusion.fund_code,
            fund_name=fusion.fund_name,
            signal_type="allocation",
            direction=fusion.direction,
            confidence=fusion.confidence,
            reason=fusion.reason,
            strategy_name="signal_fusion",
            risk_check_passed=fusion.risk_check_passed,
            risk_warnings=fusion.risk_warnings,
        )
        return self.emit_signal(signal)

    async def stream_signals(self) -> AsyncGenerator[str, None]:
        """SSE信号流"""
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.append(queue)
        try:
            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield payload
                except asyncio.TimeoutError:
                    yield json.dumps({"type": "heartbeat", "timestamp": datetime.now().isoformat()})
        except asyncio.CancelledError:
            pass
        finally:
            if queue in self._subscribers:
                self._subscribers.remove(queue)

    def format_signal(self, signal: FundSignal) -> dict:
        """格式化信号"""
        return {
            "signal_id": signal.signal_id,
            "timestamp": signal.timestamp.isoformat(),
            "fund": {
                "code": signal.fund_code,
                "name": signal.fund_name,
                "type": signal.fund_type,
            },
            "action": {
                "direction": signal.direction.value if hasattr(signal.direction, 'value') else signal.direction,
                "suggested_pct": signal.suggested_pct,
                "urgency": signal.urgency if hasattr(signal, 'urgency') else "medium",
            },
            "analysis": {
                "strategy": signal.strategy_name,
                "confidence": signal.confidence,
                "reason": signal.reason,
                "valid_until": (signal.timestamp + timedelta(days=3)).isoformat(),
            },
            "risk": {
                "check_passed": signal.risk_check_passed,
                "warnings": signal.risk_warnings,
            },
            "disclaimer": "本信号仅供参考，不构成投资建议。",
        }


# 全局单例
signal_output_service = SignalOutputService()
