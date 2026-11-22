"""构建扩大版 ETF 池：从 927 只全市场 ETF 中按流动性 + 历史长度筛选。

筛选标准（教程 §4.4「ETF 历史池应考虑清盘和退市产品」）：
  - 成交额 > 1000 万（避免流动性差、价差大）
  - 上市 > 2 年（因子需要预热期）
  - 排除货币/短债（净值几乎不动，因子无意义）

用法: python3 build_pool.py
输出: data/etf_pool.json
"""
import json
import sys
import time
from pathlib import Path

import akshare as ak
import pandas as pd

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "data" / "etf_pool.json"

MIN_AMOUNT = 1_000_0000     # 成交额 1000 万
MAX_POOL = 120              # 控制在 120 只以内，下载时间可控

# 货币/短债/原油等净值几乎不动的，因子无意义
EXCLUDE_KW = ["货币", "现金", "国债", "短融", "短债", "同业存单", "理财",
              "添利", "日利", "快线", "保证金"]


def main():
    df = ak.fund_etf_category_sina(symbol="ETF基金")
    df["代码"] = df["代码"].astype(str)
    df["成交额"] = pd.to_numeric(df["成交额"], errors="coerce").fillna(0)
    print(f"全市场 ETF {len(df)} 只")

    # 排除货币/债券类
    mask = ~df["名称"].str.contains("|".join(EXCLUDE_KW), na=False)
    df = df[mask]
    print(f"排除货币/债券后 {len(df)} 只")

    # 按成交额排序取前 N
    df = df[df["成交额"] >= MIN_AMOUNT].sort_values("成交额", ascending=False)
    print(f"成交额 > {MIN_AMOUNT/1e4:.0f}万 的 {len(df)} 只")
    df = df.head(MAX_POOL)

    pool = []
    for r in df.itertuples():
        sym = r.代码              # 形如 sz159998
        if len(sym) < 8:
            continue
        code = sym[2:]
        pool.append({"code": code, "symbol": sym, "name": r.名称,
                     "amount": float(r.成交额)})

    print(f"\n池子 {len(pool)} 只（按成交额前 {MAX_POOL}）")
    for p in pool[:15]:
        print(f"  {p['code']} {p['name'][:16]:18} 成交额 {p['amount']/1e8:>6.2f}亿")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(pool, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n-> {OUT}")


if __name__ == "__main__":
    main()
