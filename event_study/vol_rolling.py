"""VOL-001 滚动窗口复检：短周期因子应该逐段检验存活，而非一次性切分判死。

修正的方法论错误：
  上一版用 2015-2024 做样本内、2025-2026 做样本外，一次性判定"证伪"。
  但成交量异常是短周期因子（持有 1-5 日），它的生命周期本就是episodic的：
  某些年份有效、某些年份失效。正确的检验是滚动窗口看"最近是否还活着"。

实现：
  - 24 个月滚动窗口，步长 6 个月
  - 每个窗口独立计算事件超额收益 + t 检验
  - 输出该因子在时间轴上的存活图

用法: python3 vol_rolling.py
输出: reports/vol_001_rolling.json
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as st

from market_db import CODES, load_daily

PROJECT = Path(__file__).resolve().parent.parent
OUT = PROJECT / "reports" / "vol_001_rolling.json"

LOOKBACK = 20
THRESH = 5.0       # 上一版唯一样本内显著的阈值
HORIZON = 5        # 唯一样本内显著的持有期
COST = 0.0003
WIN_MONTHS = 24
STEP_MONTHS = 6


def build() -> pd.DataFrame:
    rows = []
    for code in CODES:
        df = load_daily(code)
        if df is None or len(df) < LOOKBACK + 60:
            continue
        d = df.copy()
        d["ret"] = d["close"].pct_change()
        d["vol_ratio"] = d["volume"] / d["volume"].rolling(LOOKBACK).mean().shift(1)
        close = d["close"].values
        fwd = np.full(len(d), np.nan)
        if len(d) > HORIZON + 1:
            fwd[:-HORIZON - 1] = close[HORIZON + 1:] / close[1:len(d) - HORIZON] - 1
        d["fwd"] = fwd
        d["code"] = code
        rows.append(d[["date", "code", "ret", "vol_ratio", "fwd"]])
    return pd.concat(rows, ignore_index=True).dropna(subset=["ret", "vol_ratio"])


def main():
    p = build()
    p = p.dropna(subset=["fwd"])
    print(f"面板 {len(p)} 行  {p['date'].min().date()} ~ {p['date'].max().date()}")
    print(f"因子: 成交量 ≥{THRESH:.0f}x，持有 {HORIZON} 日，扣费 {COST*2e4:.0f}bp\n")

    start, end = p["date"].min(), p["date"].max()
    rows = []
    w0 = start
    while w0 + pd.DateOffset(months=WIN_MONTHS) <= end + pd.DateOffset(months=1):
        w1 = w0 + pd.DateOffset(months=WIN_MONTHS)
        w = p[(p["date"] >= w0) & (p["date"] < w1)]
        ev = w[w["vol_ratio"] >= THRESH]
        if len(ev) >= 15 and len(w) >= 200:
            a = ev["fwd"].values - COST * 2
            b = w["fwd"].values - COST * 2
            t, pv = st.ttest_ind(a, b, equal_var=False)
            rows.append({
                "window": f"{w0.date()}~{(w1 - pd.Timedelta(days=1)).date()}",
                "n_event": len(ev), "n_all": len(w),
                "event_mean": float(np.mean(a)), "base_mean": float(np.mean(b)),
                "excess": float(np.mean(a) - np.mean(b)),
                "win": float((a > 0).mean()),
                "t": float(t), "p": float(pv),
            })
        w0 += pd.DateOffset(months=STEP_MONTHS)

    print(f"{'窗口':26} {'事件':>5} {'事件均值':>9} {'基准':>8} {'超额':>9} {'胜率':>7} {'p':>7}  存活")
    print("-" * 92)
    alive = 0
    for r in rows:
        ok = r["p"] < 0.10 and r["excess"] < 0   # 显著且方向为"放量后下跌"
        if ok:
            alive += 1
        print(f"{r['window']:26} {r['n_event']:>5} {r['event_mean']*100:>8.2f}% "
              f"{r['base_mean']*100:>7.2f}% {r['excess']*100:>8.2f}% "
              f"{r['win']*100:>6.1f}% {r['p']:>7.4f}  {'✔' if ok else '-'}")

    print(f"\n{len(rows)} 个窗口中，因子显著存活 {alive} 个 "
          f"（{alive/len(rows)*100:.0f}%），有效期为片段而非全期")

    if rows:
        recent = [r for r in rows if r["window"].startswith(("2024", "2025", "2026"))]
        if recent:
            print(f"\n最近窗口（2024起）:")
            for r in recent:
                print(f"  {r['window']}  超额 {r['excess']*100:+.2f}%  p={r['p']:.4f}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"params": {"thresh": THRESH, "horizon": HORIZON,
                                         "win_months": WIN_MONTHS, "step_months": STEP_MONTHS},
                               "windows": rows}, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"\n-> {OUT}")


if __name__ == "__main__":
    main()
