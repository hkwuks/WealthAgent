"""因子滚动 IC —— 确认哪些因子「现在还活着」。

教训来自 VOL-001：全期平均 IC 会掩盖因子在近期失效。
所以对每个因子做 36 个月滚动窗口的 IC，输出存活率与最近状态。

判定标准（不用 p 值，用方向一致性——见 vol_rolling 的经验）：
  存活 = 该窗口 IC 与全期 IC 同号，且 |IC| > 0.02

用法: python3 rolling_ic.py
输出: reports/factor_rolling_ic.json
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as st

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

from market_db import CODES, load_daily
from select_direction import compute_factor
from backend.fund_quant.factors.technical import OPS, WINDOWS

HORIZON = 20          # 用 20 日，IC 最稳定
WIN_MONTHS = 36
STEP_MONTHS = 12
MIN_OBS = 150
OUT = HERE.parent / "reports" / "factor_rolling_ic.json"


def build() -> pd.DataFrame:
    rows = []
    for code in CODES:
        df = load_daily(code)
        if df is None or len(df) < 400:
            continue
        df = df.sort_values("date").reset_index(drop=True)
        close = df["close"].values.astype(float)
        rec = {"date": pd.to_datetime(df["date"].values), "code": code}
        for op in OPS:
            for n in WINDOWS:
                rec[f"{op}_{n}"] = compute_factor(close, op, n)
        fwd = np.full(len(close), np.nan)
        fwd[:-HORIZON] = close[HORIZON:] / close[:-HORIZON] - 1
        rec["fwd"] = fwd
        rows.append(pd.DataFrame(rec))
    return pd.concat(rows, ignore_index=True)


def main():
    p = build()
    print(f"面板 {len(p)} 行  {p['code'].nunique()} 只  "
          f"{p['date'].min().date()} ~ {p['date'].max().date()}")
    print(f"未来 {HORIZON} 日收益，滚动 {WIN_MONTHS} 个月窗口，步长 {STEP_MONTHS} 个月\n")

    # 全期 IC 作为基准方向
    full = {}
    for op in OPS:
        for n in WINDOWS:
            f = f"{op}_{n}"
            sub = p[[f, "fwd"]].dropna()
            if len(sub) < MIN_OBS:
                continue
            ic, pv = st.spearmanr(sub[f], sub["fwd"])
            if pv < 0.05 and abs(ic) > 0.02:
                full[f] = {"ic": float(ic), "dir": 1 if ic > 0 else -1}

    print(f"全期有方向的因子 {len(full)} 个，逐个看滚动存活\n")

    # 窗口切分
    start, end = p["date"].min(), p["date"].max()
    windows = []
    w0 = start
    while w0 + pd.DateOffset(months=WIN_MONTHS) <= end:
        windows.append((w0, w0 + pd.DateOffset(months=WIN_MONTHS)))
        w0 += pd.DateOffset(months=STEP_MONTHS)

    print(f"{'因子':16} {'方向':>4} {'窗口':>5} {'存活':>5} {'存活率':>7} "
          f"{'最近窗口IC':>11} {'最近':>5}")
    print("-" * 76)

    results = {}
    for f, info in sorted(full.items(), key=lambda x: -abs(x[1]["ic"])):
        ics = []
        for a, b in windows:
            sub = p[(p["date"] >= a) & (p["date"] < b)][[f, "fwd"]].dropna()
            if len(sub) < MIN_OBS:
                ics.append(np.nan)
                continue
            ic, _ = st.spearmanr(sub[f], sub["fwd"])
            ics.append(ic)
        arr = np.array(ics, dtype=float)
        ok = np.array([(not np.isnan(x)) and (np.sign(x) == info["dir"]) and abs(x) > 0.02
                       for x in arr])
        n_valid = int((~np.isnan(arr)).sum())
        alive = int(ok.sum())
        recent = arr[-1] if len(arr) and not np.isnan(arr[-1]) else np.nan
        recent_ok = "✔" if (not np.isnan(recent) and np.sign(recent) == info["dir"]
                             and abs(recent) > 0.02) else "-"
        rate = alive / n_valid * 100 if n_valid else 0
        results[f] = {"dir": info["dir"], "full_ic": info["ic"],
                      "windows": n_valid, "alive": alive, "alive_rate": rate,
                      "recent_ic": None if np.isnan(recent) else float(recent),
                      "recent_alive": recent_ok == "✔"}
        print(f"{f:16} {info['dir']:+4d} {n_valid:>5} {alive:>5} "
              f"{rate:>6.0f}% {recent:>+11.4f} {recent_ok:>5}")

    # ── 只保留"现在还活着"的因子 ──────────────────────────────────
    survivors = {f: v for f, v in results.items()
                 if v["recent_alive"] and v["alive_rate"] >= 50}
    print("\n" + "=" * 76)
    print(f"既在近期存活、历史存活率又 ≥50% 的因子：{len(survivors)} 个")
    print("=" * 76)
    for f, v in sorted(survivors.items(), key=lambda kv: -abs(kv[1]["recent_ic"] or 0)):
        print(f"  {f:16} 方向 {v['dir']:+d}  近期IC {v['recent_ic']:+.4f}  "
              f"存活率 {v['alive_rate']:.0f}%")

    if not survivors:
        print("  （无）→ 说明所有因子都在近期失效，需要换方向")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"horizon": HORIZON, "windows": len(windows),
                               "results": results, "survivors": list(survivors)},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n-> {OUT}")


if __name__ == "__main__":
    main()
