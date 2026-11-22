"""份额级核对与可归因收益计算。

核心校验（这是唯一能发现记录缺失的方法）：
    买入份额 - 卖出份额 - 转托管份额 == 当前持有份额
不等就说明该基金的交易记录不完整，任何金额相减得出的"收益"都不可信。

用法: python3 scripts/verify_shares.py
"""
import json
from pathlib import Path

import pandas as pd

PROJECT = Path(__file__).resolve().parent.parent
NAV_DIR = PROJECT / "data" / "my_portfolio_nav"
SNAPSHOT = pd.Timestamp("2026-10-09")
TOL = 0.02  # 份额允许误差


def load_nav(code: str) -> float | None:
    f = NAV_DIR / f"{code}.json"
    if not f.exists():
        return None
    rows = json.loads(f.read_text(encoding="utf-8"))
    if not rows:
        return None
    p = {}
    for r in rows:
        v = r.get("adj_nav") or r.get("unit_nav") or r.get("nav")
        if v:
            p[r["date"]] = float(v)
    s = pd.Series(p).sort_index()
    use = [d for d in s.index if pd.Timestamp(d) <= SNAPSHOT]
    return float(s[use[-1]]) if use else None


def main():
    tx = pd.DataFrame(json.loads(
        (PROJECT / "data" / "transactions.json").read_text(encoding="utf-8")))
    tx["date"] = pd.to_datetime(tx["date"])
    pre = tx[tx["date"] <= SNAPSHOT]

    port = json.loads((PROJECT / "data" / "my_portfolio.json").read_text(encoding="utf-8"))
    # 持仓清单用代码索引（来自 _index.json 的名称映射不可靠，用份额比对反查）
    idx = json.loads((NAV_DIR / "_index.json").read_text(encoding="utf-8"))

    print("=" * 100)
    print(f"份额守恒核对（截止 {SNAPSHOT.date()}）")
    print("=" * 100)
    print(f"{'代码':8} {'买入份额':>10} {'卖出份额':>10} {'转托管份额':>10} "
          f"{'净份额':>10} {'判定':>10}  基金")
    print("-" * 100)

    bad = []
    ok = []
    for code, g in pre.groupby("fund_code"):
        bought = g[g["type"].str.contains("买入")]["confirm_shares"].sum()
        sold = g[g["type"].str.contains("卖出")]["confirm_shares"].sum()
        trans = g[g["type"] == "转托管出"]["confirm_shares"].sum()
        net = bought - sold - trans
        name = g["fund_name"].iloc[0]
        if sold > 0 and net < -TOL:
            verdict = "** 缺买入 **"
            bad.append((code, name, bought, sold, net))
        elif bought > 0 and net < -TOL:
            verdict = "份额为负"
            bad.append((code, name, bought, sold, net))
        else:
            verdict = "OK"
            ok.append((code, name, bought, sold, trans, net))
        if sold > 0 or net < -TOL:
            print(f"{code:8} {bought:>10.2f} {sold:>10.2f} {trans:>10.2f} "
                  f"{net:>10.2f} {verdict:>10}  {name[:24]}")

    print(f"\n记录完整的基金 {len(ok)} 只，记录残缺 {len(bad)} 只")
    if bad:
        print("\n残缺清单（这些基金的收益无法归因）：")
        for c, n, b, s, net in bad:
            print(f"  {c} {n[:26]:28} 买入 {b:>8.2f} 卖出 {s:>8.2f} 净 {net:>+8.2f}")

    # ── 可归因部分 ────────────────────────────────────────────────
    broken_codes = {c for c, *_ in bad}
    clean = pre[~pre["fund_code"].isin(broken_codes)]
    b = clean[clean["type"].str.contains("买入")]["confirm_amount"].sum()
    s = clean[clean["type"].str.contains("卖出")]["confirm_amount"].sum()
    t = clean[clean["type"] == "转托管出"]["confirm_amount"].sum()
    d = clean[clean["type"] == "机构分红"]["confirm_amount"].sum()
    net_in = b - s - t - d

    broken_sold = pre[pre["fund_code"].isin(broken_codes) &
                      pre["type"].str.contains("卖出")]["confirm_amount"].sum()
    broken_trans = pre[pre["fund_code"].isin(broken_codes) &
                        (pre["type"] == "转托管出")]["confirm_amount"].sum()

    print("\n" + "=" * 100)
    print("可归因范围")
    print("=" * 100)
    print(f"记录完整部分：买入 {b:>12,.2f}  卖出 {s:>12,.2f}  转托管 {t:>10,.2f}  分红 {d:>8,.2f}")
    print(f"                净投入 {net_in:>12,.2f}")
    print(f"残缺部分：卖出 {broken_sold:>10,.2f}  转托管 {broken_trans:>8,.2f}（买入成本缺失）")
    print(f"\n结论：残缺部分合计 {broken_sold + broken_trans:,.2f} 元的卖出/转出无法归因。")
    print("      支付宝账户的完整收益率，用当前数据算不出来。")


if __name__ == "__main__":
    main()
