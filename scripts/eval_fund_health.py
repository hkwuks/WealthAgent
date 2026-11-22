"""教程 §10 要求的两项检查：逐只基金体检 + 参数敏感性。

参数敏感性不是参数优化：这里把网格全部结果列出来看分布，
而不是挑最好的那组。挑最好 = 教程 §2.2 说的过拟合。
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from eval_benchmarks import (
    BENCH_DIR, FEE_BPS, PORT_DIR, TRADING_DAYS, load, metrics, momentum_rotation,
    resolve_holdings, to_ret,
)

PROJECT = Path(__file__).resolve().parent.parent
CASH = 0.015


def per_fund_table():
    port = json.loads((PROJECT / "data" / "my_portfolio.json").read_text(encoding="utf-8"))
    idx = json.loads((PORT_DIR / "_index.json").read_text(encoding="utf-8"))
    code, missing, _ = resolve_holdings(port["holdings"], idx)

    rows = []
    for h in port["holdings"]:
        c = code.get(h["fund_name"])
        if not c:
            continue
        s = load(BENCH_DIR, c) if c == "518880" else load(PORT_DIR, c)
        if s is None or len(s) < 300:
            continue
        r = to_ret(s)
        # 统一看最近 5 年（各基金共同可比窗口）
        r5 = r[r.index >= r.index[-1] - pd.Timedelta(days=365 * 5)]
        m5 = metrics(r5)
        mfull = metrics(r)
        rows.append({
            "name": h["fund_name"], "code": c, "amount": h["amount"],
            "class": h.get("asset_class", ""),
            "current_pct": h.get("return_pct"),
            "cagr_5y": m5.get("cagr"), "dd_5y": m5.get("max_dd"),
            "sharpe_5y": m5.get("sharpe"), "vol_5y": m5.get("vol"),
            "cagr_all": mfull.get("cagr"), "sharpe_all": mfull.get("sharpe"),
            "years": mfull.get("years"),
        })
    df = pd.DataFrame(rows).sort_values("sharpe_5y", ascending=False)

    print("=" * 100)
    print("逐只基金体检（近5年，按 Sharpe 排序；右两列是全历史）")
    print("=" * 100)
    print(f"{'基金':40} {'近5年年化':>9} {'近5年回撤':>9} {'近5年Sharpe':>11} "
          f"{'全历史年化':>10} {'全历史Sharpe':>12}")
    for _, r in df.iterrows():
        if pd.isna(r["cagr_5y"]):
            continue
        print(
            f"{r['name'][:38]:40} {r['cagr_5y']*100:>8.2f}% {r['dd_5y']*100:>8.1f}% "
            f"{r['sharpe_5y']:>11.2f} {r['cagr_all']*100:>9.2f}% {r['sharpe_all']:>12.2f}"
        )

    print(f"\n统计：{len(df)} 只有净值")
    print(f"  近5年 Sharpe > 1.0 : {(df['sharpe_5y'] > 1.0).sum()} 只")
    print(f"  近5年 Sharpe 0.5~1 : {((df['sharpe_5y'] > 0.5) & (df['sharpe_5y'] <= 1.0)).sum()} 只")
    print(f"  近5年 Sharpe < 0.5 : {(df['sharpe_5y'] <= 0.5).sum()} 只")
    print(f"  近5年 Sharpe < 0   : {(df['sharpe_5y'] < 0).sum()} 只")

    # 按资产类别加权贡献
    print("\n按资产类别汇总（权重 = 当前市值占比）")
    tot = df["amount"].sum()
    df["w"] = df["amount"] / tot
    g = df.groupby("class").apply(
        lambda x: pd.Series({
            "weight": x["w"].sum(),
            "w_sharpe": np.nansum(x["w"] * x["sharpe_5y"]) / x["w"].sum(),
            "w_cagr": np.nansum(x["w"] * x["cagr_5y"]) / x["w"].sum(),
            "n": len(x),
        }), include_groups=False
    ).sort_values("weight", ascending=False)
    print(f"{'类别':12} {'权重':>8} {'只数':>5} {'加权年化':>10} {'加权Sharpe':>11}")
    for cls, r in g.iterrows():
        print(f"{cls:12} {r['weight']*100:>7.1f}% {int(r['n']):>5} "
              f"{r['w_cagr']*100:>9.2f}% {r['w_sharpe']:>11.2f}")
    return df, missing


def sensitivity():
    print("\n" + "=" * 100)
    print("动量轮动参数敏感性（教程 §10；报告全部结果，不挑最优）")
    print("=" * 100)
    codes = ["510300", "510500", "159915", "513100", "518880", "512890"]
    pool = {c: s for c in codes if (s := load(BENCH_DIR, c)) is not None}

    rows = []
    for lb in (10, 20, 25, 40, 60):
        for top in (1, 2, 3):
            for hold in (5, 10, 20, 40):
                r = momentum_rotation(pool, lookback=lb, top_n=top, hold=hold)
                r = r[r.index >= "2020-01-02"]
                m = metrics(r)
                if not m:
                    continue
                rows.append({"lookback": lb, "top_n": top, "hold": hold,
                             "cagr": m["cagr"], "dd": m["max_dd"], "sharpe": m["sharpe"]})
    df = pd.DataFrame(rows)
    print(f"{'lookback':>9} {'top_n':>6} {'hold':>5} {'年化':>8} {'回撤':>8} {'Sharpe':>8}")
    for _, r in df.sort_values("sharpe", ascending=False).head(8).iterrows():
        print(f"{int(r.lookback):>9} {int(r.top_n):>6} {int(r.hold):>5} "
              f"{r.cagr*100:>7.2f}% {r.dd*100:>7.1f}% {r.sharpe:>8.2f}")
    print("  ...（仅列前8；完整分布见下）")
    print(f"\n全网格 {len(df)} 组：")
    for c in ("cagr", "sharpe"):
        print(f"  {c:8} 中位 {df[c].median():>7.3f}  最差 {df[c].min():>7.3f}  "
              f"最好 {df[c].max():>7.3f}  负值占比 {(df[c] < 0).mean()*100:>5.1f}%")
    # 对照：同期买入持有
    for c in ("512890", "510300"):
        s = load(BENCH_DIR, c)
        s = s[s.index >= "2020-01-02"]
        m = metrics(to_ret(s))
        print(f"  对照 买入持有 {c}: 年化 {m['cagr']*100:.2f}%  Sharpe {m['sharpe']:.2f}  "
              f"回撤 {m['max_dd']*100:.1f}%")
    return df


if __name__ == "__main__":
    per_fund_table()
    sensitivity()
