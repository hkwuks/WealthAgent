"""解析蚂蚁财富基金交易明细 PDF（已去除首页）。

版面特点：日期被拆成两行，如
    '2026/11/1\n7 09:29'   ->  2026/11/17 09:29
    '2026/11/0\n6 09:38'   ->  2026/11/06 09:38
规则：第一段末尾的日期片段 + 第二段开头的数字 = 完整日期。

用法: python3 scripts/parse_alipay_pdf.py data/投资_无首页.pdf
输出: data/transactions.json  与  reports/交易汇总.txt
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd
import pdfplumber

PROJECT = Path(__file__).resolve().parent.parent


def clean(v) -> str:
    if v is None:
        return ""
    return re.sub(r"\s+", "", str(v))


def parse_dt(raw: str, order_no: str = "", confirm_raw: str = "") -> tuple[str | None, str | None]:
    """把 '2026/11/1\\n7 09:29' 还原成 ('2026-11-17', '09:29')。

    边界情况：
      - 日期单元格被截成单行 '2025/05/0'（日数字溢出到别的单元格）
        → 用订单号前 8 位（YYYYMMDD）补齐，这是最可靠的信源
    """
    s = str(raw or "")
    parts = s.split("\n")

    def _fix(y, mo, d):
        d = int(d)
        if d == 0 and order_no and len(order_no) >= 8 and order_no[:8].isdigit():
            d = int(order_no[6:8])
        if d == 0:
            m = re.search(r"(\d{4})/(\d{1,2})/(\d{1,2})", str(confirm_raw))
            if m:
                d = int(m.group(3))
        return f"{y}-{int(mo):02d}-{d:02d}" if d else None

    def _tm(x):
        tm = re.search(r"(\d{1,2}):(\d{2})", x)
        return f"{int(tm.group(1)):02d}:{tm.group(2)}" if tm else None

    if len(parts) < 2:
        m = re.search(r"(\d{4})/(\d{1,2})/(\d{1,2})", s)
        if not m:
            return None, None
        y, mo, d = m.groups()
        return _fix(y, mo, d), _tm(s)

    head, tail = parts[0].strip(), parts[1].strip()
    m = re.match(r"(\d{4})/(\d{1,2})/(\d{1,2})$", head)
    if not m:
        return None, None
    y, mo, dpart = m.groups()
    tpart = re.match(r"\s*(\d{1,2})", tail)
    day = f"{dpart}{tpart.group(1)}" if tpart else dpart
    return _fix(y, mo, day), _tm(tail)


def num(v) -> float:
    s = clean(v).replace(",", "")
    if s in ("", "/", "-"):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


HEADER = ["订单号", "交易时间", "交易类型", "基金名称", "组合基金名称",
          "基金代码", "申请金额", "申请份额", "确认金额", "确认份额",
          "手续费", "确认日期"]

# 由第一次扫描填充：代码 -> 该代码出现过的最长（最完整）名称
_NAMES: dict[str, str] = {}


def canon_name(code: str, fallback: str) -> str:
    best = _NAMES.get(code, "")
    return best if len(best) > len(fallback) else fallback


def scan_names(pdf) -> None:
    """第一遍：收集每个基金代码最完整的名称，用于修复被换行截断的名字。"""
    for page in pdf.pages:
        for table in page.extract_tables():
            for row in table:
                if not row or len(row) < 12:
                    continue
                code = clean(row[5])
                name = clean(row[3])
                if re.fullmatch(r"\d{6}", code) and len(name) > len(_NAMES.get(code, "")):
                    _NAMES[code] = name


def main(pdf_path: str):
    recs = []
    with pdfplumber.open(pdf_path) as pdf:
        scan_names(pdf)
        for pi, page in enumerate(pdf.pages, 1):
            for table in page.extract_tables():
                for row in table:
                    if not row or len(row) < 12:
                        continue
                    vals = [clean(c) for c in row]
                    if vals[0] == "订单号" or "交易时间" in vals[:3]:
                        continue
                    if not re.search(r"\d{4}/", str(row[1])):
                        continue
                    order = clean(row[0])
                    d, t = parse_dt(row[1], order, str(row[11]))
                    d2, _ = parse_dt(row[11], order)
                    # 名字被换行拆断时（如 '国泰中证'），用同代码最长的名字回填
                    fname = vals[3]
                    if len(fname) < 6:
                        fname = canon_name(vals[5], fname)
                    recs.append({
                        "page": pi,
                        "date": d,
                        "time": t,
                        "type": vals[2],
                        "fund_name": fname,
                        "fund_code": vals[5],
                        "apply_amount": num(row[6]),
                        "confirm_amount": num(row[8]),
                        "confirm_shares": num(row[9]),
                        "fee": num(row[10]),
                        "confirm_date": d2,
                    })

    df = pd.DataFrame(recs)
    df = df[df["date"].notna()].copy()
    df = df.sort_values(["date", "time"]).reset_index(drop=True)

    print("=" * 78)
    print("解析结果")
    print("=" * 78)
    print(f"总记录数 {len(df)}")
    print(f"日期范围 {df['date'].min()} ~ {df['date'].max()}")
    print(f"页数 {df['page'].max()}")

    print("\n--- 交易类型分布 ---")
    for t, n in Counter(df["type"]).most_common():
        sub = df[df["type"] == t]
        print(f"  {t:10} {n:>5} 条   金额合计 {sub['confirm_amount'].sum():>12,.2f}")

    print("\n--- 按年统计 ---")
    df["year"] = df["date"].str[:4]
    print(f"{'年份':6} {'买入金额':>12} {'卖回金额':>12} {'分红':>10} {'笔数':>6}")
    for y, g in df.groupby("year"):
        buy = g[g["type"].str.contains("买入")]["confirm_amount"].sum()
        sell = g[g["type"].str.contains("卖出")]["confirm_amount"].sum()
        div = g[g["type"].str.contains("分红")]["confirm_amount"].sum()
        print(f"{y:6} {buy:>12,.2f} {sell:>12,.2f} {div:>10,.2f} {len(g):>6}")

    # 每只基金的净投入
    print("\n--- 每只基金净投入（买入 - 卖出）---")
    agg = df.groupby(["fund_code", "fund_name"]).apply(
        lambda g: pd.Series({
            "buy": g[g["type"].str.contains("买入")]["confirm_amount"].sum(),
            "sell": g[g["type"].str.contains("卖出")]["confirm_amount"].sum(),
            "div": g[g["type"].str.contains("分红")]["confirm_amount"].sum(),
            "n": len(g),
        }), include_groups=False)
    agg["net"] = agg["buy"] - agg["sell"]
    for (code, name), r in agg.sort_values("net", ascending=False).iterrows():
        print(f"  {code:8} {name[:24]:26} 买入 {r['buy']:>10,.2f}  卖回 {r['sell']:>9,.2f}  "
              f"净投入 {r['net']:>10,.2f}  {int(r['n']):>4} 笔")

    print(f"\n合计买入 {agg['buy'].sum():,.2f}  卖回 {agg['sell'].sum():,.2f}  "
          f"净投入 {agg['net'].sum():,.2f}  分红 {agg['div'].sum():,.2f}")

    out = PROJECT / "data" / "transactions.json"
    df.to_json(out, orient="records", force_ascii=False, indent=2)
    print(f"\n-> {out}")

    txt = PROJECT / "reports" / "交易汇总.txt"
    with open(txt, "w", encoding="utf-8") as f:
        f.write(df.to_string())
    print(f"-> {txt}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/投资_无首页.pdf")
