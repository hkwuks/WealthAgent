"""
交易建议输出 — 结构化信号 + 持久化
"""

from backend.gold.core.models import GoldSignal, RiskCheckResult
from backend.gold.data.storage import GoldDataStore
from loguru import logger


class SignalOutput:
    """交易建议输出 — 结构化信号 + API返回"""

    def __init__(self, data_store: GoldDataStore = None):
        self.data_store = data_store or GoldDataStore()

    def output(self, signal: GoldSignal, risk_result: RiskCheckResult = None) -> dict:
        """
        输出交易建议

        保存信号到SQLite，返回结构化建议。
        """
        self.data_store.save_signal(signal)

        advice = {
            "signal_id": signal.signal_id,
            "strategy": signal.strategy_name,
            "symbol": signal.symbol,
            "direction": signal.direction.value,
            "price": signal.price,
            "volume": signal.volume,
            "stop_loss": signal.stop_loss,
            "take_profit": signal.take_profit,
            "confidence": signal.confidence,
            "reason": signal.reason,
            "risk_check": {
                "passed": risk_result.passed if risk_result else True,
                "level": risk_result.risk_level.value if risk_result else "pass",
                "reason": risk_result.reason if risk_result else "",
            },
            "timestamp": signal.created_at.isoformat() if signal.created_at else None,
        }

        logger.info(f"交易建议: {signal.direction.value} {signal.symbol} "
                    f"@{signal.price} sl={signal.stop_loss} "
                    f"conf={signal.confidence:.2f} "
                    f"risk={'PASS' if (risk_result and risk_result.passed) else 'WARN'}")

        return advice

    def get_recent_signals(self, strategy_id: str = None,
                           limit: int = 50) -> list[dict]:
        """获取最近交易建议"""
        signals = self.data_store.get_signals(strategy_id, limit)
        return signals
