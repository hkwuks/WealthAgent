"""校验 data/my_portfolio_nav 与东财实时净值是否一致。

本地文件若被算成"累计净值"或存在错标，会直接污染所有回测结果。
用法: python3 scripts/verify_local_nav.py
"""
import json
import sys
import time
from pathlib import Path

import akshare as ak

PROJECT = Path(__file__).resolve().parent.parent
NAV_DIR = PROJECT / "data" / "my_portfolio_nav"


def live(code: str, indicator="累计净值走势"):
    for i in range(3):
        try:
            df = ak.fund_open_fund_info_em(symbol=code, indicator=indicator)
            df = df.sort_values("净值日期")
            col = [c for c in df.columns if "净值" in c and c != "净值日期"][0]
            return str(df["净值日期"].iloc[0]), float(df[col].iloc[0]), \
                   str(df["净值日期"].iloc[-1]), float(df[col].iloc[-1]), len(df)
        except Exception:
            time.sleep(1.5)
    return None


def main():
    rows = []
    for f in sorted(NAV_DIR.glob("[0-9]*.json")):
        code = f.stem
        d = json.loads(f.read_text(encoding="utf-8"))
        if not d:
            rows.append((code, "EMPTY", None, None, None, None))
            continue
        d.sort(key=lambda r: r["date"])
        lv = d[-1].get("adj_nav") or d[-1].get("unit_nav")
        lstart = d[0]["date"]
        r = live(code)
        rows.append((code, "OK", lstart, d[-1]["date"], lv, r))
        time.sleep(0.6)

    print(f"{'code':8} {'本地末日':>11} {'本地净值':>10} {'东财末日':>11} {'东财净值':>10} "
          f"{'偏差':>8}  判定")
    bad = []
    for code, st, ls, le, lv, lr in rows:
        if st != "OK" or lr is None:
            print(f"{code:8} {st:>11}")
            continue
        rstart, rv0, rend, rv1, n = lr
        dev = (lv / rv1 - 1) * 100 if lv and rv1 else float("nan")
        # 允许 3% 偏差（本地可能滞后或含分红差异），超过则判定为错误
        verdict = "OK" if abs(dev) < 3 else "** 错误 **"
        if verdict != "OK":
            bad.append((code, lv, rv1, dev))
        print(f"{code:8} {le:>11} {lv:>10.4f} {rend:>11} {rv1:>10.4f} "
              f"{dev:>7.2f}%  {verdict}")

    print(f"\n共 {len(rows)} 只，其中 {len(bad)} 只净值与东财不一致：")
    for code, lv, rv1, dev in bad:
        print(f"  {code}: 本地 {lv:.4f} vs 东财 {rv1:.4f}  ({dev:+.1f}%)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
