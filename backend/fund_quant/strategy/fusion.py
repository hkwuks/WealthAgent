"""信号融合机制"""

from typing import List, Optional
from ..core.enums import Direction
from ..core.models import FundSignal, FusionSignal


class SignalFusion:
    """三类策略信号加权融合"""

    DEFAULT_WEIGHTS = {
        "timing": 0.5,
        "selection": 0.2,
        "allocation": 0.3,
    }
    CONFLICT_ALLOCATION_BOOST = 1.5
    TIMING_OVERRIDE_CONFIDENCE = 0.9

    def fuse(self, signals: List[FundSignal]) -> Optional[FusionSignal]:
        """融合同一基金的所有信号"""
        if not signals:
            return None

        target_fund = signals[0].fund_code
        fund_signals = [s for s in signals if s.fund_code == target_fund]
        if not fund_signals:
            return None

        # 按策略类型分组
        grouped = {}
        for s in fund_signals:
            key = s.signal_type.value if hasattr(s.signal_type, 'value') else str(s.signal_type)
            grouped.setdefault(key, []).append(s)

        # 计算加权综合得分
        total_weight = 0.0
        weighted_score = 0.0
        weight_sum_confidence = 0.0
        contributors = []

        for s_type, type_signals in grouped.items():
            weight = self.DEFAULT_WEIGHTS.get(s_type, 0.2)
            for sig in type_signals:
                if sig.direction == Direction.HOLD:
                    continue
                dir_score = 1.0 if sig.direction in (Direction.BUY, Direction.REBALANCE) else -1.0
                weighted_score += weight * dir_score * sig.confidence
                weight_sum_confidence += weight * sig.confidence
                contributors.append({
                    "strategy": sig.strategy_name,
                    "type": s_type,
                    "direction": sig.direction.value,
                    "confidence": sig.confidence,
                    "reason": sig.reason,
                })

        if weight_sum_confidence <= 0:
            return FusionSignal(
                fund_code=target_fund,
                fund_name=fund_signals[0].fund_name,
                direction=Direction.HOLD,
                confidence=0.0,
                reason="无有效信号",
            )

        composite_score = weighted_score / weight_sum_confidence
        # 置信度计算
        confidence = min(abs(weighted_score) / weight_sum_confidence, 1.0)

        # 方向判定
        if composite_score > 0:
            direction = Direction.BUY
        elif composite_score < 0:
            direction = Direction.SELL
        else:
            direction = Direction.HOLD

        # 冲突检测
        directions = set()
        for s in fund_signals:
            if s.direction != Direction.HOLD:
                directions.add(s.direction)
        has_conflict = len(directions) > 1

        override_reason = None
        if has_conflict:
            # 择时高置信度覆盖
            timing_sigs = grouped.get("timing", [])
            for ts in timing_sigs:
                if ts.confidence >= self.TIMING_OVERRIDE_CONFIDENCE and ts.direction != direction:
                    direction = ts.direction
                    override_reason = f"择时信号置信度 {ts.confidence:.2f} >= 0.9，覆盖融合方向"
                    break

        import uuid
        signal_id = f"fusion_{uuid.uuid4().hex[:8]}"

        return FusionSignal(
            fund_code=target_fund,
            fund_name=fund_signals[0].fund_name,
            direction=direction,
            confidence=confidence,
            reason=f"融合 {len(fund_signals)} 个信号" if not override_reason else override_reason,
            contributing_strategies=contributors,
            conflict=has_conflict,
            override_reason=override_reason,
        )


signal_fusion = SignalFusion()
