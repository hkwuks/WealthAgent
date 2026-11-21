"""买入价位的可辨识统计（不猜测具体日期）。

失败记录（保留，避免重犯）：
  1. 按"净值等于隐含成本价"找买入日期 → 无效。1600~4300 个价格点里找
     一个匹配值，残差必然接近 0，自由度太多，不构成证据。
  2. 按等额定投调和平均反推起点 → 同样不够约束：任何起点都能凑出接近的值。
  3. 未锚定快照日 → 会用 2026-11 的净值去解释 2026-10-09 的持仓，产生
     "买入日期晚于快照日"的荒谬结果。

可辨识的量只有一个：
  隐含平均成本价 P = NAV(快照日) × 成本 / 市值
  P 在该基金净值历史中的分位数 → "你买在了这只基金自己价格曲线的什么位置"
这是唯一不依赖交易日期、也不受自由度污染的指标。
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from eval_benchmarks import resolve_holdings

PROJECT = Path(__file__).resolve().parent.parent
NAV_DIR = PROJECT / "data" / "my_portfolio_nav"
BENCH_DIR = PROJECT / "data" / "benchmark_nav"
SNAPSHOT = pd.Timestamp("2026-10-09")


def load(code: str) -> pd.Series | None:
    for d in (NAV_DIR, BENCH_DIR):
        f = d / f"{code}.json"
        if not f.exists():
            continue
        rows = json.loads(f.read_text(encoding="utf-8"))
        if not rows:
            continue
        pairs = {}
        for r in rows:
            v = r.get("adj_nav") or r.get("unit_nav") or r.get("nav")
            if v and float(v) > 0:
                pairs[r["date"]] = float(v)
        s = pd.Series(pairs, dtype="float64").sort_index()
        s.index = pd.to_datetime(s.index)
        return s[~s.index.duplicated(keep="last")]
    return None


def pct_rank(series: np.ndarray, value: float) -> float:
    """value 在 series 中的分位（0=最低，1=最高）。"""
    return float((series <= value).mean())


def main():
    port = json.loads((PROJECT / "data" / "my_portfolio.json").read_text(encoding="utf-8"))
    idx = json.loads((NAV_DIR / "_index.json").read_text(encoding="utf-8"))
    code_map, missing, _ = resolve_holdings(port["holdings"], idx)

    print("=" * 104)
    print(f"买入价位分位（快照日 {SNAPSHOT.date()}）")
    print("=" * 104)
    print(f"{'基金':26} {'收益率':>7} {'隐含成本价':>9} {'快照日净值':>10} "
          f"{'全历史分位':>8} {'近2年分位':>8} {'权重':>6}  解读")
    print("-" * 104)

    rows = []
    for h in port["holdings"]:
        c = code_map.get(h["fund_name"])
        if not c:
            continue
        nav = load(c)
        if nav is None or len(nav) < 60:
            continue
        # 锚定快照日：只能用快照日之前的数据
        hist = nav[nav.index <= SNAPSHOT]
        if len(hist) < 30:
            continue
        nav_snap = hist.iloc[-1]
        value, pl = h["amount"], h["holding_return"]
        cost = value - pl
        if cost <= 0:
            continue
        ret = pl / cost
        p = nav_snap * cost / value  # 隐含平均成本价

        full_rank = pct_rank(hist.values, p)
        recent = hist[hist.index >= SNAPSHOT - pd.Timedelta(days=730)]
        near_rank = pct_rank(recent.values, p) if len(recent) > 20 else np.nan

        if full_rank >= 0.90:
            note = "买在历史高位"
        elif full_rank >= 0.70:
            note = "偏高"
        elif full_rank <= 0.30:
            note = "偏低"
        else:
            note = "中位"

        rows.append({
            "name": h["fund_name"], "code": c, "cls": h.get("asset_class", ""),
            "value": value, "cost": cost, "pl": pl, "ret": ret,
            "cost_price": float(p), "nav_snapshot": float(nav_snap),
            "rank_full": full_rank, "rank_2y": near_rank,
            "weight": cost, "note": note,
        })

        print(f"{h['fund_name'][:24]:26} {ret*100:>+6.1f}% {p:>9.4f} {nav_snap:>10.4f} "
              f"{full_rank*100:>7.0f}% {near_rank*100:>7.0f}% "
              f"{cost/port['meta']['total_asset']*100:>5.1f}%  {note}")

    df = pd.DataFrame(rows)
    TC = df["weight"].sum()

    print("\n" + "=" * 104)
    print("按分位聚合（成本加权）")
    print("=" * 104)
    g = df.groupby("note").agg(只数=("name", "count"), 成本=("weight", "sum"),
                               盈亏=("pl", "sum"))
    g["成本占比"] = g["成本"] / TC
    g["收益率"] = g["盈亏"] / g["成本"]
    for note, r in g.sort_values("成本", ascending=False).iterrows():
        print(f"  {note:12} {int(r['只数']):>3} 只  成本 {r['成本']:>9,.0f} "
              f"({r['成本占比']*100:>5.1f}%)  盈亏 {r['盈亏']:>+9.2f}  "
              f"收益率 {r['收益率']*100:>+6.2f}%")

    w_rank = np.average(df["rank_full"], weights=df["weight"])
    w_ret = np.average(df["ret"], weights=df["weight"])
    print(f"\n成本加权平均分位: {w_rank*100:.1f}%  "
          f"（50% = 平均买在中位，>70% = 系统性买在偏高位置）")
    print(f"成本加权平均收益率: {w_ret*100:+.2f}%")

    corr = np.corrcoef(df["rank_full"], df["ret"])[0, 1]
    print(f"买入分位与收益率的相关系数: {corr:+.3f}  "
          f"（负值 = 买得越高亏得越多，验证追高是否成立）")

    OUT = PROJECT / "reports" / "timing_inference.json"
    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n-> {OUT}")


if __name__ == "__main__":
    main()
