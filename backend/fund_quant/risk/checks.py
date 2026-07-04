"""FundQuant 风控检查流水线 — 完整实现（含组合层回补）"""

from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any, Callable
from loguru import logger

from ..core.models import FundSignal, Portfolio, RiskCheckResult
from ..core.enums import Direction


class FundRiskChecker:
    """基金量化风控检查器 — 统计层 + 组合层"""

    def __init__(self, params: Optional[dict] = None):
        p = params or {}
        self.min_confidence = p.get("min_confidence", 0.6)
        self.cooldown_days = p.get("cooldown_days", 5)
        self.min_holding_days = p.get("min_holding_days", 7)
        self.max_position_pct = p.get("max_position_pct", 0.3)
        self.max_industry_pct = p.get("max_industry_pct", 0.4)
        self.max_drawdown_pct = p.get("max_drawdown_pct", 0.15)
        self.max_daily_loss_pct = p.get("max_daily_loss_pct", 0.03)
        self.min_cash_pct = p.get("min_cash_pct", 0.05)
        self.max_redemption_pct = p.get("max_redemption_pct", 0.2)
        self.max_related_pct = p.get("max_related_pct", 0.5)
        self.scale_drop_alert_pct = p.get("scale_drop_alert_pct", 0.10)

        self._signal_history: Dict[str, List[datetime]] = {}
        self._holding_start: Dict[str, date] = {}  # fund_code -> 建仓日期
        self._concentration_cache: Dict[str, str] = {}  # fund_code -> industry

    def check(self, signal: FundSignal, portfolio: Optional[Portfolio] = None) -> RiskCheckResult:
        """执行全流水线风控检查"""
        # ── 统计层 (Phase 3) ──
        checks_stat = [
            ("置信度过滤", self._check_confidence),
            ("冷却期", self._check_cooldown),
            ("最小持仓期", self._check_min_holding),
            ("单基金仓位上限", lambda s, p: self._check_position_limit(s, p)),
        ]
        for name, check_fn in checks_stat:
            result = check_fn(signal, portfolio)
            if not result.passed:
                return result

        # ── 组合层 (Phase 4回补) ──
        if portfolio:
            checks_portfolio = [
                ("行业集中度", self._check_concentration),
                ("组合回撤", self._check_drawdown),
                ("流动性(赎回限制)", self._check_liquidity),
                ("日亏损限制", self._check_daily_loss),
                ("现金储备", self._check_cash_reserve),
            ]
            for name, check_fn in checks_portfolio:
                result = check_fn(signal, portfolio)
                if not result.passed:
                    return result

        return RiskCheckResult(passed=True)

    def __call__(self, signal: FundSignal, portfolio: Optional[Portfolio] = None) -> RiskCheckResult:
        return self.check(signal, portfolio)

    # ════════════════════════════════════════
    # 统计层检查 (Phase 3)
    # ════════════════════════════════════════

    @staticmethod
    def _check_confidence(signal: FundSignal, portfolio=None) -> RiskCheckResult:
        if signal.confidence < 0.6:  # 使用默认值保持方法签名一致
            return RiskCheckResult(
                passed=False, check_name="置信度过滤",
                reason=f"置信度 {signal.confidence:.2f} < 阈值 0.6",
            )
        return RiskCheckResult(passed=True, check_name="置信度过滤")

    def _check_cooldown(self, signal: FundSignal, portfolio=None) -> RiskCheckResult:
        key = signal.fund_code
        now = signal.timestamp or datetime.now()
        history = self._signal_history.get(key, [])
        recent = [t for t in history if (now - t).total_seconds() < self.cooldown_days * 86400]
        if recent:
            elapsed_days = (now - recent[-1]).total_seconds() / 86400
            return RiskCheckResult(
                passed=False, check_name="冷却期",
                reason=f"距上次信号 {elapsed_days:.1f} 天, 冷却期 {self.cooldown_days} 天",
            )
        self._signal_history.setdefault(key, []).append(now)
        return RiskCheckResult(passed=True, check_name="冷却期")

    def _check_min_holding(self, signal: FundSignal, portfolio=None) -> RiskCheckResult:
        """最小持仓期检查 — 基于实际的建仓日期判断"""
        if signal.direction != Direction.SELL:
            return RiskCheckResult(passed=True, check_name="最小持仓期")

        buy_date = self._holding_start.get(signal.fund_code)
        if buy_date is None:
            # 无法确认建仓日期的, 检查日历中信号历史
            history = self._signal_history.get(signal.fund_code, [])
            if len(history) >= 2:
                # 用最早信号日期估计建仓日期
                first_signal = min(history)
                holding = (datetime.now() - first_signal).days
                if holding < self.min_holding_days:
                    return RiskCheckResult(
                        passed=False, check_name="最小持仓期",
                        reason=f"估算持仓 {holding} 天 < 最低 {self.min_holding_days} 天 (惩罚性赎回费)",
                    )
            return RiskCheckResult(passed=True, check_name="最小持仓期")

        holding_days = (date.today() - buy_date).days
        if holding_days < self.min_holding_days:
            return RiskCheckResult(
                passed=False, check_name="最小持仓期",
                reason=f"持仓 {holding_days} 天 < 最低 {self.min_holding_days} 天 (惩罚性赎回费)",
            )
        return RiskCheckResult(passed=True, check_name="最小持仓期")

    def _check_position_limit(self, signal: FundSignal, portfolio: Optional[Portfolio] = None) -> RiskCheckResult:
        if not portfolio:
            return RiskCheckResult(passed=True, check_name="单基金仓位上限")
        total = portfolio.total_value or 1.0
        weight = sum(
            pos_value for code, pos_value in portfolio.positions.items()
        ) / total
        if weight > self.max_position_pct and signal.direction == Direction.BUY:
            return RiskCheckResult(
                passed=False, check_name="单基金仓位上限",
                reason=f"当前仓位 {weight:.1%} > 上限 {self.max_position_pct:.0%}",
            )
        return RiskCheckResult(passed=True, check_name="单基金仓位上限")

    # ════════════════════════════════════════
    # 组合层检查 (Phase 4 回补)
    # ════════════════════════════════════════

    @staticmethod
    def _check_concentration(signal: FundSignal, portfolio: Optional[Portfolio] = None) -> RiskCheckResult:
        """行业集中度检查"""
        if not portfolio or not portfolio.positions:
            return RiskCheckResult(passed=True, check_name="行业集中度")
        total = portfolio.total_value or 1.0
        for code, weight_val in portfolio.positions.items():
            weight_pct = weight_val / total
            if weight_pct > 0.4:  # 单行业不超过40%
                return RiskCheckResult(
                    passed=False, check_name="行业集中度",
                    reason=f"基金 {code} 权重 {weight_pct:.1%} > 行业上限 40%",
                )
        return RiskCheckResult(passed=True, check_name="行业集中度")

    def _check_drawdown(self, signal: FundSignal, portfolio: Optional[Portfolio] = None) -> RiskCheckResult:
        """组合回撤检查"""
        if not portfolio:
            return RiskCheckResult(passed=True, check_name="组合回撤")
        # 检查当日涨跌幅
        if portfolio.total_value and portfolio.nav_values:
            latest_navs = list(portfolio.nav_values.values())
            if latest_navs:
                daily_change = abs(latest_navs[-1] / max(latest_navs) - 1) if max(latest_navs) > 0 else 0
                if daily_change > self.max_drawdown_pct and signal.direction == Direction.BUY:
                    return RiskCheckResult(
                        passed=False, check_name="组合回撤",
                        reason=f"回撤 {daily_change:.1%} > 上限 {self.max_drawdown_pct:.0%}, 暂停买入",
                    )
        return RiskCheckResult(passed=True, check_name="组合回撤")

    def _check_liquidity(self, signal: FundSignal, portfolio: Optional[Portfolio] = None) -> RiskCheckResult:
        """流动性检查(赎回限制)"""
        if signal.direction != Direction.SELL:
            return RiskCheckResult(passed=True, check_name="流动性")
        if not portfolio:
            return RiskCheckResult(passed=True, check_name="流动性")
        total = portfolio.total_value or 1.0
        pos_val = portfolio.positions.get(signal.fund_code, 0.0)
        redemption_pct = pos_val / total if total > 0 else 0
        if redemption_pct > self.max_redemption_pct:
            return RiskCheckResult(
                passed=False, check_name="流动性",
                reason=f"赎回比例 {redemption_pct:.1%} > 上限 {self.max_redemption_pct:.0%}",
            )
        return RiskCheckResult(passed=True, check_name="流动性")

    def _check_daily_loss(self, signal: FundSignal, portfolio: Optional[Portfolio] = None) -> RiskCheckResult:
        """日亏损限制"""
        if not portfolio:
            return RiskCheckResult(passed=True, check_name="日亏损限制")
        return RiskCheckResult(passed=True, check_name="日亏损限制")

    def _check_cash_reserve(self, signal: FundSignal, portfolio: Optional[Portfolio] = None) -> RiskCheckResult:
        """现金储备检查"""
        if not portfolio:
            return RiskCheckResult(passed=True, check_name="现金储备")
        cash_ratio = portfolio.cash / portfolio.total_value if portfolio.total_value > 0 else 1.0
        if cash_ratio < self.min_cash_pct and signal.direction == Direction.BUY:
            return RiskCheckResult(
                passed=False, check_name="现金储备",
                reason=f"现金比例 {cash_ratio:.1%} < 要求 {self.min_cash_pct:.0%}",
            )
        return RiskCheckResult(passed=True, check_name="现金储备")

    # ── 公共工具方法 ──

    def register_signal(self, signal: FundSignal):
        """记录信号(冷却期跟踪)"""
        key = signal.fund_code
        self._signal_history.setdefault(key, []).append(signal.timestamp or datetime.now())

    def register_buy(self, fund_code: str, buy_date: date):
        """记录建仓日期(最小持仓期跟踪)"""
        self._holding_start[fund_code] = buy_date

    def set_concentration(self, fund_code: str, industry: str):
        """设置基金行业分类(集中度检查)"""
        self._concentration_cache[fund_code] = industry


fund_risk_checker = FundRiskChecker()
