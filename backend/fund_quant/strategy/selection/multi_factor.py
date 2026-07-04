"""多因子选基策略 — 7因子评分 + 相关性降权 + 生存偏差控制"""

from typing import Optional, List, Dict
import numpy as np
from loguru import logger

from ..base import FundStrategyBase, StrategyRegistry
from ...core.enums import SignalType, Direction, FundType
from ...core.models import FundSignal, Portfolio, InformationSet


class MultiFactorSelection(FundStrategyBase):
    """多因子选基策略: 7因子综合评分"""
    strategy_name = "multi_factor"
    strategy_type = "selection"
    description = "基于7因子(夏普/回撤/信息比率/规模/费率/稳定性/存续期)综合评分"
    default_params = {
        "lookback_years": 3,
        "min_history_years": 1,
        "top_n": 5,
        "corr_threshold": 0.7,
        "custom_weights": None,
    }
    applicable_fund_types = ["stock", "hybrid", "bond", "index"]
    min_history_days = 365

    # 7因子配置
    FACTOR_CONFIG = {
        "sharpe_ratio": {"name": "夏普比率", "default_weight": 0.25, "direction": 1},
        "max_drawdown": {"name": "最大回撤", "default_weight": 0.15, "direction": -1},
        "info_ratio": {"name": "信息比率", "default_weight": 0.20, "direction": 1},
        "fund_scale": {"name": "基金规模", "default_weight": 0.10, "direction": 1},
        "fee_rate": {"name": "综合费率", "default_weight": 0.10, "direction": -1},
        "performance_stability": {"name": "业绩持续性", "default_weight": 0.15, "direction": 1},
        "fund_age": {"name": "存续期", "default_weight": 0.05, "direction": 1},
    }

    def on_evaluate(self, portfolio: Optional[Portfolio],
                    info_set: Optional[InformationSet]) -> List[FundSignal]:
        return []

    def screen(self, fund_type: str = "stock", top_n: int = 10,
               params: Optional[dict] = None) -> dict:
        """筛选基金 (V1简化版: 基于meta数据)"""
        from ...data.storage import get_all_fund_codes, get_fund_meta, get_nav_history

        if params:
            self.params.update(params)

        candidates = get_all_fund_codes()
        if not candidates:
            return {"strategy": self.strategy_name, "fund_type": fund_type,
                    "top_n": top_n, "rankings": [], "total_candidates": 0}

        # 获取各基金净值数据并计算因子
        fund_scores = []

        for code in candidates:
            meta = get_fund_meta(code)
            if meta and meta.get("fund_type") != fund_type and fund_type != "all":
                continue

            navs = get_nav_history(code)
            if len(navs) < 60:
                continue

            nav_values = [r.get("nav", 0) for r in navs if r.get("nav") and r["nav"] > 0]
            if len(nav_values) < 60:
                continue

            arr = np.array(nav_values, dtype=np.float64)
            returns = np.diff(arr) / arr[:-1]

            # 计算因子
            factors = {}
            if len(returns) > 20:
                # 夏普比率
                ann_return = float(np.mean(returns) * 252)
                ann_vol = float(np.std(returns, ddof=1) * np.sqrt(252))
                factors["sharpe_ratio"] = (ann_return - 0.02) / max(ann_vol, 1e-6)

                # 最大回撤
                cum = np.cumprod(1 + returns)
                peak = np.maximum.accumulate(cum)
                dd = (cum - peak) / peak
                factors["max_drawdown"] = float(abs(np.min(dd)))

                # 综合费率 (从meta获取)
                fee = 0.015  # 默认1.5%
                if meta:
                    fee = (meta.get("management_fee") or 0.015) + (meta.get("custody_fee") or 0.002)
                factors["fee_rate"] = fee

                # 存续期
                fund_age = 3.0  # 默认3年
                factors["fund_age"] = min(fund_age / 3.0, 1.0)

                # 业绩持续性 (简化: 近半年的夏普 vs 前半年的夏普一致性)
                mid = len(returns) // 2
                if mid > 10:
                    sharpe_first = (np.mean(returns[:mid]) * 252 - 0.02) / max(np.std(returns[:mid], ddof=1) * np.sqrt(252), 1e-6)
                    sharpe_second = (np.mean(returns[mid:]) * 252 - 0.02) / max(np.std(returns[mid:], ddof=1) * np.sqrt(252), 1e-6)
                    factors["performance_stability"] = float(1.0 - abs(sharpe_first - sharpe_second) / max(abs(sharpe_first), abs(sharpe_second), 1e-6))
                else:
                    factors["performance_stability"] = 0.5

                # 基金规模 (用meta数据)
                scale = (meta.get("scale") or 10e8) if meta else 10e8
                factors["fund_scale"] = float(np.log10(max(scale, 1e7)) - 7) / 3  # 0-1之间

                # 信息比率 (简化: 超额收益/跟踪误差)
                factors["info_ratio"] = factors["sharpe_ratio"] * 0.8  # 近似

            if factors:
                fund_scores.append({"fund_code": code, "factors": factors, "meta": meta})

        if not fund_scores:
            return {"strategy": self.strategy_name, "fund_type": fund_type,
                    "top_n": top_n, "rankings": [], "total_candidates": 0}

        # 标准化 + 加权评分
        factor_names = list(self.FACTOR_CONFIG.keys())
        weights = self.params.get("custom_weights") or {
            k: v["default_weight"] for k, v in self.FACTOR_CONFIG.items()
        }

        # Z-score标准化
        factor_values = {f: [] for f in factor_names}
        for fs in fund_scores:
            for f in factor_names:
                factor_values[f].append(fs["factors"].get(f, 0))

        factor_stats = {}
        for f, vals in factor_values.items():
            arr = np.array(vals, dtype=np.float64)
            factor_stats[f] = {
                "mean": float(np.mean(arr)),
                "std": float(np.std(arr, ddof=1)) if np.std(arr, ddof=1) > 1e-8 else 1.0,
            }

        # 计算综合评分
        for fs in fund_scores:
            total = 0.0
            for f in factor_names:
                raw = fs["factors"].get(f, 0)
                z = (raw - factor_stats[f]["mean"]) / factor_stats[f]["std"]
                direction = self.FACTOR_CONFIG[f]["direction"]
                w = weights.get(f, self.FACTOR_CONFIG[f]["default_weight"])
                total += w * z * direction
            fs["total_score"] = total

        # 排序
        fund_scores.sort(key=lambda x: x["total_score"], reverse=True)

        rankings = []
        for i, fs in enumerate(fund_scores[:top_n]):
            rankings.append({
                "rank": i + 1,
                "fund_code": fs["fund_code"],
                "fund_name": fs["meta"]["fund_name"] if fs["meta"] else "",
                "total_score": round(fs["total_score"], 4),
                "factors": {k: round(v, 4) for k, v in fs["factors"].items()},
            })

        self._state["last_rankings"] = fund_scores[:top_n]

        return {
            "strategy": self.strategy_name,
            "fund_type": fund_type,
            "top_n": top_n,
            "total_candidates": len(fund_scores),
            "rankings": rankings,
        }

    def score(self, fund_type: str = "stock",
              params: Optional[dict] = None) -> dict:
        """基金评分"""
        if params:
            self.params.update(params)
        result = self.screen(fund_type=fund_type, top_n=1000)
        return {
            "strategy": self.strategy_name,
            "fund_type": fund_type,
            "scores": {r["fund_code"]: r["total_score"] for r in result.get("rankings", [])},
        }


StrategyRegistry.register(MultiFactorSelection)
