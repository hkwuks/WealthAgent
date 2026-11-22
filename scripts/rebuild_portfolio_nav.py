"""重建 data/my_portfolio_nav：统一用东财「累计净值」，消除单位净值/累计净值口径混用。

原先的问题：
  1. 16 只基金 adj_nav 全为 null → strategy_backtest.load_nav() 读出来是 None
  2. 部分基金存的是 unit_nav（不含分红），系统性低估收益（163806 中位偏差 25%）

输出格式保持兼容: [{date, unit_nav, adj_nav}]，两者都写累计净值。
用法: python3 scripts/rebuild_portfolio_nav.py
"""
import json
import sys
import time
from pathlib import Path

import akshare as ak

PROJECT = Path(__file__).resolve().parent.parent
NAV_DIR = PROJECT / "data" / "my_portfolio_nav"
INDEX = NAV_DIR / "_index.json"


def fetch(code: str, retries: int = 4):
    for i in range(retries):
        try:
            df = ak.fund_open_fund_info_em(symbol=code, indicator="累计净值走势")
            if df is None or df.empty:
                raise ValueError("empty")
            df = df.sort_values("净值日期")
            col = [c for c in df.columns if "净值" in c and c != "净值日期"][0]
            rows = []
            for _, r in df.iterrows():
                v = r[col]
                if v != v or v is None:  # NaN
                    continue
                rows.append({"date": str(r["净值日期"]), "unit_nav": float(v), "adj_nav": float(v)})
            if not rows:
                raise ValueError("all NaN")
            return rows
        except Exception as e:
            if i == retries - 1:
                print(f"  FAIL {code}: {type(e).__name__} {str(e)[:60]}", file=sys.stderr)
                return None
            time.sleep(1.5 * (i + 1))
    return None


def main():
    idx = json.loads(INDEX.read_text(encoding="utf-8"))
    codes = sorted(idx.keys())
    print(f"重建 {len(codes)} 只基金的净值缓存...\n")

    ok, fail, empty = [], [], []
    for n, code in enumerate(codes, 1):
        rows = fetch(code)
        name = idx[code].get("name", "")
        if rows is None:
            fail.append((code, name))
            continue
        if len(rows) < 30:
            empty.append((code, name, len(rows)))
        (NAV_DIR / f"{code}.json").write_text(
            json.dumps(rows, ensure_ascii=False), encoding="utf-8"
        )
        idx[code].update({"count": len(rows), "start": rows[0]["date"], "end": rows[-1]["date"]})
        ok.append((code, name, len(rows), rows[0]["date"], rows[-1]["date"]))
        print(f"[{n:>2}/{len(codes)}] {code} {name[:24]:26} {len(rows):>5} 条  "
              f"{rows[0]['date']} ~ {rows[-1]['date']}")
        time.sleep(0.5)

    INDEX.write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n成功 {len(ok)} 只 / 失败 {len(fail)} 只 / 数据过少 {len(empty)} 只")
    for code, name in fail:
        print(f"  FAIL {code} {name}")
    for code, name, n in empty:
        print(f"  THIN {code} {name} 仅 {n} 条")
    return 0 if not fail else 1


if __name__ == "__main__":
    sys.exit(main())
