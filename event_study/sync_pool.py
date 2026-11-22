"""批量下载扩充后的 ETF 池日线。并入 market_db 的本地库。

用法: python3 sync_pool.py [--limit N]
"""
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from market_db import load_daily

OUT = HERE.parent / "data" / "etf_pool.json"


def main():
    pool = json.loads(OUT.read_text(encoding="utf-8"))
    limit = len(pool)
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    pool = pool[:limit]

    ok, thin, fail = [], [], []
    for i, p in enumerate(pool, 1):
        code = p["code"]
        df = load_daily(code, refresh=False)
        if df is None:
            df = load_daily(code, refresh=True)
        if df is None:
            fail.append((code, p["name"]))
        elif len(df) < 300:
            thin.append((code, p["name"], len(df)))
        else:
            ok.append((code, p["name"], len(df), str(df["date"].iloc[0].date())))
        if i % 20 == 0:
            print(f"  ... {i}/{len(pool)}  成功 {len(ok)} 薄数据 {len(thin)} 失败 {len(fail)}")
        time.sleep(0.2)

    print(f"\n成功 {len(ok)} / 薄 {len(thin)} / 失败 {len(fail)}  （共 {len(pool)}）")
    if fail:
        print("失败:", ", ".join(f"{c}({n[:10]})" for c, n in fail[:15]))
    if thin:
        print("薄数据:", ", ".join(f"{c}({n}条)" for c, n, _ in thin[:15]))

    # 只保留可用标的，回写
    usable = [{"code": c, "name": n} for c, n, *_ in ok]
    (HERE.parent / "data" / "etf_pool_usable.json").write_text(
        json.dumps(usable, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"可用标的 {len(usable)} 只 -> data/etf_pool_usable.json")


if __name__ == "__main__":
    main()
