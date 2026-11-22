"""拉取基准 ETF 净值，供 docs/个人量化交易教程.md 第十章/B1-B5 对照表使用。

用法: python3 scripts/fetch_benchmark_nav.py
输出: data/benchmark_nav/<code>.json  [{date, nav}]  升序
"""
import json
import sys
import time
from pathlib import Path

import akshare as ak

PROJECT = Path(__file__).resolve().parent.parent
OUT_DIR = PROJECT / "data" / "benchmark_nav"

# 教程 §11.1 对照表 B1-B5 + 组合候选
BENCHMARKS = {
    # B1 宽基基准
    "510300": "沪深300ETF",
    "510500": "中证500ETF",
    "512100": "中证1000ETF",
    "159915": "创业板ETF",
    "588000": "科创50ETF",
    # B2-B5 红利类
    "515080": "中证红利ETF",
    "512890": "红利低波ETF",
    "515650": "红利质量ETF",
    "563020": "自由现金流ETF",
    # 跨资产
    "513100": "纳指ETF",
    "513500": "标普500ETF",
    "511260": "10年国债ETF",
    "511520": "5年国债ETF",
    "518880": "黄金ETF",
    "159985": "豆粕ETF",
    "511880": "银华日利(货币)",
}


def fetch(code: str, retries: int = 4):
    for i in range(retries):
        try:
            df = ak.fund_open_fund_info_em(symbol=code, indicator="累计净值走势")
            if df is None or df.empty:
                raise ValueError("empty")
            rows = [
                {"date": str(r["净值日期"]), "nav": float(r["累计净值"])}
                for _, r in df.iterrows()
                if r["累计净值"] == r["累计净值"]  # NaN 剔除
            ]
            rows.sort(key=lambda x: x["date"])
            return rows
        except Exception as e:
            if i == retries - 1:
                print(f"  FAIL {code}: {type(e).__name__} {str(e)[:70]}", file=sys.stderr)
                return None
            time.sleep(1.5 * (i + 1))


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ok, fail = [], []
    for code, name in BENCHMARKS.items():
        rows = fetch(code)
        if rows:
            (OUT_DIR / f"{code}.json").write_text(
                json.dumps(rows, ensure_ascii=False), encoding="utf-8"
            )
            ok.append((code, name, len(rows), rows[0]["date"], rows[-1]["date"]))
        else:
            fail.append((code, name))
        time.sleep(0.8)

    print(f"\n{'code':8} {'n':>5} {'start':>11} {'end':>11}  name")
    for c, n, cnt, s, e in ok:
        print(f"{c:8} {cnt:>5} {s:>11} {e:>11}  {n}")
    if fail:
        print("\nFAILED:", [c for c, _ in fail])
    print(f"\nsaved -> {OUT_DIR}")


if __name__ == "__main__":
    main()
