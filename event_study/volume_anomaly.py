"""教程附录 B：成交量异常实验（VOL-001）

严格按 §5.1 研究流程 + §5.2 事件定义 + §5.3 指标表：
  1. 假设：异常成交量后，未来 1/2/3/5 日收益分布发生变化
  2. 事件：VolumeRatio = Vol_t / mean(Vol_{t-20..t-1})，阈值 2x/3x/5x
  3. 分组：上涨放量 / 下跌放量 / 横盘放量
  4. 统计：均值/中位数/胜率/分位数/最大不利/分年/分标的
  5. T+1 成交：信号在 T 日收盘确定，收益从 T+1 收盘起算
  6. 扣费：ETF 双边 3bp
  7. 样本外：2025 年后完全留出，不参与任何参数选择

用法: python3 volume_anomaly.py
输出: reports/vol_001.json + 控制台
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from market_db import CODES, load_daily

PROJECT = Path(__file__).resolve().parent.parent
OUT = PROJECT / "reports" / "vol_001.json"

LOOKBACK = 20
THRESHOLDS = [2.0, 3.0, 5.0]
HORIZONS = [1, 2, 3, 5]
COST = 0.0003          # 单边 3bp
IS_END = "2025-01-01"  # 样本内外分界


def build_panel() -> pd.DataFrame:
    """所有 ETF 的日收益率面板 + 成交量比率。"""
    rows = []
    for code in CODES:
        df = load_daily(code)
        if df is None or len(df) < LOOKBACK + 60:
            continue
        df = df.copy()
        df["ret"] = df["close"].pct_change()
        vma = df["volume"].rolling(LOOKBACK).mean().shift(1)
        df["vol_ratio"] = df["volume"] / vma
        df["code"] = code
        rows.append(df[["date", "code", "close", "ret", "vol_ratio"]])
    panel = pd.concat(rows, ignore_index=True)
    return panel.dropna(subset=["ret", "vol_ratio"])


def forward_returns(panel: pd.DataFrame) -> pd.DataFrame:
    """T 日信号，收益从 T+1 收盘起算（避免未来函数）。"""
    out = []
    for code, g in panel.groupby("code"):
        g = g.sort_values("date").copy()
        close = g["close"].values
        for h in HORIZONS:
            fwd = np.full(len(g), np.nan)
            # T+1 买入，T+1+h 卖出
            if len(g) > h + 1:
                fwd[:-h - 1] = close[h + 1:] / close[1:len(g) - h] - 1
            g[f"fwd{h}"] = fwd
        out.append(g)
    return pd.concat(out, ignore_index=True)


def stats(x: np.ndarray) -> dict:
    x = x[np.isfinite(x)]
    if len(x) < 30:
        return {}
    return {
        "n": int(len(x)),
        "mean": float(np.mean(x)),
        "median": float(np.median(x)),
        "win": float((x > 0).mean()),
        "std": float(np.std(x)),
        "p05": float(np.percentile(x, 5)),
        "p95": float(np.percentile(x, 95)),
        "worst": float(np.min(x)),
    }


def group_label(r: float) -> str:
    if r >= 0.005:
        return "上涨放量"
    if r <= -0.005:
        return "下跌放量"
    return "横盘放量"


def main():
    panel = build_panel()
    panel = forward_returns(panel)
    print(f"面板: {panel['code'].nunique()} 只 ETF, {len(panel)} 行, "
          f"{panel['date'].min().date()} ~ {panel['date'].max().date()}")

    IS = panel[panel["date"] < IS_END]
    OOS = panel[panel["date"] >= IS_END]
    print(f"样本内 {len(IS)} 行 / 样本外 {len(OOS)} 行（{IS_END} 起完全留出）")

    report = {"params": {"lookback": LOOKBACK, "thresholds": THRESHOLDS,
                         "horizons": HORIZONS, "cost_bps": COST * 1e4},
              "in_sample": {}, "out_sample": {}}

    for name, data in (("in_sample", IS), ("out_sample", OOS)):
        print("\n" + "=" * 96)
        print(f"{'样本内' if name == 'in_sample' else '样本外'}：成交量倍数 × 持有期 的收益分布（已扣 {COST*1e4:.0f}bp×2）")
        print("=" * 96)
        block = {}
        for th in THRESHOLDS:
            for grp in ("上涨放量", "下跌放量", "横盘放量"):
                sub = data[(data["vol_ratio"] >= th) &
                           (data["ret"].apply(group_label) == grp)]
                if len(sub) < 30:
                    continue
                print(f"\n  ≥{th:.0f}x {grp}  n={len(sub)}")
                print(f"    {'持有':>4} {'均值':>8} {'中位':>8} {'胜率':>7} "
                      f"{'标准差':>8} {'P05':>8} {'最差':>8}")
                for h in HORIZONS:
                    s = stats(sub[f"fwd{h}"].values - COST * 2)
                    if not s:
                        continue
                    print(f"    {h:>3}日 {s['mean']*100:>7.2f}% {s['median']*100:>7.2f}% "
                          f"{s['win']*100:>6.1f}% {s['std']*100:>7.2f}% "
                          f"{s['p05']*100:>7.2f}% {s['worst']*100:>7.2f}%")
                    block[f"{th}x_{grp}_{h}d"] = s
        report[name] = block

    # ── 基准对照：无条件下持有同样天数 ──────────────────────────────
    print("\n" + "=" * 96)
    print("基准（无条件下买入持有，同扣费）")
    print("=" * 96)
    base = {}
    for name, data in (("in_sample", IS), ("out_sample", OOS)):
        print(f"\n  {name}")
        for h in HORIZONS:
            s = stats(data[f"fwd{h}"].values - COST * 2)
            if s:
                print(f"    {h:>3}日  均值 {s['mean']*100:>7.2f}%  胜率 {s['win']*100:>6.1f}%")
                base[f"{name}_{h}d"] = s
    report["baseline"] = base

    # ── 显著性：事件组 vs 基准组 t 检验 ────────────────────────────
    from scipy import stats as st
    print("\n" + "=" * 96)
    print("显著性检验（Welch t-test，事件组 vs 全样本）")
    print("=" * 96)
    sig = {}
    for name, data in (("in_sample", IS), ("out_sample", OOS)):
        for th in THRESHOLDS:
            sub = data[data["vol_ratio"] >= th]
            if len(sub) < 30:
                continue
            for h in HORIZONS:
                a = sub[f"fwd{h}"].dropna().values
                b = data[f"fwd{h}"].dropna().values
                if len(a) < 30:
                    continue
                t, p = st.ttest_ind(a, b, equal_var=False)
                key = f"{name}_{th}x_{h}d"
                sig[key] = {"t": float(t), "p": float(p),
                            "excess": float(np.mean(a) - np.mean(b))}
                flag = "显著" if p < 0.05 else "不显著"
                print(f"  {name:10} ≥{th:.0f}x {h}日  超额 {np.mean(a)-np.mean(b):+.3%}  "
                      f"t={t:+.2f} p={p:.4f} {flag}")
    report["significance"] = sig

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n-> {OUT}")


if __name__ == "__main__":
    main()
