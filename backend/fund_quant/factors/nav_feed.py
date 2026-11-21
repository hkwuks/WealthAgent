"""NavFeed —— 把基金的净值历史适配成 Factor 引擎需要的 DataFeed。

现有引擎（backend/core/factor/）定义了 `data.get_factor_input(symbols, as_of, lookback)`
这个约定，但没有为 fund 域实现过。本类补齐这一环，让所有注册因子可被真实计算。

与 api/fund_quant.py 里那段硬编码 if-elif 的区别：
  硬编码版从不调用 Factor.compute()，新增因子全部 fallback 到 0.5；
  本适配器让引擎按 meta.params 真实计算。

as_of 语义（重要）：
  必须按 as_of 截断序列，否则任何"回看历史某一天"的调用都会拿到最新一段，
  画出来的历史因子值就是前视偏差。带日期的构造走 DatedNavFeed 分支。
"""
from __future__ import annotations

import bisect
from datetime import date


class NavFeed:
    """基金净值数据源（只有值，无日期轴）。

    get_factor_input 的返回约定（见 technical.py 的 _arr）：
        单标的 -> 净值序列 list[float]
        多标的 -> {symbol: list[float]}
    """

    def __init__(self, nav_map: dict[str, list[float]],
                 dates: dict[str, list[str]] | None = None):
        self._nav = nav_map
        self._dates = dates or {}

    def _slice(self, symbol: str, as_of, lookback: int) -> list[float]:
        vals = self._nav.get(symbol, [])
        ds = self._dates.get(symbol)
        if not ds or len(ds) != len(vals):
            # 无日期轴时无法按 as_of 截断，返回全部（调用方需自知此时 as_of 无效）
            return vals
        i = bisect.bisect_right(ds, str(as_of))
        return vals[max(0, i - lookback):i]

    def get_factor_input(self, symbols: list[str], as_of: date, lookback: int):
        if len(symbols) == 1:
            return self._slice(symbols[0], as_of, lookback)
        return {s: self._slice(s, as_of, lookback) for s in symbols}

    def get_forward_returns(self, symbols, from_date, to_date):
        """事件研究用的前瞻收益。当前实现只覆盖因子暴露，故返回空。"""
        return {}


def feed_from_storage(fund_code: str, min_points: int = 40) -> NavFeed | None:
    """从 SQLite 读出净值序列，构造带日期轴的 feed。"""
    from backend.fund_quant.data.storage import get_nav_history

    rows = get_nav_history(fund_code)
    if not rows:
        return None
    vals, dates = [], []
    for r in rows:
        v = r.get("adj_nav") or r.get("nav")
        if v:
            try:
                vals.append(float(v))
            except (TypeError, ValueError):
                continue
            dates.append(str(r.get("date", "")))
    if len(vals) < min_points:
        return None
    return NavFeed({fund_code: vals}, {fund_code: dates})


def feed_from_pool(codes: list[str], min_points: int = 40) -> NavFeed:
    """批量构造：一次 SQL 取多只基金，用于同类池的横截面分位。"""
    from backend.fund_quant.data.storage import get_nav_history

    nav_map, date_map = {}, {}
    for code in codes:
        rows = get_nav_history(code)
        if not rows:
            continue
        vals, ds = [], []
        for r in rows:
            v = r.get("adj_nav") or r.get("nav")
            if v:
                try:
                    vals.append(float(v))
                except (TypeError, ValueError):
                    continue
                ds.append(str(r.get("date", "")))
        if len(vals) >= min_points:
            nav_map[code] = vals
            date_map[code] = ds
    return NavFeed(nav_map, date_map)
