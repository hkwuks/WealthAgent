"""因子方向选择器 —— 用数据决定 direction，而不是凭直觉填。

教程 §10「判断策略值得实盘」的横截面一致性检查，落到单标的时序上：
  对每个因子算它与未来 N 日收益的 Spearman 相关（时序 IC）。
  IC 显著为正 -> direction 应为 +1；显著为负 -> -1；不显著 -> 该因子无方向。

滚动窗口输出，因为因子有效性是片段式的（见 vol_rolling 的教训）。

用法: python3 select_direction.py
输出: reports/factor_direction.json
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
from backend.fund_quant.factors.technical import OPS, WINDOWS

HORIZONS = [5, 20]
WIN_MONTHS = 36
OUT = HERE.parent / "reports" / "factor_direction.json"


def compute_factor(series: np.ndarray, op: str, n: int) -> np.ndarray:
    """向量化版：对每个时点算因子值，避免 O(n²) 逐点调用。"""
    s = pd.Series(series)
    if len(s) <= n + 2:
        return np.full(len(s), np.nan)
    if op == "roc":
        return (s / s.shift(n) - 1).values
    if op == "ma_gap":
        return (s / s.rolling(n).mean() - 1).values
    if op == "std":
        return s.pct_change().rolling(n).std().values
    if op == "max_gap":
        return (s / s.rolling(n).max() - 1).values
    if op == "rsv":
        lo = s.rolling(n).min()
        hi = s.rolling(n).max()
        return ((s - lo) / (hi - lo)).replace([np.inf, -np.inf], np.nan).values
    if op == "rank":
        r = s.pct_change()
        return r.rolling(n).apply(lambda x: (x <= x[-1]).mean(), raw=True).values
    if op == "skew":
        return s.pct_change().rolling(n).skew().values
    return np.full(len(s), np.nan)


def build_panel() -> pd.DataFrame:
    rows = []
    for code in CODES:
        df = load_daily(code)
        if df is None or len(df) < 300:
            continue
        df = df.sort_values("date").reset_index(drop=True)
        close = df["close"].values.astype(float)
        rec = {"date": df["date"].values, "code": code, "close": close}
        for op in OPS:
            for n in WINDOWS:
                rec[f"{op}_{n}"] = compute_factor(close, op, n)
        for h in HORIZONS:
            fwd = np.full(len(close), np.nan)
            fwd[:-h] = close[h:] / close[:-h] - 1
            rec[f"fwd{h}"] = fwd
        rows.append(pd.DataFrame(rec))
    return pd.concat(rows, ignore_index=True)


def ic_block(p: pd.DataFrame) -> dict:
    """每个因子 × 每个持有期的 Spearman IC。"""
    res = {}
    for op in OPS:
        for n in WINDOWS:
            f = f"{op}_{n}"
            for h in HORIZONS:
                sub = p[[f, f"fwd{h}"]].dropna()
                if len(sub) < 200:
                    continue
                ic, pv = st.spearmanr(sub[f], sub[f"fwd{h}"])
                res[f"{f}_h{h}"] = {"ic": float(ic), "p": float(pv), "n": len(sub)}
    return res


def main():
    p = build_panel()
    p["date"] = pd.to_datetime(p["date"])
    print(f"面板 {len(p)} 行  {p['code'].nunique()} 只  "
          f"{p['date'].min().date()} ~ {p['date'].max().date()}\n")

    print("=" * 96)
    print("全期 IC（因子 vs 未来收益的 Spearman 相关）")
    print("=" * 96)
    print(f"{'因子':18} " + " ".join(f"{'未来'+str(h)+'日':>12}" for h in HORIZONS))
    full = ic_block(p)
    by_factor = {}
    for op in OPS:
        for n in WINDOWS:
            line = []
            for h in HORIZONS:
                k = f"{op}_{n}_h{h}"
                if k in full:
                    ic, pv = full[k]["ic"], full[k]["p"]
                    mark = "**" if pv < 0.01 else ("*" if pv < 0.05 else "")
                    line.append(f"{ic:+.4f}{mark:<2}")
                    by_factor.setdefault(f"{op}_{n}", {})[f"h{h}"] = full[k]
            if line:
                print(f"{op+'_'+str(n):18} " + " ".join(f"{x:>12}" for x in line))

    print("\n" + "=" * 96)
    print("方向判定（|IC|>0.02 且 p<0.05 才算有方向，否则判为无效）")
    print("=" * 96)
    print(f"{'因子':18} {'先验':>6} {'实测IC':>9} {'应为':>6} {'一致?':>7}  说明")
    verdict = {}
    for f, hs in by_factor.items():
        op, n = f.rsplit("_", 1)
        prior = OPS[op][1]
        sig = [(h, v) for h, v in hs.items() if v["p"] < 0.05 and abs(v["ic"]) > 0.02]
        if not sig:
            verdict[f] = {"direction": 0, "reason": "无显著方向"}
            print(f"{f:18} {prior:+6d} {'—':>9} {0:+6d} {'—':>7}  无效，淘汰")
            continue
        ic = np.mean([v["ic"] for _, v in sig])
        d = 1 if ic > 0 else -1
        ok = "✔" if d == prior else "✘"
        verdict[f] = {"direction": d, "ic": float(ic),
                      "prior": prior, "match": d == prior,
                      "horizons": [h for h, _ in sig],
                      "reason": "数据支持" if d == prior else "数据与先验相反"}
        print(f"{f:18} {prior:+6d} {ic:>+9.4f} {d:+6d} {ok:>7}  "
              f"{'符合直觉' if d == prior else '** 反直觉，按数据来 **'}")

    valid = [f for f, v in verdict.items() if v["direction"] != 0]
    contra = [f for f, v in verdict.items() if v["direction"] != 0 and not v["match"]]
    print(f"\n{len(by_factor)} 个因子中，有显著方向 {len(valid)} 个，"
          f"其中 {len(contra)} 个与先验相反")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"full_ic": full, "verdict": verdict},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
