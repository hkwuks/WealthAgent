"""风格漂移检测 — 因子回归 + 多窗口一致性 + Chow test

通用版，不依赖基金领域模型。核心输入：净值收益率序列 + 因子收益率字典。
"""
from __future__ import annotations

from typing import Optional
from dataclasses import dataclass, field


@dataclass
class DriftResult:
    """风格漂移检测结果"""
    passed: bool = True
    drift_score: float = 0.0
    chow_pvalue: float = 1.0
    window_scores: dict = field(default_factory=dict)
    alarm_windows: list = field(default_factory=list)
    multi_window_alarm: bool = False
    chow_alarm: bool = False
    reason: str = ""


class StyleDriftDetector:
    """风格漂移检测器

    基于 Rolling 回归的多窗口风格漂移检测：
    - 3 窗口协同: 60 日 / 120 日 / 250 日
    - 多窗口一致性: ≥2 窗口同时告警才判定漂移
    - Chow test: 结构性断点检测

    >>> d = StyleDriftDetector()
    >>> import numpy as np
    >>> nav = list(np.cumsum(np.random.randn(300) * 0.01) + 1)
    >>> factors = {"benchmark": list(np.cumsum(np.random.randn(300) * 0.008) + 1)}
    >>> r = d.check(nav, factors)
    >>> isinstance(r, DriftResult)
    True
    """

    def __init__(self, r2_threshold: float = 0.3):
        self.threshold = r2_threshold
        self.windows = {"short": 60, "medium": 120, "long": 250}
        self.chow_split_ratio = 0.5

    def check(self, nav_returns: list[float],
              factor_returns: dict[str, list[float]],
              label: str = "") -> DriftResult:
        """执行风格漂移检测

        Args:
            nav_returns: 净值/价格收益率序列（小数，如 0.01 表示 1%）
            factor_returns: {因子名: 收益率序列}
            label: 标识标签（用于调试）

        Returns:
            DriftResult
        """
        min_len = min(self.windows.values())
        if len(nav_returns) < min_len:
            return DriftResult(passed=True, reason=f"数据不足 {min_len} 日，跳过")

        # 多窗口检测
        window_alarms = []
        window_scores = {}
        for win_name, win_size in self.windows.items():
            if len(nav_returns) < win_size:
                continue
            score = self._rolling_drift(
                nav_returns[-win_size:],
                {k: v[-win_size:] for k, v in factor_returns.items()},
            )
            window_scores[win_name] = score
            if score > self.threshold:
                window_alarms.append(win_name)

        # Chow test
        chow_p = self._chow_test(nav_returns, factor_returns)

        multi_alarm = len(window_alarms) >= 2
        chow_alarm = chow_p < 0.05
        drift_score = max(window_scores.values()) if window_scores else 0.0

        if multi_alarm or chow_alarm:
            parts = []
            if window_scores:
                parts.append("窗口得分: " + ", ".join(f"{k}={v:.2f}" for k, v in window_scores.items()))
            if multi_alarm:
                parts.append(f"告警窗口: {', '.join(window_alarms)} (≥2)")
            if chow_alarm:
                parts.append(f"Chow test p={chow_p:.4f} < 0.05")
            return DriftResult(
                passed=False, drift_score=drift_score,
                chow_pvalue=chow_p, window_scores=window_scores,
                alarm_windows=window_alarms, multi_window_alarm=multi_alarm,
                chow_alarm=chow_alarm,
                reason="; ".join(parts),
            )

        return DriftResult(
            passed=True, drift_score=drift_score,
            chow_pvalue=chow_p, window_scores=window_scores,
            alarm_windows=window_alarms, multi_window_alarm=multi_alarm,
            chow_alarm=chow_alarm,
            reason=f"漂移得分 {drift_score:.2f} (阈值 {self.threshold})",
        )

    def _rolling_drift(self, nav: list[float], factors: dict[str, list[float]]) -> float:
        """对半分割窗口，比较前后半段 R² 变化"""
        n = len(nav)
        split = max(1, int(n * self.chow_split_ratio))
        r2_first = _r_squared(nav[:split], factors)
        r2_second = _r_squared(nav[split:], factors)
        if r2_first is None or r2_second is None:
            return 0.0
        return max(0.0, r2_first - r2_second)

    def _chow_test(self, nav: list[float], factors: dict[str, list[float]]) -> float:
        """Chow test 结构性断点检测，返回 p-value"""
        n = len(nav)
        if n < 30:
            return 1.0
        split = n // 2
        factor_list = list(factors.keys())
        if not factor_list:
            return 1.0

        X_list = [factors[f] for f in factor_list]
        min_len = min(len(v) for v in X_list) if X_list else 0
        if min_len < n:
            return 1.0

        X = _build_design_matrix(X_list, n)
        y = __import__("numpy").array(nav[-n:])
        k = X.shape[1]

        try:
            import numpy as np
            # 全样本
            beta = np.linalg.solve(X.T @ X, X.T @ y)
            rss_pooled = float(np.sum((y - X @ beta) ** 2))
            # 前半
            X1, y1 = X[:split], y[:split]
            beta1 = np.linalg.solve(X1.T @ X1, X1.T @ y1)
            rss1 = float(np.sum((y1 - X1 @ beta1) ** 2))
            # 后半
            X2, y2 = X[split:], y[split:]
            beta2 = np.linalg.solve(X2.T @ X2, X2.T @ y2)
            rss2 = float(np.sum((y2 - X2 @ beta2) ** 2))

            rss_ur = rss1 + rss2
            if rss_ur < 1e-10:
                return 1.0
            chow_stat = ((rss_pooled - rss_ur) / k) / (rss_ur / (n - 2 * k))
            if chow_stat <= 0:
                return 1.0
            try:
                from scipy import stats
                return float(1.0 - stats.f.cdf(chow_stat, k, n - 2 * k))
            except ImportError:
                return max(0.0, min(1.0, 1.0 / (1.0 + chow_stat / k)))
        except np.linalg.LinAlgError:
            return 1.0


# ── 工具函数 ──

def _r_squared(nav: list[float], factors: dict[str, list[float]]) -> float | None:
    """计算回归 R²: nav = α + Σβ_i * factor_i + ε"""
    n = len(nav)
    if n < 10:
        return None
    factor_list = list(factors.keys())
    if not factor_list:
        return None
    X_list = [factors[f] for f in factor_list]
    if any(len(v) < n for v in X_list):
        return None

    import numpy as np
    X = _build_design_matrix(X_list, n)
    y = np.array(nav[-n:], dtype=float)
    try:
        XtX = X.T @ X
        if np.linalg.cond(XtX) > 1e10:
            return 0.0
        beta = np.linalg.solve(XtX, X.T @ y)
        y_pred = X @ beta
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        return float(np.clip(1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0, 0.0, 1.0))
    except np.linalg.LinAlgError:
        return None


def _build_design_matrix(factor_arrays: list[list[float]], n: int):
    """构建设计矩阵 [1, f1, f2, ..., fk]"""
    import numpy as np
    cols = [np.ones(n)]
    for arr in factor_arrays:
        cols.append(np.array(arr[-n:], dtype=float))
    return np.column_stack(cols)


def demo():
    """风格漂移自检"""
    import numpy as np
    np.random.seed(42)
    nav = list(np.cumsum(np.random.randn(300) * 0.01) + 1)
    factors = {"benchmark": list(np.cumsum(np.random.randn(300) * 0.008) + 1)}

    d = StyleDriftDetector()
    r = d.check(nav, factors)
    print(f"[style_drift] 漂移得分={r.drift_score:.4f}, 通过={r.passed}")
    assert not r.passed or r.drift_score < 0.3
    print("[style_drift] ✅ 风格漂移检测通过")


if __name__ == "__main__":
    demo()
