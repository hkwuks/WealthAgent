"""
SHFE 主力合约展期处理 — 转换连续 K 线至统一基准。

原理:
  当合约从旧主力切换到新主力时，调整新合约价格以匹配旧合约，
  消除展期日的跳空缺口。

两种方法:
  1. backward_ratio: 用展期日前后价差比例调整后续所有价格
  2. forward_adjust: 用展期日价差差额调整过往所有价格（默认，更常用）
"""

import numpy as np
from typing import Optional
from datetime import datetime
from loguru import logger

from backend.gold.core.models import GoldBarData


class ContractRolloverProcessor:
    """主力合约展期处理器 — 消除换月跳空"""

    def __init__(self, method: str = "forward_adjust"):
        """
        Args:
            method: forward_adjust（前向调整, 默认 / backward_ratio（比例调整）
        """
        self.method = method

    def process(self, bars: list[GoldBarData],
                rollover_dates: list[datetime] = None) -> list[GoldBarData]:
        """
        对连续 K 线进行处理，消除展期跳空。

        Args:
            bars: 主力连续 K 线（含展期日跳空）
            rollover_dates: 展期日期列表（如无则自动检测跳空 > 5% 的日期）

        Returns:
            调整后的连续 K 线
        """
        if len(bars) < 10:
            return bars

        closes = np.array([b.close for b in bars])

        if rollover_dates is None:
            rollover_dates = self._detect_rollovers(bars)

        if not rollover_dates:
            return bars

        adjusted = list(bars)
        for rd in rollover_dates:
            rd_idx = None
            for i, b in enumerate(bars):
                if b.datetime.date() >= rd.date():
                    rd_idx = i
                    break
            if rd_idx is None or rd_idx >= len(bars) - 1:
                continue

            # 展期日跳空 = 新合约 - 旧合约
            gap = bars[rd_idx + 1].close - bars[rd_idx].close
            gap_pct = gap / bars[rd_idx].close * 100

            if abs(gap_pct) < 1.0:
                continue  # 无显著跳空，不是展期

            logger.info(f"检测到展期跳空: {bars[rd_idx].datetime.date()} -> "
                        f"{bars[rd_idx + 1].datetime.date()}, gap={gap_pct:.2f}%")

            if self.method == "forward_adjust":
                # 前向调整：展期后的全部价格减去跳空间隙
                for j in range(rd_idx + 1, len(adjusted)):
                    b = adjusted[j]
                    adjusted[j] = GoldBarData(
                        symbol=b.symbol, exchange=b.exchange, period=b.period,
                        datetime=b.datetime,
                        open=b.open - gap, high=b.high - gap,
                        low=b.low - gap, close=b.close - gap,
                        volume=b.volume, turnover=b.turnover,
                        open_interest=b.open_interest,
                    )
            else:
                # 比例调整
                ratio = bars[rd_idx].close / bars[rd_idx + 1].close
                for j in range(rd_idx + 1, len(adjusted)):
                    b = adjusted[j]
                    adjusted[j] = GoldBarData(
                        symbol=b.symbol, exchange=b.exchange, period=b.period,
                        datetime=b.datetime,
                        open=b.open * ratio, high=b.high * ratio,
                        low=b.low * ratio, close=b.close * ratio,
                        volume=b.volume, turnover=b.turnover,
                        open_interest=b.open_interest,
                    )

        logger.info(f"展期处理完成: {len(rollover_dates)} 次展期, "
                    f"{len(bars)} -> {len(adjusted)} bars")
        return adjusted

    @staticmethod
    def _detect_rollovers(bars: list[GoldBarData],
                          gap_threshold: float = 3.0) -> list[datetime]:
        """自动检测跳空 > gap_threshold% 的日期作为展期候选"""
        rollovers = []
        for i in range(1, len(bars)):
            gap = abs(bars[i].close / bars[i - 1].close - 1) * 100
            if gap > gap_threshold:
                # 确认不是数据异常：检查高低价差也跳空
                high_gap = abs(bars[i].high / bars[i - 1].high - 1) * 100
                low_gap = abs(bars[i].low / bars[i - 1].low - 1) * 100
                if high_gap > gap_threshold * 0.5 and low_gap > gap_threshold * 0.5:
                    rollovers.append(bars[i].datetime)
                    logger.debug(f"自动检测展期: {bars[i-1].datetime.date()} -> "
                                 f"{bars[i].datetime.date()}, gap={gap:.1f}%")
        return rollovers
