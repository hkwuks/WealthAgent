"""NavFeed —— 把基金的净值历史适配成 Factor 引擎需要的 DataFeed。

现有引擎（backend/core/factor/）定义了 `data.get_factor_input(symbols, as_of, lookback)`
这个约定，但没有为 fund 域实现过。本类补齐这一环，让所有注册因子可被真实计算。

与 api/fund_quant.py 里那段硬编码 if-elif 的区别：
  硬编码版从不调用 Factor.compute()，新增因子全部 fallback 到 0.5；
  本适配器让引擎按 meta.params 真实计算。
"""
from __future__ import annotations

from datetime import date


class NavFeed:
    """基金净值数据源。

    get_factor_input 的返回约定（见 technical.py 的 _arr）：
        单标的 -> 净值序列 list[float]
        多标的 -> {symbol: list[float]}
    """

    def __init__(self, nav_map: dict[str, list[float]], as_of: date | None = None):
        self._nav = nav_map
        self._as_of = as_of

    def get_factor_input(self, symbols: list[str], as_of: date, lookback: int):
        if len(symbols) == 1:
            return self._nav.get(symbols[0], [])
        return {s: self._nav.get(s, []) for s in symbols}

    def get_forward_returns(self, symbols, from_date, to_date):
        """事件研究用的前瞻收益。当前实现只覆盖因子暴露，故返回空。"""
        return {}


def feed_from_storage(fund_code: str, min_points: int = 40) -> NavFeed | None:
    """从 SQLite 读出净值序列，构造 feed。"""
    from backend.fund_quant.data.storage import get_nav_history

    rows = get_nav_history(fund_code)
    if not rows:
        return None
    vals = []
    for r in rows:
        v = r.get("adj_nav") or r.get("nav")
        if v:
            try:
                vals.append(float(v))
            except (TypeError, ValueError):
                continue
    if len(vals) < min_points:
        return None
    return NavFeed({fund_code: vals})
