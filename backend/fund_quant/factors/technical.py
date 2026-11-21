"""量价技术因子 — 参考 Qlib Alpha158 的「算子 × 窗口」设计。

Alpha158 的 158 个因子 = 9 个 K 线形态 + 4 个价格特征 + 29 种算子 × 5 个窗口。
本项目只做 ETF/基金，取其中可用的量价算子，用一张声明表生成因子类，
而不是为每个 (算子, 窗口) 组合手写一个类 —— 后者会写出 100+ 个几乎相同的文件。

元数据里的 direction 是「因子值越大，未来收益越大(+1)还是越小(-1)」，
这是 §1.3「先研究市场，再开发策略」的落点：方向由数据验证，不由直觉填写。
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _P

_root = str(_P(__file__).resolve().parents[3])
if _root not in _sys.path:
    _sys.path.insert(0, _root)

import numpy as np

from backend.core.factor.factor import Factor
from backend.core.factor.models import FactorMeta

WINDOWS = [5, 10, 20, 60]


def _arr(data, s: str, as_of, lookback: int) -> np.ndarray | None:
    """取单标的的净值序列。失败返回 None 而不是抛异常。"""
    try:
        navs = data.get_factor_input([s], as_of, lookback)
    except Exception:
        return None
    if not navs or len(navs) < 20:
        return None
    a = np.array([x for x in navs if isinstance(x, (int, float)) and x > 0], dtype=float)
    return a if len(a) >= 20 else None


# ── 算子定义：名称 -> (中文名, direction, 计算函数, 说明) ───────────────
# direction 语义: 该因子值越大，未来收益预期越高(+1) / 越低(-1)。
# 短期反转类为 -1（涨多了会跌），动量类为 +1（强者恒强），这是待验证的先验假设。

def _ret(arr, n):
    return arr[-1] / arr[-n - 1] - 1 if len(arr) > n else np.nan


def _ma_gap(arr, n):
    """价格相对均线的偏离。正=高于均线。"""
    if len(arr) <= n:
        return np.nan
    return arr[-1] / np.mean(arr[-n:]) - 1


def _std(arr, n):
    """波动率。"""
    if len(arr) <= n:
        return np.nan
    r = np.diff(arr[-n - 1:]) / arr[-n - 1:-1]
    return float(np.std(r))


def _max_gap(arr, n):
    """距区间最高点的回撤（负数）。"""
    if len(arr) < n:
        return np.nan
    w = arr[-n:]
    return arr[-1] / np.max(w) - 1


def _rsv(arr, n):
    """随机指标 RSV: 当前价在区间高低位中的位置，0~1。"""
    if len(arr) < n:
        return np.nan
    w = arr[-n:]
    lo, hi = np.min(w), np.max(w)
    return (arr[-1] - lo) / (hi - lo) if hi > lo else 0.5


def _rank(arr, n):
    """当前涨跌幅在过去 n 期涨跌幅中的分位。"""
    if len(arr) <= n:
        return np.nan
    r = np.diff(arr[-n - 1:]) / arr[-n - 1:-1]
    return float((r <= r[-1]).mean())


def _skew(arr, n):
    if len(arr) <= n:
        return np.nan
    r = np.diff(arr[-n - 1:]) / arr[-n - 1:-1]
    s = np.std(r)
    return float(np.mean(((r - np.mean(r)) / s) ** 3)) if s > 0 else 0.0


OPS = {
    "roc":    ("收益率",   +1, _ret,     "n 日累计收益率，动量"),
    "ma_gap": ("均线偏离", -1, _ma_gap,  "价格/均线-1，过高则回归"),
    "std":    ("波动率",   -1, _std,     "n 日收益率标准差，低波占优"),
    "max_gap":("距高点",   -1, _max_gap, "当前价/区间最高-1"),
    "rsv":    ("RSV",      +1, _rsv,     "区间位置 0~1，突破方向"),
    "rank":   ("涨幅分位", -1, _rank,    "当日涨跌在历史分位，高分=反转"),
    "skew":   ("收益偏度", -1, _skew,    "正偏（暴涨）后易回落"),
}

CATEGORY = "technical"


class _TechnicalFactor(Factor):
    """算子+窗口 生成的因子。子类只需覆盖 meta 与 _op/_n。"""
    _op = ""
    _n = 20

    def compute(self, symbols, as_of, lookback, data):
        fn = OPS[self._op][2]
        need = max(self._n + 5, self.meta.min_history_days, lookback)
        out = {}
        for s in symbols:
            arr = _arr(data, s, as_of, need)
            if arr is None:
                continue
            try:
                v = fn(arr, self._n)
            except Exception:
                continue
            if v is not None and np.isfinite(v):
                out[s] = float(v)
        return out


def build_factors() -> list[tuple[type[Factor], FactorMeta]]:
    """生成全部 (算子 × 窗口) 因子类。返回列表供 FactorRegistry 批量注册。"""
    out = []
    for op, (cn, direction, _fn, desc) in OPS.items():
        for n in WINDOWS:
            name = f"tech_{op}_{n}"
            meta = FactorMeta(
                name=name,
                display_name=f"{cn}{n}日",
                category=CATEGORY,
                domain="fund",
                description=f"{desc}（窗口 {n} 日）",
                direction=direction,
                params={"lookback": n, "op": op, "window": n},
                formula=f"{op}(nav, {n})",
                min_history_days=n + 5,
                reference="Qlib Alpha158 算子设计",
                fund_types=["equity", "index", "qdii"],
            )
            cls = type(
                f"Tech_{op}_{n}",
                (_TechnicalFactor,),
                {"meta": meta, "_op": op, "_n": n,
                 "__doc__": f"{cn}（{n}日）— {desc}"},
            )
            out.append((cls, meta))
    return out


def register_all():
    """把本模块所有因子注册进全局 FactorRegistry。幂等。"""
    from backend.core.factor.registry import FactorRegistry

    added = 0
    for cls, meta in build_factors():
        try:
            FactorRegistry.register(cls, meta)
            added += 1
        except ValueError:   # 已注册
            pass
    return added


if __name__ == "__main__":
    import sys as _sys
    from pathlib import Path as _P
    _sys.path.insert(0, str(_P(__file__).resolve().parents[3]))

    factors = build_factors()
    print(f"生成 {len(factors)} 个因子：{len(OPS)} 算子 × {len(WINDOWS)} 窗口\n")
    for cls, meta in factors[:12]:
        print(f"  {meta.name:18} {meta.display_name:10} direction={meta.direction:+d}  {meta.formula}")

    # 自检：合成数据验证算子方向
    class _FakeData:
        def get_factor_input(self, symbols, as_of, n):
            return list(np.linspace(1.0, 2.0, 200))

    fd = _FakeData()
    vals = {}
    for cls, meta in factors:
        if meta.params["window"] == 20:
            v = cls().compute(["X"], None, 200, fd)
            vals[meta.params["op"]] = round(v.get("X", float("nan")), 4)
    print("\n单调上涨序列下的因子值（200 日 +100%）：")
    for k, v in vals.items():
        print(f"  {k:10} {v:>8.4f}")
    assert vals["roc"] > 0, "上涨序列 roc 应为正"
    assert vals["ma_gap"] > 0, "上涨序列应高于均线"
    assert vals["max_gap"] == 0.0, "区间最高点即当前价，距高点应为 0"

    n = register_all()
    from backend.core.factor.registry import FactorRegistry
    print(f"\n注册 {n} 个，Registry 总数 {FactorRegistry.count()}")
    print("[technical_factors] ✅ 自检通过")
