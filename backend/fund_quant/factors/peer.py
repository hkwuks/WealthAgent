"""同类池 —— 让「同类百分位」有真实分母。

问题：单只基金算出来的因子值，只有放进同类型基金里比较才有意义。
支付宝的"同类排名"就是这个道理。

做法：
  1. 按 fund_type 取同类成员（由 build_peer_pool.py 预先入库净值）
  2. 对每个成员算同一组因子
  3. 横截面排序得到百分位

限制：池子成员少于 MIN_POOL 时返回 None —— 1 只基金的分位恒为 50/100，没有信息量。
"""
from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path

import numpy as np

MIN_POOL = 8          # 少于此数不做横截面比较
_TYPES_FILE = Path(__file__).resolve().parents[3] / "data" / "fund_types.json"


@lru_cache(maxsize=1)
def _type_map() -> dict[str, str]:
    if not _TYPES_FILE.exists():
        return {}
    return json.loads(_TYPES_FILE.read_text(encoding="utf-8"))


def fund_type_of(fund_code: str) -> str | None:
    """先查缓存的全市场类型表，再退回 funds.json。"""
    t = _type_map().get(fund_code)
    if t:
        return t
    funds_file = Path(__file__).resolve().parents[3] / "data" / "backend" / "funds.json"
    if not funds_file.exists():
        return None
    try:
        for f in json.loads(funds_file.read_text(encoding="utf-8")):
            if f.get("fund_code") == fund_code:
                return f.get("fund_type")
    except Exception:
        pass
    return None


@lru_cache(maxsize=64)
def peer_codes(fund_type: str | None) -> tuple[str, ...]:
    """同类成员（含自身），按代码排序保证可复现。"""
    if not fund_type:
        return ()
    from backend.fund_quant.data.storage import get_conn

    with get_conn() as conn:
        have = {r[0] for r in conn.execute("SELECT DISTINCT fund_code FROM nav_history")}
    return tuple(sorted(c for c, t in _type_map().items() if t == fund_type and c in have))


@lru_cache(maxsize=32)
def _feed_for(codes: tuple[str, ...]):
    from .nav_feed import feed_from_pool

    return feed_from_pool(list(codes))


def cross_section(fund_type: str | None, factor_names: tuple[str, ...],
                  as_of: date) -> dict[str, dict[str, float]]:
    """{factor_name: {code: raw_value}}，只含能算出值的成员。"""
    codes = peer_codes(fund_type)
    if len(codes) < MIN_POOL:
        return {}

    from backend.core.factor import FactorRegistry

    feed = _feed_for(codes)
    if not feed._nav:                      # noqa: SLF001 — 同包内直读，避免再造一个 getter
        return {}

    out: dict[str, dict[str, float]] = {}
    for name in factor_names:
        try:
            meta = FactorRegistry.get_meta(name)
            cls = FactorRegistry.get(name)
            raw = cls().compute(list(codes), as_of, meta.params.get("lookback", 60), feed)
        except Exception:
            continue
        if len(raw) >= MIN_POOL:
            out[name] = raw
    return out


def percentile(raw_map: dict[str, float], code: str) -> int | None:
    """同类型横截面百分位 0~100。越大 = 该因子值在同类中越高。"""
    v = raw_map.get(code)
    if v is None or len(raw_map) < MIN_POOL:
        return None
    arr = np.fromiter(raw_map.values(), dtype=float)
    pct = float((arr < v).mean()) * 100
    # 并列时分到中位，避免全部并列值被打成 0
    ties = int((arr == v).sum()) - 1
    return int(round(min(max(pct + ties * 0.5, 0), 100)))
