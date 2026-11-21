"""多因子选基策略 — 对接因子分析引擎，动态IC权重"""
from datetime import date
from typing import Optional

from loguru import logger

from ..base import FundStrategyBase, StrategyRegistry
from ...core.enums import SignalType, Direction, FundType
from ...core.models import FundSignal, Portfolio, InformationSet
from ...factors.nav_feed import feed_from_storage

# ── verdict 等级顺序 ──
_VERDICT_ORDER = {"strong": 0, "usable": 1, "weak": 2, "noise": 3}


def _verdict_ge(v: str, min_v: str) -> bool:
    """判断因子等级 >= 最低要求"""
    return _VERDICT_ORDER.get(v, 3) <= _VERDICT_ORDER.get(min_v, 3)


class MultiFactorSelection(FundStrategyBase):
    """多因子选基策略: 基于因子分析引擎的动态多因子评分"""
    strategy_name = "multi_factor"
    strategy_type = "selection"
    description = "基于因子评价引擎(IC_IR加权)的动态多因子评分"
    default_params = {
        "lookback_years": 3,
        "min_history_years": 1,
        "top_n": 5,
        "corr_threshold": 0.7,
        "weight_method": "ic_weighted",  # ic_weighted/equal/significant_only
        "custom_weights": None,
        "min_factor_verdict": "usable",
    }
    param_ranges = {
        "lookback_years": {"min": 1, "max": 5},
        "top_n": {"min": 3, "max": 20},
        "min_factor_verdict": {"options": [{"label": "可用", "value": "usable"}, {"label": "强信号", "value": "strong"}]},
        "weight_method": {"options": [{"label": "IC加权", "value": "ic_weighted"}, {"label": "等权", "value": "equal"}]},
        "min_history_years": {"min": 0.5, "max": 3},
    }
    formula_description = "基于IC_IR加权动态权重的多因子评分选基策略"
    applicable_fund_types = ["stock", "hybrid", "bond", "index"]
    min_history_days = 365

    def on_evaluate(self, portfolio: Optional[Portfolio],
                    info_set: Optional[InformationSet]) -> list[FundSignal]:
        return []

    def screen(self, fund_type: str = "stock", top_n: int = 10,
               params: Optional[dict] = None) -> dict:
        """筛选基金 — 使用因子引擎"""
        from backend.core.factor import (
            FactorRegistry, EvaluationEngine, EvalConfig,
        )
        from ...data.storage import get_all_fund_codes, get_fund_meta, get_nav_history

        if params:
            self.params.update(params)

        top_n = self.params.get("top_n", top_n)
        candidates = get_all_fund_codes()
        if not candidates:
            return {"strategy": self.strategy_name, "fund_type": fund_type,
                    "top_n": top_n, "rankings": [], "total_candidates": 0}

        # 1. 获取因子评价结果
        active = self._load_active_factors(candidates)
        if not active:
            logger.warning("没有通过评价的可用因子，回退等权")
            return self._fallback_screen(fund_type, top_n)

        # 2. 动态权重
        weights = self.params.get("custom_weights")
        if weights is None:
            weights = self._compute_weights(active)

        # 3. 计算每只基金评分
        fund_scores = []
        for code in candidates:
            fund_meta = get_fund_meta(code)
            if fund_meta and fund_meta.get("fund_type") != fund_type and fund_type != "all":
                continue

            navs = get_nav_history(code)
            if len(navs) < 60:
                continue

            # 走引擎统一计算：以前这里调 _compute_factor_simple，
            # 那份实现只认 10 个硬编码因子名，28 个 tech_* 全部返回 0.0。
            total = 0.0
            factor_values = {}
            feed = feed_from_storage(code)
            if feed is None:
                continue
            for f, fmeta in active:
                try:
                    raw = f.compute([code], date.today(),
                                    fmeta.params.get("lookback", 60), feed)
                    val = raw.get(code)
                    if val is None:
                        continue
                    factor_values[fmeta.name] = val
                    w = weights.get(fmeta.name, 0)
                    total += w * val * fmeta.direction
                except Exception:
                    continue

            if factor_values:
                fund_scores.append({
                    "fund_code": code,
                    "total_score": total,
                    "factors": {k: round(v, 4) for k, v in factor_values.items()},
                    "meta": fund_meta,
                })

        if not fund_scores:
            return {"strategy": self.strategy_name, "fund_type": fund_type,
                    "top_n": top_n, "rankings": [], "total_candidates": 0}

        # 4. Z-score 标准化
        if len(fund_scores) > 1:
            scores = [fs["total_score"] for fs in fund_scores]
            mean = __import__('numpy').mean(scores)
            std = max(__import__('numpy').std(scores, ddof=1), 1e-8)
            for fs in fund_scores:
                fs["total_score"] = (fs["total_score"] - mean) / std

        # 5. 排序
        fund_scores.sort(key=lambda x: x["total_score"], reverse=True)

        rankings = []
        for i, fs in enumerate(fund_scores[:top_n]):
            rankings.append({
                "rank": i + 1,
                "fund_code": fs["fund_code"],
                "fund_name": fs["meta"]["fund_name"] if fs["meta"] else "",
                "total_score": round(fs["total_score"], 4),
                "factors": fs["factors"],
            })

        self._state["last_rankings"] = fund_scores[:top_n]

        return {
            "strategy": self.strategy_name,
            "fund_type": fund_type,
            "top_n": top_n,
            "total_candidates": len(fund_scores),
            "rankings": rankings,
        }

    def _load_active_factors(self, symbols: list[str]) -> list[tuple]:
        """取可用因子。

        以前这里跑一遍 EvaluationEngine，但喂的是 _DummyFeed ——
        get_forward_returns 对所有标的直接返回 0.01，算出的 IC 是噪声，
        verdict 也就没有意义。真正的因子有效性已经在离线研究报告里做过
        （reports/factor_rolling_ic.json，36 月滚动窗口），结论写进了
        FactorMeta.params["weight"]。直接用那个，不再在线伪造一遍。

        返回 [(factor_instance, meta)]。
        """
        from backend.core.factor import FactorRegistry
        from backend.fund_quant.factors import load_all

        load_all()
        return [(FactorRegistry.get(m.name)(), m)
                for m in FactorRegistry.list(domain="fund")
                if m.params.get("weight", 0) > 0]

    def _compute_weights(self, active_factors: list[tuple],
                         method: str | None = None) -> dict[str, float]:
        """权重 = 离线研究报告的 |recent_ic|（存在 meta.params["weight"]）。

        以前按 EvaluationEngine 的 ic_ir 分权，但那个 ic_ir 是拿
        _DummyFeed 恒定 0.01 的假前瞻收益算出来的，没有信息。
        """
        if not active_factors:
            return {}
        total = sum(meta.params.get("weight", 0.0) for _, meta in active_factors)
        if total <= 0:
            return {meta.name: 1.0 / len(active_factors) for _, meta in active_factors}
        return {meta.name: meta.params.get("weight", 0.0) / total
                for _, meta in active_factors}

    def _fallback_screen(self, fund_type: str, top_n: int) -> dict:
        """回退到默认评分（无因子引擎时）"""
        from ...data.storage import get_all_fund_codes, get_fund_meta
        fund_scores = []
        for code in get_all_fund_codes() or []:
            meta = get_fund_meta(code)
            if meta and meta.get("fund_type") != fund_type and fund_type != "all":
                continue
            fund_scores.append({
                "fund_code": code,
                "total_score": float(meta.get("scale", 0)) if meta else 0,
                "meta": meta,
            })
        fund_scores.sort(key=lambda x: x["total_score"], reverse=True)
        rankings = [{"rank": i + 1, "fund_code": fs["fund_code"],
                      "fund_name": fs["meta"]["fund_name"] if fs["meta"] else "",
                      "total_score": 0.0, "factors": {}}
                     for i, fs in enumerate(fund_scores[:top_n])]
        return {"strategy": self.strategy_name, "fund_type": fund_type,
                "top_n": top_n, "total_candidates": len(fund_scores),
                "rankings": rankings}

    def score(self, fund_type: str = "stock",
              params: Optional[dict] = None) -> dict:
        """基金评分"""
        if params:
            self.params.update(params)
        result = self.screen(fund_type=fund_type, top_n=1000)
        return {
            "strategy": self.strategy_name,
            "fund_type": fund_type,
            "scores": {r["fund_code"]: r["total_score"]
                       for r in result.get("rankings", [])},
        }


StrategyRegistry.register(MultiFactorSelection)
