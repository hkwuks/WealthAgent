"""
数据质量检查 — 监测 K 线数据异常

检查项:
- OHLC 一致性 (high >= max(open,close), low <= min(open,close))
- 跳空检测 (涨跌幅 > threshold → 标记)
- 异常值过滤 (价差 > 3*ATR → 标记)
- 非交易日过滤
"""

from typing import Optional
from dataclasses import dataclass, field

from backend.gold.core.models import GoldBarData
from loguru import logger


@dataclass
class DataQualityReport:
    """数据质量报告"""
    total_bars: int = 0
    ohlc_errors: list = field(default_factory=list)
    gaps: list = field(default_factory=list)
    outliers: list = field(default_factory=list)
    weekend_bars: list = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not any([self.ohlc_errors, self.outliers])

    @property
    def summary(self) -> str:
        parts = []
        if self.ohlc_errors:
            parts.append(f"OHLC不一致 x{len(self.ohlc_errors)}")
        if self.gaps:
            parts.append(f"跳空 x{len(self.gaps)}")
        if self.outliers:
            parts.append(f"异常值 x{len(self.outliers)}")
        if self.weekend_bars:
            parts.append(f"周末数据 x{len(self.weekend_bars)}")
        return ", ".join(parts) if parts else "OK"


class DataQualityChecker:
    """K 线数据质量检查"""

    GAP_THRESHOLD = 0.05    # 5% 跳空
    OUTLIER_ATR_RATIO = 3.0  # 3×ATR 为异常
    MIN_BARS = 20

    def check(self, bars: list[GoldBarData]) -> DataQualityReport:
        """检查整批 K 线数据"""
        report = DataQualityReport(total_bars=len(bars))

        if len(bars) < self.MIN_BARS:
            logger.warning(f"数据不足 {self.MIN_BARS} 根，跳过质量检查")
            return report

        # 1. OHLC 一致性
        for i, b in enumerate(bars):
            if b.high < max(b.open, b.close) or b.low > min(b.open, b.close):
                report.ohlc_errors.append({
                    "idx": i, "datetime": str(b.datetime),
                    "o": b.open, "h": b.high, "l": b.low, "c": b.close,
                })

        # 2. 跳空检测
        for i in range(1, len(bars)):
            prev_close = bars[i-1].close
            if prev_close == 0:
                continue
            gap = (bars[i].open - prev_close) / prev_close
            if abs(gap) > self.GAP_THRESHOLD:
                report.gaps.append({
                    "idx": i,
                    "date": str(bars[i].datetime),
                    "gap_pct": round(gap * 100, 2),
                })

        # 3. 异常值 (HL spread > 3×ATR)
        atr = self._calc_atr(bars)
        if atr > 0:
            for i, b in enumerate(bars):
                spread = b.high - b.low
                if spread > self.OUTLIER_ATR_RATIO * atr:
                    report.outliers.append({
                        "idx": i,
                        "date": str(b.datetime),
                        "spread": round(spread, 2),
                        "atr": round(atr, 2),
                        "ratio": round(spread / atr, 1),
                    })

        # 4. 周末数据过滤
        for i, b in enumerate(bars):
            if b.datetime.weekday() >= 5:  # 5=Sat, 6=Sun
                report.weekend_bars.append({
                    "idx": i,
                    "date": str(b.datetime),
                    "weekday": b.datetime.strftime("%A"),
                })

        if not report.passed:
            logger.warning(f"数据质量问题: {report.summary}")

        return report

    @staticmethod
    def _calc_atr(bars: list, period: int = 14) -> float:
        if len(bars) < period + 1:
            return 0.0
        trs = []
        for i in range(1, len(bars)):
            tr = max(bars[i].high - bars[i].low,
                     abs(bars[i].high - bars[i-1].close),
                     abs(bars[i].low - bars[i-1].close))
            trs.append(tr)
        return sum(trs[-period:]) / period
