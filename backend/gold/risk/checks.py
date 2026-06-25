"""
简化风控 — 3项检查

1. 最大回撤检查: 当前回撤是否超过阈值 → REJECT
2. 日内亏损检查: 当日累计亏损是否超过阈值 → REJECT
3. 信号频率检查: 当日信号数是否超过上限 → WARNING(不拒绝)
"""

from datetime import date
from backend.gold.core.models import GoldSignal, RiskCheckResult, RiskLevel
from backend.gold.data.storage import GoldDataStore
from backend.gold.core.config import GoldSettings
from loguru import logger


class RiskChecker:
    """简化风控3检查"""

    def __init__(self, config: GoldSettings = None, data_store: GoldDataStore = None):
        self.config = config or GoldSettings()
        self.data_store = data_store or GoldDataStore()

    def check(self, signal: GoldSignal, current_equity: float = None,
              initial_capital: float = None) -> RiskCheckResult:
        """
        执行风控检查

        Returns: RiskCheckResult(passed, risk_level, reason)
        """
        checks = [
            self._check_drawdown(signal, current_equity, initial_capital),
            self._check_daily_loss(signal),
            self._check_signal_frequency(signal),
        ]

        failures = [c for c in checks if not c["passed"]]
        if not failures:
            return RiskCheckResult(
                passed=True,
                risk_level=RiskLevel.PASS,
                reason="所有风控检查通过",
            )

        # 按严重程度排序: REJECT > WARNING > PASS
        level_order = {RiskLevel.REJECT: 3, RiskLevel.WARNING: 2, RiskLevel.PASS: 1}
        worst = max(failures, key=lambda c: level_order.get(c["level"], 0))

        return RiskCheckResult(
            passed=worst["level"] != RiskLevel.REJECT,
            risk_level=worst["level"],
            reason="; ".join(f["reason"] for f in failures if f["reason"]),
        )

    def _check_drawdown(self, signal: GoldSignal, current_equity: float = None,
                        initial_capital: float = None) -> dict:
        """1. 最大回撤检查 — 回撤>10% → REJECT"""
        if current_equity is None or initial_capital is None or initial_capital == 0:
            return {"passed": True, "level": RiskLevel.PASS, "reason": ""}

        drawdown = (initial_capital - current_equity) / initial_capital
        max_dd = self.config.max_drawdown_pct

        if drawdown > max_dd:
            return {
                "passed": False,
                "level": RiskLevel.REJECT,
                "reason": f"回撤{drawdown*100:.1f}%超限{max_dd*100:.0f}%",
            }
        elif drawdown > max_dd * 0.8:
            return {
                "passed": True,
                "level": RiskLevel.WARNING,
                "reason": f"回撤{drawdown*100:.1f}%接近限值{max_dd*100:.0f}%",
            }
        return {"passed": True, "level": RiskLevel.PASS, "reason": ""}

    def _check_daily_loss(self, signal: GoldSignal) -> dict:
        """2. 日内亏损检查 — 日亏损>3% → REJECT"""
        today = signal.created_at.date() if signal.created_at else date.today()
        today_str = today.isoformat()

        signals_today = self.data_store.get_signals(strategy_id=None, limit=1000)
        daily_loss = 0
        for s in signals_today:
            if s.get("direction", "").startswith("close") and s.get("timestamp", "").startswith(today_str):
                daily_loss += s.get("pnl", 0)

        max_daily = self.config.max_daily_loss_pct
        capital = self.config.backtest_capital
        loss_pct = abs(min(daily_loss, 0)) / capital if capital > 0 else 0

        if loss_pct > max_daily:
            return {
                "passed": False,
                "level": RiskLevel.REJECT,
                "reason": f"日内亏损{loss_pct*100:.1f}%超限{max_daily*100:.0f}%",
            }
        return {"passed": True, "level": RiskLevel.PASS, "reason": ""}

    def _check_signal_frequency(self, signal: GoldSignal) -> dict:
        """3. 信号频率检查 — 日信号≥20 → WARNING(不拒绝)"""
        today = signal.created_at.date() if signal.created_at else date.today()
        today_str = today.isoformat()

        signals_today = self.data_store.get_signals(strategy_id=None, limit=1000)
        count = sum(1 for s in signals_today
                    if s.get("timestamp", "").startswith(today_str))

        max_signals = self.config.max_daily_signals
        if count >= max_signals:
            return {
                "passed": True,  # WARNING不拒绝
                "level": RiskLevel.WARNING,
                "reason": f"日内信号{count}次接近上限{max_signals}次",
            }
        return {"passed": True, "level": RiskLevel.PASS, "reason": ""}
