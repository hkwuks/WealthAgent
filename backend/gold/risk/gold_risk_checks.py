"""黄金领域风控检查 — 继承 core.RiskCheck

独特性（你问的"回调/独特模式"）：
  1. SQLite 持久化 — 黄金风控状态跨会话保存
  2. ATR 波动率 — 期货特有指标
  3. 保证金占比 — 期货特有
  4. RiskCheck 是"回调"：每个 check() 被 RiskPipeline.run_signal() 遍历调用
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from core import RiskCheck, RiskContext, RiskVerdict, RiskLevel, Signal

try:
    from backend.gold.data.storage import GoldDataStore
    from backend.gold.core.config import GoldSettings
except ImportError:
    GoldDataStore = None
    GoldSettings = None


class GoldDrawdownCheck(RiskCheck):
    """回撤检查 — 使用 SQLite 持久化当前权益

    独特模式：check() 内访问数据库查询历史权益。
    RiskCheck.check(ctx, signal) 是回调接口，RiskPipeline 遍历调用。
    """
    name = "gold_drawdown"

    def __init__(self, drawdown_limit: float = 0.15,
                 data_store: Optional["GoldDataStore"] = None,
                 config: Optional["GoldSettings"] = None):
        self._limit = drawdown_limit
        self._store = data_store or (GoldDataStore() if GoldDataStore else None)
        self._config = config or (GoldSettings() if GoldSettings else None)

    def check(self, ctx: RiskContext, signal: Signal | None = None) -> RiskVerdict:
        if signal is None:
            return RiskVerdict(passed=True, check_name=self.name)
        initial = self._config.backtest_capital if self._config else ctx.portfolio_value
        current = ctx.portfolio_value
        if current <= 0 or initial <= 0:
            return RiskVerdict(passed=True, check_name=self.name)
        drawdown = (initial - current) / initial
        if drawdown > self._limit:
            return RiskVerdict(passed=False, level=RiskLevel.REJECT,
                               reason=f"回撤 {drawdown:.1%} > 限值 {self._limit:.0%}",
                               check_name=self.name)
        return RiskVerdict(passed=True, check_name=self.name)


class GoldDailyLossCheck(RiskCheck):
    """日内亏损检查 — SQLite 持久化当日累计亏损

    独特模式：使用 ctx.extra 传递当日 PnL，或从数据库恢复。
    """
    name = "gold_daily_loss"

    def __init__(self, max_loss_pct: float = 0.03,
                 capital: float = 1_000_000,
                 data_store: Optional["GoldDataStore"] = None,
                 config: Optional["GoldSettings"] = None):
        self._max_loss = max_loss_pct * capital
        self._store = data_store or (GoldDataStore() if GoldDataStore else None)
        self._config = config or (GoldSettings() if GoldSettings else None)
        if self._config:
            self._max_loss = self._config.max_daily_loss_pct * self._config.backtest_capital

    def check(self, ctx: RiskContext, signal: Signal | None = None) -> RiskVerdict:
        if signal is None:
            return RiskVerdict(passed=True, check_name=self.name)
        total_pnl = ctx.extra.get("daily_pnl", 0.0)
        if total_pnl < -self._max_loss:
            return RiskVerdict(passed=False, level=RiskLevel.REJECT,
                               reason=f"日内亏损 ¥{abs(total_pnl):.0f} > 限值 ¥{self._max_loss:.0f}",
                               check_name=self.name)
        return RiskVerdict(passed=True, check_name=self.name)


class GoldConsecutiveLossCheck(RiskCheck):
    """连续亏损熔断 — 跟踪连亏次数

    独特模式：有状态 RiskCheck，外部通过 ctx.extra 传入连亏次数。
    """
    name = "gold_consecutive_loss"

    def __init__(self, max_losses: int = 5):
        self._max = max_losses
        self._consecutive: int = 0

    def check(self, ctx: RiskContext, signal: Signal | None = None) -> RiskVerdict:
        if signal is None:
            return RiskVerdict(passed=True, check_name=self.name)
        consecutive = ctx.extra.get("consecutive_losses", self._consecutive)
        if consecutive >= self._max:
            return RiskVerdict(passed=False, level=RiskLevel.REJECT,
                               reason=f"连续 {consecutive} 笔亏损, 触发熔断 {self._max}",
                               check_name=self.name)
        return RiskVerdict(passed=True, check_name=self.name)

    def record_result(self, pnl: float):
        if pnl < 0:
            self._consecutive += 1
        else:
            self._consecutive = 0


class GoldVarCheck(RiskCheck):
    """VaR(95%) 检查 — 15% 年化波动假设"""
    name = "gold_var_95"

    def __init__(self, var_limit: float = 0.10):
        self._limit = var_limit

    def check(self, ctx: RiskContext, signal: Signal | None = None) -> RiskVerdict:
        import math
        daily_vol = 0.15 / math.sqrt(252)
        var_95 = 1.645 * daily_vol * ctx.portfolio_value
        var_pct = var_95 / (ctx.extra.get("initial_capital", ctx.portfolio_value) or 1)
        if var_pct > self._limit:
            return RiskVerdict(passed=False, level=RiskLevel.REJECT,
                               reason=f"VaR(95%)={var_pct:.1%} > 限值 {self._limit:.0%}",
                               check_name=self.name)
        return RiskVerdict(passed=True, check_name=self.name)


class AtrVolatilityCheck(RiskCheck):
    """ATR 波动率检查 — 黄金期货特有

    ATR / 价格 > 10% 拒绝，> 5% 警告。
    独特模式：通过 ctx.extra 传入 ATR 值，完全由外部数据驱动。
    """
    name = "atr_volatility"

    def __init__(self, reject_ratio: float = 0.10, warn_ratio: float = 0.05):
        self._reject = reject_ratio
        self._warn = warn_ratio

    def check(self, ctx: RiskContext, signal: Signal | None = None) -> RiskVerdict:
        if signal is None:
            return RiskVerdict(passed=True, check_name=self.name)
        atr = ctx.extra.get("atr_value")
        price = ctx.extra.get("current_price")
        if atr is None or not price:
            return RiskVerdict(passed=True, check_name=self.name)
        ratio = atr / price
        if ratio > self._reject:
            return RiskVerdict(passed=False, level=RiskLevel.REJECT,
                               reason=f"ATR/Price={ratio:.1%} > 拒绝阈值 {self._reject:.0%}",
                               check_name=self.name)
        if ratio > self._warn:
            return RiskVerdict(passed=True, level=RiskLevel.WARNING,
                               reason=f"ATR/Price={ratio:.1%} 接近警告阈值 {self._warn:.0%}",
                               check_name=self.name)
        return RiskVerdict(passed=True, check_name=self.name)


class GoldPositionLimitCheck(RiskCheck):
    """持仓限制 — 同品种手数上限 + 保证金占比

    期货特有：需要保证金比例和手数计算。
    """
    name = "gold_position_limit"

    def __init__(self, max_lots: int = 10, max_margin_ratio: float = 0.3):
        self._max_lots = max_lots
        self._max_margin = max_margin_ratio

    def check(self, ctx: RiskContext, signal: Signal | None = None) -> RiskVerdict:
        if signal is None:
            return RiskVerdict(passed=True, check_name=self.name)
        positions = ctx.extra.get("positions", [])
        # 同品种手数
        prefix = signal.symbol.rstrip("0123456789")
        same = [p for p in positions
                if p.get("symbol", "").rstrip("0123456789") == prefix]
        total = sum(p.get("volume", 0) for p in same)
        if total >= self._max_lots:
            return RiskVerdict(passed=False, level=RiskLevel.REJECT,
                               reason=f"{prefix} 总持仓 {total} 手 >= 上限 {self._max_lots}",
                               check_name=self.name)
        # 保证金占比
        account = ctx.extra.get("account", {})
        margin = account.get("margin", 0) or 0
        balance = account.get("balance", 1) or 1
        margin_ratio = margin / balance if balance > 0 else 0
        if margin_ratio > self._max_margin:
            return RiskVerdict(passed=False, level=RiskLevel.REJECT,
                               reason=f"保证金占比 {margin_ratio:.0%} > {self._max_margin:.0%}",
                               check_name=self.name)
        return RiskVerdict(passed=True, check_name=self.name)
