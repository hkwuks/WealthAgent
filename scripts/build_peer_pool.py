"""同类池构建器 —— 让「同类百分位」有真实分母。

问题：用户持有 27 只基金散落在 11 个 fund_type 里，多数类型只有 1~4 只，
同类型分位没有统计意义（1 只基金的分位恒为 50 或 100）。

做法：按 fund_type 从全市场拉取样成员的真实净值入 nav_history，
使每类至少有 --per-type 只可比基金。之后暴露接口按同类型算横截面分位。

用法:
    python3 scripts/build_peer_pool.py --per-type 80
    python3 scripts/build_peer_pool.py --per-type 80 --dry-run   # 只看会拉哪些
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

# 东财接口必须直连；代理会让 push2 系接口失败
for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(_k, None)

KEEP_ROWS = 520          # 每只基金只保留最近约 2 年，控制库体积
WORKERS = 8
TYPES_FILE = PROJECT / "data" / "fund_types.json"


def _fetch(code: str) -> tuple[str, int]:
    import akshare as ak

    try:
        df = ak.fund_open_fund_info_em(symbol=code, indicator="单位净值走势")
    except Exception:
        return code, -1
    if df is None or df.empty:
        return code, 0
    try:
        date_col = "净值日期" if "净值日期" in df.columns else "日期"
        nav_col = "单位净值" if "单位净值" in df.columns else "累计净值"
        tail = df[[date_col, nav_col]].tail(KEEP_ROWS)
        rows = [
            (code, str(r[date_col])[:10], float(r[nav_col]), None, "eastmoney")
            for _, r in tail.iterrows()
            if r[nav_col] and float(r[nav_col]) > 0
        ]
    except Exception:
        return code, -2

    from backend.fund_quant.data.storage import get_conn

    with get_conn() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO nav_history "
            "(fund_code, date, nav, adjusted_nav, source) VALUES (?,?,?,?,?)",
            rows,
        )
    return code, len(rows)


def load_type_map(refresh: bool = False) -> dict[str, str]:
    """基金代码 -> 基金类型。缓存到 data/fund_types.json。"""
    if TYPES_FILE.exists() and not refresh:
        return json.loads(TYPES_FILE.read_text(encoding="utf-8"))
    import akshare as ak

    df = ak.fund_name_em()
    m = dict(zip(df["基金代码"].astype(str), df["基金类型"]))
    TYPES_FILE.write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
    return m


def target_types() -> list[str]:
    """用户持有基金涉及的 fund_type。"""
    funds_file = PROJECT / "data" / "backend" / "funds.json"
    if not funds_file.exists():
        raise SystemExit(f"缺少 {funds_file}")
    funds = json.loads(funds_file.read_text(encoding="utf-8"))
    seen, out = set(), []
    for f in funds:
        t = f.get("fund_type")
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-type", type=int, default=80)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--refresh-types", action="store_true")
    args = ap.parse_args()

    from backend.fund_quant.data.storage import get_conn

    tmap = load_type_map(refresh=args.refresh_types)
    types = target_types()
    with get_conn() as conn:
        have = {r[0] for r in conn.execute("SELECT DISTINCT fund_code FROM nav_history")}

    plan: list[str] = []
    recheck: list[str] = []   # 已有代码但行数太少，需要补
    with get_conn() as conn:
        thin = {
            r[0] for r in conn.execute(
                "SELECT fund_code FROM nav_history GROUP BY fund_code HAVING count(*) < 60")
        }

    for t in types:
        members = [c for c, ty in tmap.items() if ty == t]
        covered = [c for c in members if c in have]
        need = max(0, args.per_type - len(covered))
        if need:
            plan.extend([c for c in members if c not in have][:need])
        recheck.extend([c for c in covered if c in thin])

    print(f"类型 {len(types)} 个: {types}")
    print(f"已有净值 {len(have)} 只，其中行数不足 60 的 {len(thin)} 只")
    print(f"计划下载 {len(plan)} 只（每类补到 {args.per_type} 只）")

    if args.dry_run:
        for t in types:
            members = [c for c, ty in tmap.items() if ty == t]
            cov = sum(1 for c in members if c in have)
            print(f"  {t:20s} 全市场 {len(members):5d}  已有 {cov:4d}")
        return

    targets = plan + recheck
    if not targets:
        print("无需下载")
        return

    t0, ok, fail = time.time(), 0, 0
    with cf.ThreadPoolExecutor(WORKERS) as ex:
        for i, (code, n) in enumerate(ex.map(_fetch, targets), 1):
            if n > 0:
                ok += 1
            else:
                fail += 1
            if i % 25 == 0 or i == len(targets):
                el = time.time() - t0
                print(f"  [{i}/{len(targets)}] ok={ok} fail={fail} "
                      f"{el:.0f}s ({i / max(el, 1e-9):.1f}/s)")

    with get_conn() as conn:
        total = conn.execute("SELECT count(DISTINCT fund_code) FROM nav_history").fetchone()[0]
        rows = conn.execute("SELECT count(*) FROM nav_history").fetchone()[0]
    print(f"\n完成: 成功 {ok}, 失败 {fail}, 耗时 {time.time() - t0:.0f}s")
    print(f"nav_history: {total} 只基金 / {rows:,} 行")


if __name__ == "__main__":
    main()
