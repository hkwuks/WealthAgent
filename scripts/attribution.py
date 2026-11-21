"""买入归因：反推每只基金的隐含平均买入净值，拆解盈亏来源。

前提（用户确认）：
  - 几乎只有买入，没有卖出 → holding_return 就是该基金的累计浮动盈亏，无已实现收益
  - cost = amount - holding_return 即累计投入成本

反推逻辑：
  value = shares × NAV_now
  cost  = shares × avg_cost_price
  => avg_cost_price = NAV_now × cost / value
因此"买了多少份"被消掉了，隐含成本价位是唯一确定的。

归因拆解（教程 §10 的横截面一致性检查）：
  总超额 = 实际盈亏 - 若买在同类基准上的盈亏
  再拆成 择基(选对了基金) 与 择时(买在了什么价位)
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT = Path(__file__).resolve().parent.parent
NAV_DIR = PROJECT / "data" / "my_portfolio_nav"
BENCH_DIR = PROJECT / "data" / "benchmark_nav"

# 资产类别 -> 对照基准（教程 §11.1 的 B1-B5 思路）
CLASS_BENCH = {
    "A股": "512890",      # 红利低波，A股权益的可投资基准
    "港股": "515080",     # 中证红利，港股无对应场内基准时用红利口径
    "海外股票": "513500",  # 标普500
    "黄金": "518880",     # 实物黄金
    "大宗商品": "518880",  # 无更好基准
    "债券": "511260",     # 10年国债
}


def load(dirpath: Path, code: str) -> pd.Series | None:
    f = dirpath / f"{code}.json"
    if not f.exists():
        return None
    rows = json.loads(f.read_text(encoding="utf-8"))
    if not rows:
        return None
    pairs = {}
    for r in rows:
        v = r.get("adj_nav") or r.get("unit_nav") or r.get("nav")
        if v and float(v) > 0:
            pairs[r["date"]] = float(v)
    s = pd.Series(pairs, dtype="float64").sort_index()
    s.index = pd.to_datetime(s.index)
    return s[~s.index.duplicated(keep="last")]


def find_holding_window(nav: pd.Series, cost_price: float) -> tuple[str, str, float]:
    """隐含成本价位落在净值历史的哪个位置。

    返回 (最早触及日期, 最近触及日期, 隐含持有天数)。
    净值单调下跌时成本价可能永远达不到 → 返回最后日期，说明成本高于任何历史净值。
    """
    below = nav[nav <= cost_price]
    if below.empty:
        return str(nav.index[-1].date()), str(nav.index[-1].date()), 0.0
    first = below.index[0]
    # 从右往左找最近一次在该价位附近（±2%）的日期
    near = nav[(nav >= cost_price * 0.98) & (nav <= cost_price * 1.02)]
    last = near.index[-1] if not near.empty else below.index[-1]
    days = (nav.index[-1] - last).days
    return str(first.date()), str(last.date()), float(days)


def main():
    port = json.loads((PROJECT / "data" / "my_portfolio.json").read_text(encoding="utf-8"))
    idx = json.loads((NAV_DIR / "_index.json").read_text(encoding="utf-8"))
    from eval_benchmarks import resolve_holdings

    code_map, missing, _ = resolve_holdings(port["holdings"], idx)

    rows = []
    for h in port["holdings"]:
        c = code_map.get(h["fund_name"])
        tv = h["amount"]; pl = h["holding_return"]
        cost = tv - pl
        rows.append({
            "name": h["fund_name"], "code": c or "?", "cls": h.get("asset_class", ""),
            "value": tv, "cost": cost, "pl": pl,
            "ret": pl / cost if cost else np.nan,
        })
    df = pd.DataFrame(rows)
    TOTAL_COST = df["cost"].sum()
    TOTAL_PL = df["pl"].sum()

    print("=" * 104)
    print(f"总投入 {TOTAL_COST:,.2f}  市值 {df['value'].sum():,.2f}  "
          f"盈亏 {TOTAL_PL:+,.2f}  收益率 {TOTAL_PL/TOTAL_COST*100:+.2f}%")
    print("=" * 104)

    # ── 贡献度：每只基金对总收益率的贡献（bp）────────────────────────
    print(f"\n{'基金':34} {'成本':>9} {'盈亏':>9} {'收益率':>8} {'贡献bp':>8} {'权重':>7}")
    print("-" * 104)
    df["contrib_bp"] = df["pl"] / TOTAL_COST * 1e4
    df["weight"] = df["cost"] / TOTAL_COST
    for _, r in df.sort_values("contrib_bp").iterrows():
        print(f"{r['name'][:32]:34} {r['cost']:>9.0f} {r['pl']:>+9.2f} "
              f"{r['ret']*100:>+7.2f}% {r['contrib_bp']:>+8.0f} {r['weight']*100:>6.1f}%")

    # ── 按类别汇总 ──────────────────────────────────────────────────
    print(f"\n{'类别':10} {'成本权重':>9} {'盈亏':>10} {'收益率':>8} {'贡献bp':>8}")
    print("-" * 52)
    g = df.groupby("cls").agg(
        权重=("cost", lambda x: x.sum() / TOTAL_COST),
        盈亏=("pl", "sum"),
        贡献bp=("contrib_bp", "sum"),
    )
    g["收益率"] = g["盈亏"] / df.groupby("cls")["cost"].sum()
    for cls, r in g.sort_values("贡献bp").iterrows():
        print(f"{cls:10} {r['权重']*100:>8.1f}% {r['盈亏']:>+10.2f} "
              f"{r['收益率']*100:>+7.2f}% {r['贡献bp']:>+8.0f}")

    # ── 反推买入价位 ────────────────────────────────────────────────
    print("\n" + "=" * 104)
    print("反推隐含平均买入价位（只买不卖 ⇒ 成本价唯一确定）")
    print("=" * 104)
    print(f"{'基金':30} {'现净值':>9} {'隐含成本价':>10} {'价差':>8} {'持有天数':>9}  最近同价位日期")
    print("-" * 104)
    detail = []
    for _, r in df.iterrows():
        src = BENCH_DIR if r["code"] == "518880" else NAV_DIR
        nav = load(src, r["code"]) if r["code"] != "?" else None
        if nav is None or nav.empty:
            print(f"{r['name'][:28]:30} {'无净值数据':>9}")
            continue
        nav_now = nav.iloc[-1]
        cost_price = nav_now * r["cost"] / r["value"]
        first, last, days = find_holding_window(nav, cost_price)
        gap = (cost_price / nav_now - 1) * 100
        print(f"{r['name'][:28]:30} {nav_now:>9.4f} {cost_price:>10.4f} "
              f"{gap:>+7.2f}% {days:>9.0f}  {last}")
        detail.append({**r, "nav_now": nav_now, "cost_price": cost_price,
                       "gap_pct": gap, "days": days, "last_touch": last})

    d = pd.DataFrame(detail)

    # ── 追高幅度 ────────────────────────────────────────────────────
    # 只用完整可用历史，不选窗口。
    #   基金自身收益 = 数据起点买入至今（一次性买入者拿到的）
    #   你的收益     = 你的加权平均成本至今
    #   差额         = 你在净值曲线上的买入位置偏离起点的程度
    # 差额为负 ⇒ 你的成本高于起点价 ⇒ 买在了上涨之后（追高），
    #            且这个推断不依赖任何具体交易日期。
    print("\n" + "=" * 104)
    print("追高幅度（你的成本 vs 该基金数据起点的净值）")
    print("=" * 104)
    print(f"{'基金':28} {'你的收益':>8} {'起点买入者':>10} {'追高幅度':>9} {'权重':>6}  判定")
    print("-" * 104)
    rows2 = []
    for _, r in d.iterrows():
        src = BENCH_DIR if r["code"] == "518880" else NAV_DIR
        nav = load(src, r["code"])
        if nav is None or len(nav) < 60:
            continue
        fund_ret = nav.iloc[-1] / nav.iloc[0] - 1
        chase = r["ret"] - fund_ret
        rows2.append({"name": r["name"], "cls": r["cls"], "weight": r["weight"],
                      "your": r["ret"], "fund": fund_ret, "chase": chase,
                      "start": str(nav.index[0].date())})
        verdict = "追高" if chase < -0.10 else ("略高" if chase < -0.02 else "低位/持平")
        print(f"{r['name'][:26]:28} {r['ret']*100:>+7.2f}% {fund_ret*100:>+9.2f}% "
              f"{chase*100:>+8.2f}% {r['weight']*100:>5.1f}%  {verdict}")

    d2 = pd.DataFrame(rows2)
    if not d2.empty:
        print("\n" + "-" * 104)
        w = d2["weight"] / d2["weight"].sum()
        print(f"加权平均：你的收益 {np.average(d2['your'], weights=d2['weight'])*100:+.2f}%  "
              f"起点买入者 {np.average(d2['fund'], weights=d2['weight'])*100:+.2f}%  "
              f"追高幅度 {np.average(d2['chase'], weights=d2['weight'])*100:+.2f}%")
        chase_neg = d2[d2["chase"] < -0.10]
        print(f"\n追高 >10pp 的基金: {len(chase_neg)} / {len(d2)} 只，"
              f"合计权重 {chase_neg['weight'].sum()*100:.1f}%")
        for _, r in chase_neg.sort_values("chase").iterrows():
            print(f"    {r['name'][:30]:32} 你 {r['your']*100:>+7.1f}%  vs 起点 {r['fund']*100:>+7.1f}%  "
                  f"差 {(r['your']-r['fund'])*100:>+7.1f}pp  权重 {r['weight']*100:.1f}%")

    out = PROJECT / "reports" / "attribution.json"
    d.to_json(out, orient="records", force_ascii=False, indent=2, date_format="iso")
    print(f"\n-> {out}")


if __name__ == "__main__":
    main()
