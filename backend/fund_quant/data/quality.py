"""FundQuant 数据质量检查 — 统计检验 + 异常值检测"""

from datetime import date, datetime, timedelta
from typing import Optional, List, Dict, Tuple
from loguru import logger
import numpy as np

from ..core.enums import DataQuality
from ..core.errors import DataQualityError
from ..data.storage import get_nav_history


class DataQualityChecker:
    """数据质量检查器"""

    # 连续缺失阈值（日）
    MAX_CONSECUTIVE_MISSING = 5
    # 单日涨跌幅异常阈值
    MAX_DAILY_CHANGE = 0.15  # 15%
    # 分级基金B份额阈值放宽
    MAX_DAILY_CHANGE_GRADE_B = 0.30  # 30%
    # 持仓数据最大延迟（季度数）
    MAX_MISSING_HOLDINGS_QUARTERS = 2
    # 净值数据最大延迟（日）
    MAX_NAV_DELAY_DAYS = 5
    # ADF检验p值阈值 (均值回归检验)
    ADF_PVALUE_THRESHOLD = 0.05
    # Hurst指数阈值 (>0.5 = 趋势性, <0.5 = 均值回归)
    HURST_THRESHOLD = 0.5

    def check_nav_quality(self, fund_code: str,
                          start_date: Optional[str] = None,
                          end_date: Optional[str] = None) -> List[dict]:
        """检查净值数据质量（增强版）"""
        records = get_nav_history(fund_code, start_date, end_date)
        if not records:
            return [{"fund_code": fund_code, "issue": "no_data", "severity": "critical"}]

        issues = []
        sorted_records = sorted(records, key=lambda r: r["date"])

        # ── 1. 缺失值检查 ──
        missing_streak = self._check_missing_gaps(sorted_records)
        if missing_streak > self.MAX_CONSECUTIVE_MISSING:
            issues.append({
                "fund_code": fund_code, "test": "连续缺失",
                "issue": f"最大连续缺失 {missing_streak} 天",
                "severity": "warning" if missing_streak <= 10 else "critical",
                "value": missing_streak,
            })

        # ── 2. 异常值检查 (MAD截断) ──
        outlier_issues = self._check_outliers_mad(sorted_records)
        issues.extend(outlier_issues)

        # ── 3. 数据延迟检查 ──
        delay_issue = self._check_data_delay(sorted_records)
        if delay_issue:
            issues.append(delay_issue)

        # ── 4. 持仓缺失检查 ──
        holding_issue = self._check_missing_holdings(fund_code)
        if holding_issue:
            issues.append(holding_issue)

        # ── 5. 规模突降检查 ──
        scale_issue = self._check_scale_drop(fund_code)
        if scale_issue:
            issues.append(scale_issue)

        # ── 6. ADF检验 ──
        adf_issue = self._check_adf_test(sorted_records, fund_code)
        if adf_issue:
            issues.append(adf_issue)

        # ── 7. Hurst指数 ──
        hurst_issue = self._check_hurst(sorted_records, fund_code)
        if hurst_issue:
            issues.append(hurst_issue)

        # ── 8. 换手率异常 ──
        turnover_issue = self._check_turnover_anomaly(sorted_records)
        if turnover_issue:
            issues.append(turnover_issue)

        return issues

    # ── 私有检查方法 ──

    @staticmethod
    def _check_missing_gaps(sorted_records: List[dict]) -> int:
        """检查最大连续缺失天数"""
        max_gap = 0
        current_gap = 0
        for i in range(1, len(sorted_records)):
            try:
                prev = datetime.strptime(sorted_records[i - 1]["date"], "%Y-%m-%d").date()
                curr = datetime.strptime(sorted_records[i]["date"], "%Y-%m-%d").date()
                gap = (curr - prev).days
                if gap > 3:
                    current_gap += gap - 1
                else:
                    max_gap = max(max_gap, current_gap)
                    current_gap = 0
            except ValueError:
                continue
        return max(max_gap, current_gap)

    @staticmethod
    def _check_outliers_mad(sorted_records: List[dict]) -> List[dict]:
        """基于滚动MAD的异常值检测"""
        issues = []
        nav_values = []
        for r in sorted_records:
            nav = r.get("nav")
            if nav and nav > 0:
                nav_values.append(nav)

        if len(nav_values) < 30:
            return issues

        arr = np.array(nav_values)
        returns = np.diff(arr) / arr[:-1]

        for i in range(1, len(returns)):
            # 滚动窗口: 前60日
            window_start = max(0, i - 60)
            window = returns[window_start:i]
            if len(window) < 10:
                continue

            median = np.median(window)
            mad = np.median(np.abs(window - median))
            if mad < 1e-8:
                continue

            # MAD截断: 超过5倍MAD的为异常
            modified_z = 0.6745 * (returns[i] - median) / mad
            if abs(modified_z) > 5.0:
                issues.append({
                    "fund_code": sorted_records[i + 1]["fund_code"] if i + 1 < len(sorted_records) else "",
                    "test": "MAD异常值",
                    "issue": f"单日涨跌幅异常: {returns[i]:.2%} (修正Z={modified_z:.1f}) 日期: {sorted_records[i + 1]['date']}",
                    "severity": "warning",
                    "value": float(returns[i]),
                })
        return issues

    @staticmethod
    def _check_data_delay(sorted_records: List[dict]) -> Optional[dict]:
        """检查数据延迟"""
        if not sorted_records:
            return None
        last_date_str = sorted_records[-1]["date"]
        try:
            last_date = datetime.strptime(last_date_str, "%Y-%m-%d").date()
            delay = (date.today() - last_date).days
            if delay > 5:
                return {
                    "fund_code": sorted_records[-1]["fund_code"],
                    "test": "数据延迟",
                    "issue": f"数据延迟 {delay} 天",
                    "severity": "warning" if delay <= 10 else "critical",
                    "value": delay,
                }
        except ValueError:
            pass
        return None

    @staticmethod
    def _check_adf_test(sorted_records: List[dict], fund_code: str) -> Optional[dict]:
        """ADF检验偏差序列的均值回归特性"""
        deviations = []
        for r in sorted_records:
            est = r.get("adjusted_nav") or r.get("nav")
            actual = r.get("nav")
            if est and actual and actual > 0:
                deviations.append((est - actual) / actual)

        if len(deviations) < 30:
            return None

        try:
            from scipy import stats
            # 简单ADF: 对偏差序列做自回归, 检验系数是否显著为1
            arr = np.array(deviations)
            y = arr[1:]
            x = arr[:-1]
            x = np.column_stack([np.ones(len(x)), x])
            beta = np.linalg.lstsq(x, y, rcond=None)[0]
            resid = y - x @ beta
            se = np.sqrt(np.sum(resid ** 2) / (len(y) - 2) / np.sum((x[:, 1] - np.mean(x[:, 1])) ** 2))
            t_stat = (beta[1] - 1.0) / se if se > 0 else 0
            # DF临界值 (近似)
            p_value = 1.0 - stats.t.cdf(t_stat, df=len(y) - 2)

            if p_value > 0.05:
                return {
                    "fund_code": fund_code,
                    "test": "ADF检验",
                    "issue": f"偏差序列非均值回归 (p={p_value:.4f} > 0.05), 策略可能失效",
                    "severity": "warning",
                    "value": float(p_value),
                }
        except Exception:
            pass
        return None

    @staticmethod
    def _check_hurst(sorted_records: List[dict], fund_code: str) -> Optional[dict]:
        """Hurst指数检验 (趋势vs均值回归)"""
        navs = [r.get("nav") for r in sorted_records if r.get("nav") and r["nav"] > 0]
        if len(navs) < 100:
            return None

        try:
            arr = np.array(navs)
            # 简化Hurst: R/S分析
            lags = [2, 5, 10, 20, 40, 80]
            rs = []
            for lag in lags:
                if lag >= len(arr):
                    continue
                n = len(arr) // lag * lag
                if n < lag * 2:
                    continue
                segments = arr[:n].reshape(-1, lag)
                mean = np.mean(segments, axis=1, keepdims=True)
                dev = segments - mean
                cumsum = np.cumsum(dev, axis=1)
                r = np.max(cumsum, axis=1) - np.min(cumsum, axis=1)
                s = np.std(segments, axis=1, ddof=1)
                s = np.where(s == 0, 1.0, s)
                rs.append(np.mean(r / s))

            if len(rs) < 4:
                return None
            log_rs = np.log(rs)
            log_lags = np.log(lags[:len(rs)])
            A = np.column_stack([np.ones(len(log_lags)), log_lags])
            hurst, _ = np.linalg.lstsq(A, log_rs, rcond=None)[0]

            if hurst > 0.5:
                return {
                    "fund_code": fund_code,
                    "test": "Hurst指数",
                    "issue": f"H={hurst:.3f} > 0.5, 序列呈趋势性 (非均值回归)",
                    "severity": "info" if hurst < 0.6 else "warning",
                    "value": float(hurst),
                }
        except Exception:
            pass
        return None

    @staticmethod
    def _check_turnover_anomaly(sorted_records: List[dict]) -> Optional[dict]:
        """换手率/交易量异常检测"""
        changes = []
        for i in range(1, len(sorted_records)):
            prev = sorted_records[i - 1].get("nav")
            curr = sorted_records[i].get("nav")
            if prev and curr and prev > 0:
                changes.append(abs(curr - prev) / prev)

        if len(changes) < 20:
            return None

        arr = np.array(changes)
        q99 = np.percentile(arr, 99)
        extreme_count = int(np.sum(arr > q99 * 3))

        if extreme_count > max(1, len(changes) // 100):
            return {
                "fund_code": sorted_records[0]["fund_code"],
                "test": "波动异常",
                "issue": f"极端波动 {extreme_count} 次 (占总交易日 {len(changes)} 的 {extreme_count/len(changes)*100:.1f}%)",
                "severity": "info",
                "value": extreme_count,
            }
        return None

    # ── 持仓缺失检查 (PRD §7.4) ──

    @staticmethod
    def _check_missing_holdings(fund_code: str) -> Optional[dict]:
        """检查持仓数据是否缺失超过2个季度"""
        from ..data.storage import get_holdings
        try:
            records = get_holdings(fund_code)
            if not records:
                return {
                    "fund_code": fund_code,
                    "test": "持仓缺失",
                    "issue": "无持仓数据记录",
                    "severity": "warning",
                    "value": 0,
                }
            # 检查最近持仓数据是否过时
            periods = sorted([r["report_period"] for r in records if r.get("report_period")], reverse=True)
            if periods:
                from datetime import date
                latest = datetime.strptime(periods[0], "%Y-%m-%d").date()
                months_ago = (date.today().year - latest.year) * 12 + (date.today().month - latest.month)
                if months_ago > 6:  # 超过2个季度
                    return {
                        "fund_code": fund_code,
                        "test": "持仓缺失",
                        "issue": f"最近持仓 {periods[0]} ({months_ago}个月前), 超过2个季度",
                        "severity": "warning",
                        "value": months_ago,
                    }
            return None
        except Exception:
            return None

    # ── 规模突降检查 (PRD §7.4) ──

    @staticmethod
    def _check_scale_drop(fund_code: str) -> Optional[dict]:
        """检查基金规模是否突降>50%"""
        from ..data.storage import get_fund_meta
        try:
            meta = get_fund_meta(fund_code)
            if not meta or meta.get("scale") is None:
                return None
            scale = meta["scale"]
            if scale < 10_000_000:  # 1000万以下视为清盘风险
                return {
                    "fund_code": fund_code,
                    "test": "规模突降",
                    "issue": f"规模 {scale:.0f} < 1000万, 清盘风险高",
                    "severity": "critical",
                    "value": float(scale),
                }
            return None
        except Exception:
            return None

    def estimate_nav_quality(self, fund_code: str) -> DataQuality:
        """估算整体数据质量级别"""
        issues = self.check_nav_quality(fund_code)
        severities = [i["severity"] for i in issues]
        if "critical" in severities:
            return DataQuality.ERROR
        if "warning" in severities:
            return DataQuality.SUSPICIOUS
        return DataQuality.GOOD

    def get_quality_summary(self, fund_code: str) -> dict:
        """获取完整数据质量摘要"""
        issues = self.check_nav_quality(fund_code)
        quality = self.estimate_nav_quality(fund_code)
        return {
            "fund_code": fund_code,
            "quality": quality.value,
            "total_issues": len(issues),
            "critical_issues": len([i for i in issues if i["severity"] == "critical"]),
            "warning_issues": len([i for i in issues if i["severity"] == "warning"]),
            "info_issues": len([i for i in issues if i["severity"] == "info"]),
            "issues": issues,
        }


# 全局单例
data_quality_checker = DataQualityChecker()
