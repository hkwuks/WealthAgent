"""因子引擎端到端自检 —— 上线前必须通过。

检查项：
  1. load_all() 注册成功，Registry 非空
  2. 每个注册因子都能被实例化并 compute()
  3. 归一化值落在 0~1
  4. 暴露接口返回结构符合前端 FactorExposure 的契约

用法: python3 scripts/verify_factor_engine.py
"""
import asyncio
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

import numpy as np

from backend.core.factor import FactorRegistry
from backend.fund_quant.factors import load_all
from backend.fund_quant.factors.nav_feed import NavFeed
from backend.fund_quant.factors.normalize import _squash, op_of


def check_registry() -> int:
    n = load_all()
    metas = FactorRegistry.list(domain="fund")
    assert n > 0, "load_all 返回 0，注册失败"
    assert len(metas) == n, f"Registry 里 {len(metas)} 个，load_all 返回 {n}"
    print(f"✔ 注册 {n} 个因子，分类: "
          f"{ {c: sum(1 for m in metas if m.category == c) for c in set(m.category for m in metas)} }")
    return n


def check_compute() -> None:
    """每个因子在合成序列上应返回有限值。"""
    from datetime import date

    # 用带波动的序列，避免单调序列让某些算子退化
    rng = np.random.default_rng(42)
    steps = 1 + rng.normal(0, 0.01, 400)
    vals = list(300 * np.cumprod(steps))

    feed = NavFeed({"T": vals})
    ok, fail = 0, []
    for meta in FactorRegistry.list(domain="fund"):
        try:
            r = FactorRegistry.get(meta.name)().compute(
                ["T"], date.today(), meta.params.get("lookback", 60), feed)
            v = r.get("T")
            if v is None or not np.isfinite(v):
                fail.append((meta.name, "无值"))
                continue
            nv = _squash(v, op_of(meta.name))
            if not (0 <= nv <= 1):
                fail.append((meta.name, f"归一化越界 {nv}"))
                continue
            ok += 1
        except Exception as e:
            fail.append((meta.name, f"{type(e).__name__}: {e}"))

    print(f"✔ compute 通过 {ok} 个")
    if fail:
        for n, why in fail:
            print(f"  ✘ {n}: {why}")
        raise AssertionError(f"{len(fail)} 个因子计算失败")


def check_api() -> None:
    """暴露接口的结构必须匹配前端 FactorExposure.ts 的 FactorExposureData。"""
    from backend.api.fund_quant import fund_factor_exposure
    from backend.fund_quant.data.storage import get_nav_history, get_conn
    import json

    code = "510300"
    if not get_nav_history(code):
        f = PROJECT / "data" / "ohlcv" / f"{code}.json"
        if not f.exists():
            print("⚠ 无净值数据，跳过 API 检查")
            return
        rows = json.loads(f.read_text(encoding="utf-8"))
        with get_conn() as c:
            for r in rows[-500:]:
                c.execute("INSERT OR REPLACE INTO nav_history (fund_code,date,nav) "
                          "VALUES (?,?,?)", (code, r["date"], r["close"]))
            c.commit()
        print(f"  （已注入 {len(rows[-500:])} 条测试净值）")

    res = asyncio.run(fund_factor_exposure(code))
    assert res.get("success"), f"接口失败: {res}"
    d = res["data"]
    for k in ("fund_code", "fund_name", "factors", "total_score"):
        assert k in d, f"缺少字段 {k}"
    assert len(d["factors"]) > 0, "因子列表为空"

    for name, item in d["factors"].items():
        for k in ("value", "weight", "rank_pct"):
            assert k in item, f"{name} 缺少 {k}"
        assert 0 <= item["value"] <= 1, f"{name} value 越界"
        assert 0 <= item["rank_pct"] <= 100, f"{name} rank_pct 越界"

    ws = sum(v["weight"] for v in d["factors"].values())
    assert abs(ws - 1.0) < 0.01, f"权重和 {ws:.4f} != 1"
    print(f"✔ 暴露接口返回 {len(d['factors'])} 个因子，权重和 {ws:.4f}，"
          f"总分 {d['total_score']}")


def check_normalize() -> None:
    """归一化必须在典型值域内单调，不能把所有因子压成同一个数。"""
    # max_gap 值域 (-0.6, 0]：-0.6 -> 0（跌到底），0 -> 1（在最高点）
    cases = [("roc", 0.15, 0.75), ("roc", -0.15, 0.25), ("rsv", 0.8, 0.8),
             ("std", 0.03, 0.5), ("max_gap", -0.3, 0.5), ("max_gap", 0.0, 1.0)]
    for op, raw, expect in cases:
        got = round(_squash(raw, op), 4)
        assert abs(got - expect) < 0.02, f"{op}({raw}) = {got}, 期望约 {expect}"
    print(f"✔ 归一化映射正确（{len(cases)} 个用例）")


if __name__ == "__main__":
    import logging
    logging.disable(logging.INFO)
    print("=" * 60)
    print("因子引擎端到端自检")
    print("=" * 60)
    check_registry()
    check_normalize()
    check_compute()
    check_api()
    print("\n✅ 全部通过")
