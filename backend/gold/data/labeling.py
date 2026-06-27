"""
Triple-Barrier Labeling — 基于 López de Prado 方法的序列标注

为 ML 策略生成三屏障标签：
1. 止盈屏障 (Take Profit): attention up = ATR × tp_multiplier
2. 止损屏障 (Stop Loss): price down = ATR × sl_multiplier
3. 时间屏障 (Max Holding): max_holding_days 后到期

既支持 DataFrame，也支持 GoldBarData 列表。
"""

from typing import Optional
import numpy as np
import pandas as pd
from backend.gold.core.models import GoldBarData
from loguru import logger


class TripleBarrierLabeler:
    """Triple-Barrier Labeling — 碰触哪个屏障决定标签"""

    def __init__(
        self,
        atr_window: int = 20,
        tp_multiplier: float = 1.5,
        sl_multiplier: float = 1.0,
        max_holding_days: int = 5,
    ):
        self.atr_window = atr_window
        self.tp_multiplier = tp_multiplier
        self.sl_multiplier = sl_multiplier
        self.max_holding_days = max_holding_days

    # ── GoldBarData 接口 ──────────────────────────────────────────────

    def label_bars(self, bars: list[GoldBarData]) -> list[dict]:
        """对 GoldBarData 列表逐根标注，返回 label 记录列表。

        每条记录:
          bar_index, label(1/-1/0), touch_day, barrier_type, return, tp_price, sl_price
        """
        if len(bars) < self.atr_window + 2:
            logger.warning(f"数据不足 {self.atr_window + 2} 根, 跳过标注")
            return []

        atr_vals = self._compute_atr_bars(bars)
        closes = np.array([b.close for b in bars])
        highs = np.array([b.high for b in bars])
        lows = np.array([b.low for b in bars])
        results = []

        for i in range(len(bars)):
            if i >= len(bars) - self.max_holding_days or np.isnan(atr_vals[i]):
                results.append(self._null_label(i))
                continue

            cp = closes[i]
            atr_v = atr_vals[i]
            tp_price = cp + atr_v * self.tp_multiplier
            sl_price = cp - atr_v * self.sl_multiplier
            touched = False

            for d in range(1, self.max_holding_days + 1):
                idx = i + d
                if idx >= len(bars):
                    break
                if lows[idx] <= sl_price:
                    ret = (sl_price - cp) / cp
                    results.append(dict(bar_index=i, label=-1, touch_day=d,
                                        barrier_type="sl", return_pct=ret,
                                        tp_price=tp_price, sl_price=sl_price))
                    touched = True
                    break
                if highs[idx] >= tp_price:
                    ret = (tp_price - cp) / cp
                    results.append(dict(bar_index=i, label=1, touch_day=d,
                                        barrier_type="tp", return_pct=ret,
                                        tp_price=tp_price, sl_price=sl_price))
                    touched = True
                    break

            if not touched:
                end_idx = min(i + self.max_holding_days, len(bars) - 1)
                ret = (closes[end_idx] - cp) / cp
                results.append(dict(bar_index=i, label=1 if ret > 0 else -1,
                                    touch_day=self.max_holding_days,
                                    barrier_type="time", return_pct=ret,
                                    tp_price=tp_price, sl_price=sl_price))

        return results

    # ── DataFrame 接口 ─────────────────────────────────────────────

    def label_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """DataFrame 版标注。 新增列: tb_label, tb_touch_day, tb_barrier_type, …"""
        df = df.copy()
        atr = self._compute_atr_df(df)
        closes = df["close"].values
        labels, touch_days, barrier_types, returns, tps, sls = ([] for _ in range(6))

        for i in range(len(df)):
            if i >= len(df) - self.max_holding_days or np.isnan(atr.iloc[i]):
                labels.append(0); touch_days.append(0)
                barrier_types.append("none"); returns.append(0.0)
                tps.append(np.nan); sls.append(np.nan)
                continue

            cp, av = closes[i], atr.iloc[i]
            tp_p = cp + av * self.tp_multiplier
            sl_p = cp - av * self.sl_multiplier
            tps.append(tp_p); sls.append(sl_p)
            touched = False

            for d in range(1, self.max_holding_days + 1):
                idx = i + d
                if idx >= len(df):
                    break
                if df["low"].iloc[idx] <= sl_p:
                    labels.append(-1); touch_days.append(d)
                    barrier_types.append("sl")
                    returns.append((sl_p - cp) / cp)
                    touched = True
                    break
                if df["high"].iloc[idx] >= tp_p:
                    labels.append(1); touch_days.append(d)
                    barrier_types.append("tp")
                    returns.append((tp_p - cp) / cp)
                    touched = True
                    break

            if not touched:
                end_p = closes[min(i + self.max_holding_days, len(df) - 1)]
                r = (end_p - cp) / cp
                labels.append(1 if r > 0 else -1)
                touch_days.append(self.max_holding_days)
                barrier_types.append("time")
                returns.append(r)

        df["tb_label"] = labels
        df["tb_touch_day"] = touch_days
        df["tb_barrier_type"] = barrier_types
        df["tb_return"] = returns
        df["tb_tp"] = tps
        df["tb_sl"] = sls
        return df

    # ── 内部方法 ──────────────────────────────────────────────────────

    def _compute_atr_bars(self, bars: list[GoldBarData]) -> np.ndarray:
        if len(bars) < 2:
            return np.full(len(bars), np.nan)
        trs = []
        for i in range(1, len(bars)):
            h, l, pc = bars[i].high, bars[i].low, bars[i - 1].close
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))
        atr = np.full(len(bars), np.nan)
        for i in range(self.atr_window, len(bars)):
            atr[i] = np.mean(trs[i - self.atr_window:i])
        return atr

    def _compute_atr_df(self, df: pd.DataFrame) -> pd.Series:
        hl, hc = df["high"] - df["low"], (df["high"] - df["close"].shift(1)).abs()
        lc = (df["low"] - df["close"].shift(1)).abs()
        tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
        return tr.rolling(self.atr_window).mean()

    @staticmethod
    def _null_label(bar_index: int) -> dict:
        return dict(bar_index=bar_index, label=0, touch_day=0,
                    barrier_type="none", return_pct=0.0,
                    tp_price=None, sl_price=None)

    # ── 统计便利方法 ──────────────────────────────────────────────────

    @staticmethod
    def label_distribution(labels: list[dict]) -> dict:
        """返回标签分布统计"""
        total = len(labels)
        if total == 0:
            return {}
        bulls = sum(1 for l in labels if l["label"] == 1)
        bears = sum(1 for l in labels if l["label"] == -1)
        neutral = sum(1 for l in labels if l["label"] == 0)
        by_type = {}
        for l in labels:
            bt = l.get("barrier_type", "none")
            by_type[bt] = by_type.get(bt, 0) + 1
        return {
            "total": total,
            "bull": bulls, "bull_pct": round(bulls / total * 100, 1),
            "bear": bears, "bear_pct": round(bears / total * 100, 1),
            "neutral": neutral, "neutral_pct": round(neutral / total * 100, 1),
            "by_barrier": {k: round(v / total * 100, 1) for k, v in by_type.items()},
        }
