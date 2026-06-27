"""
全量风控 — 7 项检查

1. 回撤检查: 当前回护是否超过阈值 → REJECT
2. 日内亏损检查: 当日累计亏损是否超过阈值 → REJECT
3. 信号频率检查: 当日信号数是否超过上限 → REJECT
4. VaR检查: 持仓VaR(95%) 是否超过资金比例 → WARNING/REJECT
5. 波动率检查: ATR/价格 比例是否异常 → WARNING/REJECT
6. 持仓限制检查: 单品种手数/保证金占比上限 → REJECT
7. 连续亏损熔断: 连续亏损次数超过阈值 → REJECT
"""

from datetime import date
import numpy as np
from backend.gold.core.models import GoldSignal, RiskCheckResult, RiskLevel, SignalDirection
from backend.gold.data.storage import GoldDataStore
from backend.gold.core.config import GoldSettings
from loguru import logger


class RiskChecker:
    """全量风控 — 7 项检查 + 状态跟踪"""

    def __init__(self, config: GoldSettings = None, data_store: GoldDataStore = None):
        self.config = config or GoldSettings()
        self.data_store = data_store or GoldDataStore()
        # 内置状态跟踪（日内累计）
        self._daily_stats: dict[str, dict] = {}
        self._init_tables()

    def _init_tables(self):
        with self.data_store._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS risk_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id TEXT, strategy TEXT, symbol TEXT,
                    direction TEXT, level TEXT, reason TEXT,
                    created_at TEXT
                );
                CREATE TABLE IF NOT EXISTS risk_daily (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trade_date TEXT NOT NULL UNIQUE,
                    signal_count INTEGER DEFAULT 0,
                    total_pnl REAL DEFAULT 0,
                    consecutive_losses INTEGER DEFAULT 0,
                    equity REAL,
                    updated_at TEXT
                );
            """)

    # ── 主入口 ────────────────────────────────────────────────

    def check(self, signal: GoldSignal,
              current_equity: float = None,
              initial_capital: float = None,
              atr_value: float = None,
              current_price: float = None,
              positions: list = None,
              account: dict = None) -> RiskCheckResult:
        """
        全量风控入口

        缺失参数自动推断:
          - initial_capital 从 config.backtest_capital 取
          - current_equity 从 daily 状态恢复
          - positions/account 传了就查，不传跳过持仓限制
          - atr_value/current_price 传了就查，不传跳过波动率
        """
        if initial_capital is None:
            initial_capital = self.config.backtest_capital

        today = date.today().isoformat()
        daily = self._get_daily(today)

        checks = [
            self._check_drawdown(signal, current_equity, initial_capital),
            self._check_daily_loss(signal, daily),
            self._check_signal_frequency(signal, daily),
            self._check_var(signal, current_equity, initial_capital),
            self._check_volatility(signal, atr_value, current_price),
            self._check_position_limit(signal, positions, account),
            self._check_consecutive_loss(signal, daily),
        ]

        non_pass = [c for c in checks if c.get("level") != RiskLevel.PASS]
        if not non_pass:
            self._log(signal, "PASS", "所有风控检查通过")
            return RiskCheckResult(
                passed=True,
                risk_level=RiskLevel.PASS,
                reason="所有风控检查通过",
            )

        level_order = {RiskLevel.REJECT: 3, RiskLevel.WARNING: 2, RiskLevel.PASS: 1}
        worst = max(non_pass, key=lambda c: level_order.get(c["level"], 0))
        reasons = "; ".join(c["reason"] for c in non_pass if c.get("reason"))
        self._log(signal, worst["level"].value, reasons)

        return RiskCheckResult(
            passed=worst["level"] != RiskLevel.REJECT,
            risk_level=worst["level"],
            reason=reasons,
        )

    # ── 7 项检查 ──────────────────────────────────────────────

    def _check_drawdown(self, signal, current_equity, initial_capital):
        """1. 回撤检查"""
        if current_equity is None:
            with self.data_store._get_conn() as conn:
                row = conn.execute(
                    "SELECT equity FROM risk_daily ORDER BY id DESC LIMIT 1"
                ).fetchone()
            current_equity = row["equity"] if row else initial_capital

        if current_equity is None or initial_capital is None or initial_capital == 0:
            return {"passed": True, "level": RiskLevel.PASS, "reason": ""}

        drawdown = (initial_capital - current_equity) / initial_capital
        max_dd = self.config.max_drawdown_pct
        if drawdown > max_dd:
            return {"passed": False, "level": RiskLevel.REJECT,
                    "reason": f"回撤{drawdown*100:.1f}%超限{max_dd*100:.0f}%"}
        elif drawdown > max_dd * 0.8:
            return {"passed": True, "level": RiskLevel.WARNING,
                    "reason": f"回撤{drawdown*100:.1f}%接近限值{max_dd*100:.0f}%"}
        return {"passed": True, "level": RiskLevel.PASS, "reason": ""}

    def _check_daily_loss(self, signal, daily):
        """2. 日内亏损检查"""
        total_loss = daily.get("total_pnl", 0)
        max_loss = self.config.max_daily_loss_pct * self.config.backtest_capital

        if total_loss < -max_loss:
            return {"passed": False, "level": RiskLevel.REJECT,
                    "reason": f"日内亏损¥{abs(total_loss):.0f}超限¥{max_loss:.0f}"}
        elif total_loss < -max_loss * 0.8:
            return {"passed": True, "level": RiskLevel.WARNING,
                    "reason": f"日内亏损¥{abs(total_loss):.0f}接近限值¥{max_loss:.0f}"}
        return {"passed": True, "level": RiskLevel.PASS, "reason": ""}

    def _check_signal_frequency(self, signal, daily):
        """3. 信号频率检查 — 超限直接拒绝"""
        max_sig = self.config.max_daily_signals
        count = daily.get("signals", 0)

        if count >= max_sig:
            return {"passed": False, "level": RiskLevel.REJECT,
                    "reason": f"今日信号{count}次超过上限{max_sig}次"}
        elif count >= max_sig * 0.8:
            return {"passed": True, "level": RiskLevel.WARNING,
                    "reason": f"今日信号{count}次接近上限{max_sig}次"}
        return {"passed": True, "level": RiskLevel.PASS, "reason": ""}

    def _check_var(self, signal, current_equity, initial_capital):
        """4. VaR 检查 (95%置信度, 15%年化波动假设)"""
        if current_equity is None:
            return {"passed": True, "level": RiskLevel.PASS, "reason": ""}
        if initial_capital is None:
            initial_capital = current_equity

        daily_vol = 0.15 / np.sqrt(252)
        var_95 = 1.645 * daily_vol * current_equity
        var_pct = var_95 / initial_capital

        if var_pct > 0.10:
            return {"passed": False, "level": RiskLevel.REJECT,
                    "reason": f"VaR(95%)={var_pct*100:.1f}%超限10%"}
        elif var_pct > 0.05:
            return {"passed": True, "level": RiskLevel.WARNING,
                    "reason": f"VaR(95%)={var_pct*100:.1f}%接近限值5%"}
        return {"passed": True, "level": RiskLevel.PASS, "reason": ""}

    def _check_volatility(self, signal, atr_value, current_price):
        """5. 波动率检查"""
        if atr_value is None or current_price is None or current_price == 0:
            return {"passed": True, "level": RiskLevel.PASS, "reason": ""}
        vol_ratio = atr_value / current_price
        if vol_ratio > 0.10:
            return {"passed": False, "level": RiskLevel.REJECT,
                    "reason": f"波动率{vol_ratio*100:.1f}%超限10%"}
        elif vol_ratio > 0.05:
            return {"passed": True, "level": RiskLevel.WARNING,
                    "reason": f"波动率{vol_ratio*100:.1f}%接近限值5%"}
        return {"passed": True, "level": RiskLevel.PASS, "reason": ""}

    def _check_position_limit(self, signal, positions, account):
        """6. 持仓限制检查（持仓手数 + 保证金占比）"""
        cfg = self.config

        if positions:
            # 同品种总手数（去掉数字后缀对比，如 "au2608" → "au"）
            sym_prefix = signal.symbol.rstrip("0123456789")
            same_symbol = [p for p in positions
                           if p.get("symbol", "").rstrip("0123456789") == sym_prefix]
            total_lots = sum(p.get("volume", 0) for p in same_symbol)
            if total_lots >= cfg.max_position_lots:
                return {"passed": False, "level": RiskLevel.REJECT,
                        "reason": f"{sym_prefix}总持仓{total_lots}手已达上限{cfg.max_position_lots}手"}

            # 方向冲突警告（已有同向仓）
            for p in positions:
                if p.get("direction") == signal.direction.value and p.get("volume", 0) > 0:
                    return {"passed": True, "level": RiskLevel.WARNING,
                            "reason": f"已有{p['direction']}仓{p['volume']}手，加仓注意风险"}

        if account:
            margin = account.get("margin", 0) or 0
            balance = account.get("balance", 1) or 1
            if balance <= 0:
                balance = 1
            margin_ratio = margin / balance
            if margin_ratio > cfg.max_margin_ratio:
                return {"passed": False, "level": RiskLevel.REJECT,
                        "reason": f"保证金占比{margin_ratio*100:.0f}%超限{cfg.max_margin_ratio*100:.0f}%"}
            elif margin_ratio > cfg.max_margin_ratio * 0.8:
                return {"passed": True, "level": RiskLevel.WARNING,
                        "reason": f"保证金占比{margin_ratio*100:.0f}%接近限值{cfg.max_margin_ratio*100:.0f}%"}

        return {"passed": True, "level": RiskLevel.PASS, "reason": ""}

    def _check_consecutive_loss(self, signal, daily):
        """7. 连续亏损熔断"""
        consecutive = daily.get("consecutive_losses", 0)
        max_losses = self.config.max_consecutive_losses

        if consecutive >= max_losses:
            return {"passed": False, "level": RiskLevel.REJECT,
                    "reason": f"连续{consecutive}笔亏损已达熔断阈值{max_losses}"}
        elif consecutive >= max_losses - 1:
            return {"passed": True, "level": RiskLevel.WARNING,
                    "reason": f"连续{consecutive}笔亏损接近熔断阈值{max_losses}"}
        return {"passed": True, "level": RiskLevel.PASS, "reason": ""}

    # ── 外部回调（由交易系统调用，跟踪当日状态） ────────────

    def record_signal(self, signal: GoldSignal):
        """记录一次信号生成"""
        today = date.today().isoformat()
        daily = self._get_daily(today)
        daily["signals"] = daily.get("signals", 0) + 1
        self._save_daily(today, daily)

    def record_trade_result(self, direction: str, entry_price: float,
                            exit_price: float, volume: int):
        """记录一笔平仓盈亏"""
        today = date.today().isoformat()
        daily = self._get_daily(today)

        if direction == SignalDirection.LONG.value:
            pnl = (exit_price - entry_price) * volume * self.config.au_multiplier
        else:
            pnl = (entry_price - exit_price) * volume * self.config.au_multiplier

        daily["total_pnl"] = daily.get("total_pnl", 0) + pnl
        if pnl < 0:
            daily["consecutive_losses"] = daily.get("consecutive_losses", 0) + 1
        else:
            daily["consecutive_losses"] = 0

        self._save_daily(today, daily)
        logger.info(f"[风控] 记录交易: {direction} {volume}手 PnL=¥{pnl:.0f} "
                    f"日内累计=¥{daily['total_pnl']:.0f} 连亏={daily['consecutive_losses']}")

    def set_equity(self, equity: float):
        """更新当前权益"""
        today = date.today().isoformat()
        daily = self._get_daily(today)
        daily["equity"] = equity
        self._save_daily(today, daily)

    def get_daily_summary(self) -> dict:
        """获取当日风控摘要（供 API 展示）"""
        today = date.today().isoformat()
        daily = self._get_daily(today)
        return {
            "signal_count": daily.get("signals", 0),
            "total_pnl": daily.get("total_pnl", 0),
            "consecutive_losses": daily.get("consecutive_losses", 0),
            "equity": daily.get("equity"),
        }

    def get_check_config(self) -> list[dict]:
        """获取风控规则配置（供前端展示）"""
        cfg = self.config
        return [
            {"name": "最大回撤", "threshold": f"{cfg.max_drawdown_pct*100:.0f}%", "action": "拒绝", "status": "active"},
            {"name": "日内亏损", "threshold": f"¥{cfg.max_daily_loss_pct*cfg.backtest_capital:.0f}", "action": "拒绝", "status": "active"},
            {"name": "信号频率", "threshold": f"{cfg.max_daily_signals}/日", "action": "拒绝", "status": "active"},
            {"name": "单品种持仓上限", "threshold": f"{cfg.max_position_lots}手", "action": "拒绝", "status": "active"},
            {"name": "保证金占比上限", "threshold": f"{cfg.max_margin_ratio*100:.0f}%", "action": "拒绝", "status": "active"},
            {"name": "连续亏损熔断", "threshold": f"{cfg.max_consecutive_losses}次", "action": "拒绝", "status": "active"},
            {"name": "VaR(95%)", "threshold": "10%", "action": "警告/拒绝", "status": "active"},
            {"name": "波动率", "threshold": "10%", "action": "警告/拒绝", "status": "active"},
        ]

    # ── 内部 ──────────────────────────────────────────────────

    def _get_daily(self, today: str) -> dict:
        if today not in self._daily_stats:
            with self.data_store._get_conn() as conn:
                row = conn.execute(
                    "SELECT * FROM risk_daily WHERE trade_date = ?", (today,)
                ).fetchone()
            if row:
                self._daily_stats[today] = {
                    "signals": row["signal_count"],
                    "total_pnl": row["total_pnl"],
                    "consecutive_losses": row["consecutive_losses"],
                    "equity": row["equity"],
                }
            else:
                self._daily_stats[today] = {
                    "signals": 0, "total_pnl": 0.0,
                    "consecutive_losses": 0, "equity": None,
                }
        return self._daily_stats[today]

    def _save_daily(self, today: str, daily: dict):
        with self.data_store._get_conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO risk_daily
                   (trade_date, signal_count, total_pnl,
                    consecutive_losses, equity, updated_at)
                   VALUES (?, ?, ?, ?, ?, datetime('now'))""",
                (today, daily["signals"], daily["total_pnl"],
                 daily["consecutive_losses"], daily.get("equity"))
            )
            conn.commit()

    def _log(self, signal, level, reason):
        try:
            with self.data_store._get_conn() as conn:
                conn.execute(
                    """INSERT INTO risk_log
                       (signal_id, strategy, symbol, direction,
                        level, reason, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, datetime('now'))""",
                    (signal.signal_id, signal.strategy_name, signal.symbol,
                     signal.direction.value, level, reason)
                )
                conn.commit()
        except Exception as e:
            logger.debug(f"风控日志写入失败: {e}")
