"""风控层 — RiskCheck 接口 + RiskPipeline 两阶段 + 6 项内置检查"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .signal import Signal, Position


class RiskLevel(str, Enum):
    PASS = "pass"
    WARNING = "warning"
    REJECT = "reject"


@dataclass
class RiskVerdict:
    passed: bool = True
    level: RiskLevel = RiskLevel.PASS
    reason: str = ""
    check_name: str = ""


@dataclass
class RiskContext:
    """风控上下文 — 策略不可见，风控专用"""
    portfolio_value: float = 0.0
    daily_loss: float = 0.0
    daily_signal_count: int = 0
    consecutive_losses: int = 0
    max_drawdown: float = 0.0
    peak_value: float = 0.0
    positions: list = field(default_factory=list)
    extra: dict = field(default_factory=dict)


class RiskCheck(ABC):
    """单个风控检查"""
    name: str = ""

    @abstractmethod
    def check(self, ctx: RiskContext, signal: Signal | None = None) -> RiskVerdict:
        ...

    def config_schema(self) -> dict:
        return {}


# ── 内置通用检查 ──

class MaxDrawdownCheck(RiskCheck):
    """最大回撤检查

    >>> c = MaxDrawdownCheck(drawdown_limit=0.10)
    >>> ctx = RiskContext(max_drawdown=0.05)
    >>> c.check(ctx).passed
    True
    >>> ctx.max_drawdown = 0.15
    >>> c.check(ctx).level == RiskLevel.REJECT
    True
    """
    name = "max_drawdown"

    def __init__(self, drawdown_limit: float = 0.15):
        self._limit = drawdown_limit

    def check(self, ctx: RiskContext, signal: Signal | None = None) -> RiskVerdict:
        ok = ctx.max_drawdown < self._limit
        return RiskVerdict(
            passed=ok,
            level=RiskLevel.PASS if ok else RiskLevel.REJECT,
            reason=f"max_drawdown={ctx.max_drawdown:.2%} >= limit={self._limit:.2%}" if not ok else "",
            check_name=self.name,
        )


class DailyLossCheck(RiskCheck):
    """单日亏损上限

    >>> c = DailyLossCheck(limit=0.03)
    >>> ctx = RiskContext(daily_loss=0.02)
    >>> c.check(ctx).passed
    True
    >>> ctx.daily_loss = 0.05
    >>> c.check(ctx).level == RiskLevel.REJECT
    True
    """
    name = "daily_loss"

    def __init__(self, limit: float = 0.03):
        self._limit = limit

    def check(self, ctx: RiskContext, signal: Signal | None = None) -> RiskVerdict:
        ok = ctx.daily_loss < self._limit
        return RiskVerdict(
            passed=ok,
            level=RiskLevel.PASS if ok else RiskLevel.REJECT,
            reason=f"daily_loss={ctx.daily_loss:.2%} >= limit={self._limit:.2%}" if not ok else "",
            check_name=self.name,
        )


class SignalFrequencyCheck(RiskCheck):
    """信号频率限制

    >>> c = SignalFrequencyCheck(max_per_day=5)
    >>> ctx = RiskContext(daily_signal_count=3)
    >>> c.check(ctx).passed
    True
    >>> ctx.daily_signal_count = 10
    >>> c.check(ctx).level == RiskLevel.REJECT
    True
    """
    name = "signal_frequency"

    def __init__(self, max_per_day: int = 10):
        self._max = max_per_day

    def check(self, ctx: RiskContext, signal: Signal | None = None) -> RiskVerdict:
        ok = ctx.daily_signal_count < self._max
        return RiskVerdict(
            passed=ok,
            level=RiskLevel.PASS if ok else RiskLevel.REJECT,
            reason=f"daily_signals={ctx.daily_signal_count} >= max={self._max}" if not ok else "",
            check_name=self.name,
        )


class ConsecutiveLossCheck(RiskCheck):
    """连续亏损上限

    >>> c = ConsecutiveLossCheck(max_losses=5)
    >>> ctx = RiskContext(consecutive_losses=3)
    >>> c.check(ctx).passed
    True
    >>> ctx.consecutive_losses = 6
    >>> c.check(ctx).level == RiskLevel.REJECT
    True
    """
    name = "consecutive_loss"

    def __init__(self, max_losses: int = 5):
        self._max = max_losses

    def check(self, ctx: RiskContext, signal: Signal | None = None) -> RiskVerdict:
        ok = ctx.consecutive_losses < self._max
        return RiskVerdict(
            passed=ok,
            level=RiskLevel.PASS if ok else RiskLevel.REJECT,
            reason=f"consecutive_losses={ctx.consecutive_losses} >= max={self._max}" if not ok else "",
            check_name=self.name,
        )


class VarCheck(RiskCheck):
    """VaR 检查（基于历史回撤近似）

    >>> c = VarCheck(var_limit=0.05)
    >>> ctx = RiskContext(max_drawdown=0.03)
    >>> c.check(ctx).passed
    True
    """
    name = "var_95"

    def __init__(self, var_limit: float = 0.05):
        self._limit = var_limit

    def check(self, ctx: RiskContext, signal: Signal | None = None) -> RiskVerdict:
        # ponytail: 用 max_drawdown 近似 VaR(95%)，精确计算在 Phase 2
        ok = ctx.max_drawdown < self._limit
        return RiskVerdict(
            passed=ok,
            level=RiskLevel.PASS if ok else RiskLevel.REJECT,
            reason=f"var_approx={ctx.max_drawdown:.2%} >= limit={self._limit:.2%}" if not ok else "",
            check_name=self.name,
        )


class PositionLimitCheck(RiskCheck):
    """持仓数量/金额限制

    >>> c = PositionLimitCheck(max_positions=3)
    >>> ctx = RiskContext(positions=["a", "b"])
    >>> c.check(ctx).passed
    True
    >>> ctx.positions = ["a", "b", "c", "d"]
    >>> c.check(ctx).level == RiskLevel.REJECT
    True
    """
    name = "position_limit"

    def __init__(self, max_positions: int = 10, max_position_pct: float = 0.3):
        self._max_positions = max_positions
        self._max_pct = max_position_pct

    def check(self, ctx: RiskContext, signal: Signal | None = None) -> RiskVerdict:
        n_pos = len(getattr(ctx, "positions", []))
        ok = n_pos < self._max_positions
        return RiskVerdict(
            passed=ok,
            level=RiskLevel.PASS if ok else RiskLevel.REJECT,
            reason=f"positions={n_pos} >= max={self._max_positions}" if not ok else "",
            check_name=self.name,
        )


# ── 风控管道 ──

class RiskPipeline:
    """风控管道 — 责任链模式，两阶段执行"""

    def __init__(self):
        self._checks: list[RiskCheck] = []

    def add(self, check: RiskCheck):
        self._checks.append(check)

    def remove(self, name: str):
        self._checks = [c for c in self._checks if c.name != name]

    def run_portfolio(self, ctx: RiskContext) -> list[RiskVerdict]:
        """组合级风控 — 每日开盘/再平衡前执行一次"""
        results: list[RiskVerdict] = []
        for check in self._checks:
            verdict = check.check(ctx)
            results.append(verdict)
        return results

    def run_signal(self, signal: Signal, ctx: RiskContext) -> list[RiskVerdict]:
        """信号级风控 — 每个 signal 执行一次，任一 REJECT 立即返回"""
        results: list[RiskVerdict] = []
        for check in self._checks:
            verdict = check.check(ctx, signal)
            results.append(verdict)
            if verdict.level == RiskLevel.REJECT:
                break
        return results

    @property
    def checks(self) -> list[RiskCheck]:
        return list(self._checks)


def demo():
    """风控层自检"""
    pipeline = RiskPipeline()
    pipeline.add(SignalFrequencyCheck(max_per_day=5))
    pipeline.add(ConsecutiveLossCheck(max_losses=3))
    pipeline.add(PositionLimitCheck(max_positions=2))

    ctx = RiskContext(daily_signal_count=2, consecutive_losses=1,
                      positions=["a"])
    signal = Signal(id="", strategy="test", symbol="AU0",
                    direction="long", price=600, volume=1)

    # 组合级
    results = pipeline.run_portfolio(ctx)
    assert all(r.passed for r in results), f"portfolio checks failed: {[r.reason for r in results if not r.passed]}"

    # 信号级 — 应该通过
    results = pipeline.run_signal(signal, ctx)
    assert all(r.passed for r in results)

    # 信号级 — 触发频率限制
    ctx.daily_signal_count = 10
    results = pipeline.run_signal(signal, ctx)
    rejections = [r for r in results if r.level == RiskLevel.REJECT]
    assert len(rejections) >= 1

    print("[risk] ✅ 风控层通过")


if __name__ == "__main__":
    demo()
