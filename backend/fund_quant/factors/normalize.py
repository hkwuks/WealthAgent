"""因子值归一化 —— 把不同量纲的原始因子压到 0~1，供前端雷达图。

为什么不能统一用一种变换：
  roc   原始值 ±0.3（收益率）      -> 线性映射
  rsv   原始值 0~1（区间位置）     -> 本身就是概率，直接用
  std   原始值 0~0.05（波动率）    -> 需要放大
  ma_gap 原始值 ±0.3              -> 线性映射
统一 squash 会让某一类因子永远显示 0 或 1，雷达图失去意义。
"""

from __future__ import annotations

import numpy as np

# 每类算子的合理值域（基于 15 只 ETF 2015-2026 实测分布）
RANGES = {
    "roc": (-0.30, 0.30),
    "ma_gap": (-0.30, 0.30),
    "std": (0.0, 0.06),
    "max_gap": (-0.60, 0.0),
    "rsv": (0.0, 1.0),
    "rank": (0.0, 1.0),
    "skew": (-2.0, 2.0),
}


def _squash(value: float, op: str | None = None) -> float:
    """按算子类型映射到 0~1。op 为 None 时用 tanh 兜底。"""
    if op in ("rsv", "rank"):
        # 这两个算子已经是 0~1 概率/分位，再做线性映射会把 0.2 压成 0.2 而非合理区间
        return float(value)
    if op is None:
        return float((np.tanh(value) + 1) / 2)
    lo, hi = RANGES.get(op, (-1.0, 1.0))
    if hi == lo:
        return 0.5
    return float((value - lo) / (hi - lo))


def op_of(name: str) -> str | None:
    """tech_ma_gap_10 -> ma_gap

    算子名本身含下划线（ma_gap / max_gap），不能简单取 parts[1]：
    split('_') 后 ma_gap 会被截成 'ma'，RANGES 查不到就回退到 (-1,1)，
    整个窗口的归一化值全错。末尾那一段一定是窗口数字，去掉它才是算子。
    """
    if not name.startswith("tech_"):
        return None
    body = name[len("tech_"):]
    op, _, win = body.rpartition("_")
    return op if op and win.isdigit() else None
