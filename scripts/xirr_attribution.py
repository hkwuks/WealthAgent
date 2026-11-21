"""基于真实交易记录做 MWR / TWR 归因。

MWR（资金加权）= XIRR，反映你的钱真实的年化回报
TWR（时间加权）= 剔除申购节奏后的组合表现
两者之差 = 择时/资金进出时点的价值

关键处理：
  1. 转托管出（2026-08-26）不是卖出，是转到券商账户，不能算收益
  2. 机构分红是收益的一部分，不是新增本金
  3. 赎回要按当日净值折算，而不是按确认金额当现金流（确认金额就是现金流）

输出: reports/xirr_report.json + 控制台
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT = Path(__file__).resolve().parent.parent
NAV_DIR = PROJECT / "data" / "my_portfolio_nav"
SNAPSHOT = "2026-10-09"


def load_nav(code: str) -> pd.Series | None:
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
    s.index = pd.to_datetime(s.index)
    return s


def xirr(flows: list[tuple[pd.Timestamp, float]]) -> float:
    """不规则现金流的年化内部收益率，二分法。"""
    if len(flows) < 2:
        return np.nan
    flows = sorted(flows)
    t0 = flows[0][0]
    yrs = np.array([(d - t0).days / 365.25 for d, _ in flows], dtype=float)
    amt = np.array([a for _, a in flows], dtype=float)
    if not (amt.min() < 0 < amt.max()):
        return np.nan

    def npv(r: float) -> float:
        return float(np.sum(amt / np.power(1 + r, yrs)))

    lo, hi = -0.9999, 2.0
    while npv(lo) * npv(hi) > 0:
        hi *= 2
        if hi > 100:
            return np.nan
    for _ in range(300):
        mid = (lo + hi) / 2
        if npv(lo) * npv(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def main():
    tx = pd.DataFrame(json.loads(
        (PROJECT / "data" / "transactions.json").read_text(encoding="utf-8")))
    tx["date"] = pd.to_datetime(tx["date"])
    snap = pd.Timestamp(SNAPSHOT)

    # ── 组合层 MWR（支付宝口径）──────────────────────────────────────
    # 该 PDF 只含支付宝账户。现金流方向（投资者视角）：
    #   买入       -> 现金流出，负
    #   卖出       -> 现金流入，正
    #   转托管出   -> 资金离开支付宝，正（不是亏损，但确实从本账户流出）
    #   机构分红   -> confirm_shares 全为 0，是现金分红，正
    #   期末市值   -> 正，但只能用支付宝口径 59,497.01，不能用全账户 69,198.22
    SNAP_VALUE = 59497.01          # 支付宝账户快照市值
    DYNAMIC = True                 # 分红按现金流处理

    rows_by_year: dict[int, list] = {}
    for _, r in tx.iterrows():
        amt = r["confirm_amount"]
        if amt <= 0:
            continue
        if "买入" in r["type"]:
            rows_by_year.setdefault(r["date"].year, []).append((r["date"], -amt, r["type"]))
        elif r["type"] in ("机构分红", "转托管出") or "卖出" in r["type"]:
            rows_by_year.setdefault(r["date"].year, []).append((r["date"], amt, r["type"]))

    flows = [(d, a) for v in rows_by_year.values() for d, a, _ in v]
    flows.append((snap, SNAP_VALUE))

    rate = xirr(flows)
    total_in = -sum(a for _, a in flows if a < 0)
    total_out = sum(a for d, a in flows if a > 0 and d < snap)
    days = (snap - min(d for d, _ in flows)).days

    print("=" * 76)
    print("资金加权收益率 MWR (XIRR) —— 支付宝口径")
    print("=" * 76)
    print(f"买入现金流合计       {total_in:>12,.2f}")
    print(f"卖出+转出+分红合计   {total_out:>12,.2f}")
    print(f"期末市值(2026-10-09) {SNAP_VALUE:>12,.2f}")
    print(f"投资跨度             {days:>12} 天 ({days/365.25:.2f} 年)")
    print(f"\n>>> 资金加权年化 MWR = {rate*100:+.2f}%")

    simple = (SNAP_VALUE + total_out - total_in) / total_in
    print(f"\n简单累计收益率（不考虑时间）= {simple*100:+.2f}%")
    print(f"  校验：期末 + 收回 - 投入 = {SNAP_VALUE + total_out - total_in:+,.2f} 元")
    print(f"  净投入 {total_in - total_out:,.2f} -> 市值 {SNAP_VALUE:,.2f}，"
          f"浮盈 {SNAP_VALUE - total_in + total_out:+,.2f} 元")

    # ── 逐基金 MWR ──────────────────────────────────────────────────
    print("\n" + "=" * 76)
    print("逐只基金 XIRR（仅含≥90天且有净投入的）")
    print("=" * 76)
    print(f"{'代码':8} {'基金':26} {'净投入':>10} {'天数':>6} {'XIRR':>8}")
    per = []
    for code, g in tx.groupby("fund_code"):
        g = g[g["type"] != "转托管出"]
        if g.empty:
            continue
        fl = []
        for _, r in g.iterrows():
            amt = r["confirm_amount"]
            if amt <= 0:
                continue
            fl.append((r["date"], -amt if "买入" in r["type"] else amt))
        net = -sum(a for _, a in fl)
        if net <= 0:
            continue
        start = min(d for d, _ in fl)
        span = (snap - start).days
        if span < 90:
            continue
        # 用最新净值估算期末价值
        nav = load_nav(code)
        if nav is None or nav.empty:
            continue
        nav_s = nav[nav.index <= snap]
        if nav_s.empty:
            continue
        shares = 0.0
        for _, r in g.iterrows():
            if "买入" in r["type"]:
                shares += r["confirm_shares"]
            elif "卖出" in r["type"]:
                shares -= r["confirm_shares"]
        end_val = shares * nav_s.iloc[-1]
        fl.append((snap, end_val))
        rr = xirr(fl)
        name = g["fund_name"].iloc[0]
        per.append({"code": code, "name": name, "net": net, "days": span, "xirr": rr})
        if rr == rr:
            print(f"{code:8} {name[:24]:26} {net:>10,.0f} {span:>6} {rr*100:>+7.2f}%")

    if per:
        df = pd.DataFrame(per)
        df = df[df["xirr"].notna()]
        w = df["net"] / df["net"].sum()
        print(f"\n净投入加权平均 XIRR = {(df['xirr']*w).sum()*100:+.2f}%")
        print(f"正收益基金 {(df['xirr']>0).sum()} 只 / {len(df)} 只")

    out = PROJECT / "reports" / "xirr_report.json"
    out.write_text(json.dumps({
        "mwr": rate, "simple": simple,
        "total_in": total_in, "total_out": total_out,
        "final_value": final_value, "days": days, "per_fund": per,
    }, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n-> {out}")


if __name__ == "__main__":
    main()
