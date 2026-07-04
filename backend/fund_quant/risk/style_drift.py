"""风格漂移检测 — Rolling回归 + 多窗口一致性 + Chow test"""

from typing import Optional, Dict, List, Tuple
from datetime import date
from loguru import logger
import numpy as np

from ..core.models import RiskCheckResult


class StyleDriftDetector:
    """风格漂移检测器

    基于Rolling回归的基金风格漂移检测:
    - 3窗口协同: 60日/120日/250日
    - 多窗口一致性: ≥2窗口同时告警才判定漂移
    - Chow test: 结构性断点检测
    """

    def __init__(self, style_r2_threshold: float = 0.3):
        self.threshold = style_r2_threshold
        self._drift_cache: Dict[str, float] = {}
        self._chow_cache: Dict[str, List[float]] = {}

        # 多窗口配置
        self.windows = {
            "short": 60,
            "medium": 120,
            "long": 250,
        }
        # Chow test 分割点（窗口后半部分）
        self.chow_split_ratio = 0.5

    def check(self, fund_code: str, nav_returns: List[float],
              factor_returns: Dict[str, List[float]]) -> RiskCheckResult:
        """执行风格漂移检测"""
        if len(nav_returns) < min(self.windows.values()):
            return RiskCheckResult(
                passed=True, check_name="风格漂移",
                reason=f"数据不足{min(self.windows.values())}日，跳过检测",
            )

        # 1. 多窗口一致性检测
        window_alarms = []
        window_scores = {}
        for win_name, win_size in self.windows.items():
            if len(nav_returns) < win_size:
                continue
            score = self._rolling_regression_drift(
                nav_returns[-win_size:],
                {k: v[-win_size:] for k, v in factor_returns.items()},
                win_size,
            )
            window_scores[win_name] = score
            if score > self.threshold:
                window_alarms.append(win_name)

        # 2. Chow test 结构性断点检测
        chow_pvalue = self._chow_test(nav_returns, factor_returns)
        self._chow_cache[fund_code] = [chow_pvalue]

        # 3. 综合判定: 至少2个窗口同时告警 或 Chow test显著
        multi_window_alarm = len(window_alarms) >= 2
        chow_alarm = chow_pvalue < 0.05  # 5%显著性水平

        drift_score = max(window_scores.values()) if window_scores else 0.0
        self._drift_cache[fund_code] = drift_score

        if multi_window_alarm or chow_alarm:
            reason_parts = []
            if window_scores:
                reason_parts.append(f"窗口得分: {', '.join(f'{k}={v:.2f}' for k, v in window_scores.items())}")
            if multi_window_alarm:
                reason_parts.append(f"告警窗口: {', '.join(window_alarms)} (≥2)")
            if chow_alarm:
                reason_parts.append(f"Chow test p={chow_pvalue:.4f} < 0.05")

            return RiskCheckResult(
                passed=False, check_name="风格漂移",
                reason=f"风格漂移检测: {'; '.join(reason_parts)}",
                details={
                    "window_scores": window_scores,
                    "alarm_windows": window_alarms,
                    "multi_window_alarm": multi_window_alarm,
                    "chow_pvalue": round(chow_pvalue, 4),
                    "chow_alarm": chow_alarm,
                },
            )

        return RiskCheckResult(
            passed=True, check_name="风格漂移",
            reason=f"漂移得分 {drift_score:.2f} (阈值 {self.threshold}), 多窗口一致",
            details={
                "window_scores": window_scores,
                "alarm_windows": window_alarms,
                "multi_window_alarm": multi_window_alarm,
                "chow_pvalue": round(chow_pvalue, 4),
            },
        )

    def _rolling_regression_drift(self, nav_returns: List[float],
                                    factor_returns: Dict[str, List[float]],
                                    window_size: int) -> float:
        """Rolling回归计算漂移得分

        对半分割窗口, 比较前后半段R²变化:
        - R²下降 > threshold → 风格漂移
        """
        if len(nav_returns) < window_size * self.chow_split_ratio:
            return 0.0

        split = int(len(nav_returns) * self.chow_split_ratio)

        # 前半段R²
        r2_first = self._r_squared(nav_returns[:split], factor_returns)
        # 后半段R²
        r2_second = self._r_squared(nav_returns[split:], factor_returns)

        if r2_first is None or r2_second is None:
            return 0.0

        # R²下降量作为漂移得分
        drift = max(0.0, r2_first - r2_second)
        return drift

    @staticmethod
    def _r_squared(nav_returns: List[float],
                   factor_returns: Dict[str, List[float]]) -> Optional[float]:
        """计算回归R²: nav = α + Σβ_i * factor_i + ε"""
        n = len(nav_returns)
        if n < 10:
            return None

        # 构建设计矩阵
        factors = list(factor_returns.keys())
        if not factors:
            return None

        # 确保所有因子序列长度一致
        X_list = []
        for f in factors:
            fr = factor_returns[f]
            if len(fr) < n:
                return None
            X_list.append(fr[-n:])

        X = np.column_stack([np.ones(n)] + X_list)
        y = np.array(nav_returns[-n:])

        try:
            # OLS: β = (X'X)^(-1)X'y
            XtX = X.T @ X
            if np.linalg.cond(XtX) > 1e10:
                return 0.0  # 共线性过强
            beta = np.linalg.solve(XtX, X.T @ y)
            y_pred = X @ beta
            ss_res = np.sum((y - y_pred) ** 2)
            ss_tot = np.sum((y - np.mean(y)) ** 2)
            r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
            return float(np.clip(r2, 0.0, 1.0))
        except np.linalg.LinAlgError:
            return None

    @staticmethod
    def _chow_test(nav_returns: List[float],
                    factor_returns: Dict[str, List[float]]) -> float:
        """Chow test 结构性断点检测

        原假设H₀: 两段回归系数相同 (无结构性断点)
        返回p-value, 越小越可能断点
        """
        n = len(nav_returns)
        if n < 30:
            return 1.0

        split = n // 2
        factors = list(factor_returns.keys())
        if not factors:
            return 1.0

        # 构建矩阵
        X_list = []
        for f in factors:
            fr = factor_returns[f]
            if len(fr) < n:
                return 1.0
            X_list.append(fr[-n:])

        X = np.column_stack([np.ones(n)] + X_list)
        y = np.array(nav_returns[-n:])
        k = X.shape[1]  # 参数个数

        try:
            # 全样本回归
            beta = np.linalg.solve(X.T @ X, X.T @ y)
            resid = y - X @ beta
            rss_pooled = float(np.sum(resid ** 2))

            # 前半段回归
            X1 = X[:split]
            y1 = y[:split]
            beta1 = np.linalg.solve(X1.T @ X1, X1.T @ y1)
            rss1 = float(np.sum((y1 - X1 @ beta1) ** 2))

            # 后半段回归
            X2 = X[split:]
            y2 = y[split:]
            beta2 = np.linalg.solve(X2.T @ X2, X2.T @ y2)
            rss2 = float(np.sum((y2 - X2 @ beta2) ** 2))

            # Chow统计量
            rss_ur = rss1 + rss2
            if rss_ur < 1e-10:
                return 1.0

            chow_stat = ((rss_pooled - rss_ur) / k) / (rss_ur / (n - 2 * k))
            if chow_stat <= 0:
                return 1.0

            # F分布→p-value (简化: 使用scipy或近似)
            try:
                from scipy import stats
                p_value = 1.0 - stats.f.cdf(chow_stat, k, n - 2 * k)
            except ImportError:
                # 无scipy时使用近似
                p_value = max(0.0, min(1.0, 1.0 / (1.0 + chow_stat / k)))
            return float(p_value)

        except np.linalg.LinAlgError:
            return 1.0

    def get_drift_score(self, fund_code: str) -> Optional[float]:
        """获取缓存漂移得分"""
        return self._drift_cache.get(fund_code)

    def get_chow_pvalue(self, fund_code: str) -> Optional[float]:
        """获取Chow test p-value"""
        vals = self._chow_cache.get(fund_code)
        return vals[-1] if vals else None


style_drift_detector = StyleDriftDetector()
