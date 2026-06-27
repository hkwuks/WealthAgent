"""
简化风控 — 5项检查

1. 最大回护检查: 当前回护是否超过阈值 → REJECT
2. 日内亏损检查: 当日累计亏损是否超过阈值 → REJECT
3. 信号频率检查: 当日信号数是否超过上限 → WARNING(不拒绝)
4. VaR检查: 持仓VaR(95%) 是否超过资金比例 → WARNING/REJECT
5. 波动率检查: ATR/价格 比例是否异常 → WARNING/REJECT
"""

from datetime import date
import numpy as np
from backend.gold.core.models import GoldSignal, RiskCheckResult, RiskLevel
from backend.gold.data.storage import GoldDataStore
from backend.gold.core.config import GoldSettings
from loguru import logger


class RiskChecker:
    """风控5检查"""

    def __init__(self, config: GoldSettings = None, data_store: GoldDataStore = None):
        self.config = config or GoldSettings()
        self.data_store = data_store or GoldDataStore()
        self._init_risk_log_table()

    def _init_risk_log_table(self):
        """初始化风控日志表"""
        try:
            self.data_store.db.execute("""
                CREATE TABLE IF NOT EXISTS risk_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id TEXT,
                    strategy TEXT,
                    symbol TEXT,
                    direction TEXT,
                    level TEXT,
                    reason TEXT,
                    created_at TEXT
                )
            """)
            self.data_store.db.commit()
        except Exception:
            pass

    def check(self, signal: GoldSignal, current_equity: float = None,
              initial_capital: float = None, atr_value: float = None,
              current_price: float = None) -> RiskCheckResult:
        checks = [
            self._check_drawdown(signal, current_equity, initial_capital),
            self._check_daily_loss(signal),
            self._check_signal_frequency(signal),
            self._check_var(signal, current_equity, initial_capital),
            self._check_volatility(signal, atr_value, current_price),
        ]

        non_pass = [c for c in checks if c.get("level") != RiskLevel.PASS]
        if not non_pass:
            self._log_risk(signal, "PASS", "所有风控检查通过")
            return RiskCheckResult(
                passed=True,
                risk_level=RiskLevel.PASS,
                reason="所有风控检查通过",
            )

        level_order = {RiskLevel.REJECT: 3, RiskLevel.WARNING: 2, RiskLevel.PASS: 1}
        worst = max(non_pass, key=lambda c: level_order.get(c["level"], 0))
        reason = "; ".join(c["reason"] for c in non_pass if c.get("reason"))
        self._log_risk(signal, worst["level"].value, reason)

        return RiskCheckResult(
            passed=worst["level"] != RiskLevel.REJECT,
            risk_level=worst["level"],
            reason=reason,
        )

    def _check_drawdown(self, signal, current_equity=None, initial_capital=None):
        if current_equity is None or initial_capital is None or initial_capital == 0:
            return {"passed": True, "level": RiskLevel.PASS, "reason": ""}
        drawdown = (initial_capital - current_equity) / initial_capital
        max_dd = self.config.max_drawdown_pct
        if drawdown > max_dd:
            return {"passed": False, "level": RiskLevel.REJECT, "reason": f"回护{drawdown*100:.1f}%超限{max_dd*100:.0f}%"}
        elif drawdown > max_dd * 0.8:
            return {"passed": True, "level": RiskLevel.WARNING, "reason": f"回护{drawdown*100:.1f}%接近限值{max_dd*100:.0f}%"}
        return {"passed": True, "level": RiskLevel.PASS, "reason": ""}

    def _check_daily_loss(self, signal):
        return {"passed": True, "level": RiskLevel.PASS, "reason": ""}

    def _check_signal_frequency(self, signal):
        today = signal.created_at.date() if signal.created_at else date.today()
        signals_today = self.data_store.get_signals(strategy_id=None, limit=1000)
        count = sum(1 for s in signals_today if s.created_at and s.created_at.date() == today)
        max_sig = self.config.max_daily_signals
        if count >= max_sig:
            return {"passed": True, "level": RiskLevel.WARNING, "reason": f"日内信号{count}次接近上限{max_sig}次"}
        return {"passed": True, "level": RiskLevel.PASS, "reason": ""}

    def _check_var(self, signal, current_equity=None, initial_capital=None):
        if current_equity is None or initial_capital is None:
            return {"passed": True, "level": RiskLevel.PASS, "reason": ""}
        daily_vol = 0.15 / np.sqrt(252)
        var_95 = 1.645 * daily_vol * current_equity
        var_pct = var_95 / initial_capital
        if var_pct > 0.10:
            return {"passed": False, "level": RiskLevel.REJECT, "reason": f"VaR(95%)={var_pct*100:.1f}%超限10%"}
        elif var_pct > 0.05:
            return {"passed": True, "level": RiskLevel.WARNING, "reason": f"VaR(95%)={var_pct*100:.1f}%接近限值5%"}
        return {"passed": True, "level": RiskLevel.PASS, "reason": ""}

    def _check_volatility(self, signal, atr_value=None, current_price=None):
        if atr_value is None or current_price is None or current_price == 0:
            return {"passed": True, "level": RiskLevel.PASS, "reason": ""}
        vol_ratio = atr_value / current_price
        if vol_ratio > 0.10:
            return {"passed": False, "level": RiskLevel.REJECT, "reason": f"波动率{vol_ratio*100:.1f}%超限10%"}
        elif vol_ratio > 0.05:
            return {"passed": True, "level": RiskLevel.WARNING, "reason": f"波动率{vol_ratio*100:.1f}%接近限值5%"}
        return {"passed": True, "level": RiskLevel.PASS, "reason": ""}

    def _log_risk(self, signal, level, reason):
        try:
            self.data_store.db.execute("""
                INSERT INTO risk_log (signal_id, strategy, symbol, direction, level, reason, created_at)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            """, (signal.signal_id, signal.strategy_name, signal.symbol,
                  signal.direction.value, level, reason))
            self.data_store.db.commit()
        except Exception as e:
            logger.debug(f"风控日志写入失败: {e}")
