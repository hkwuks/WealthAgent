"""
ML预测策略 — 包装GoldPricePredictor为StrategyBase子类

回测模式下，on_bar()累积K线到滑动窗口，每window_size根bar做一次预测：
- 回归模式: predicted_change > threshold → LONG, < -threshold → SHORT
- Triple-Barrier模式: direction=1 → LONG, direction=-1 → SHORT
- 持仓中: 方向反转或达到max_holding_bars → 平仓
"""

import numpy as np
import pandas as pd
from datetime import datetime
from typing import Optional

from backend.gold.strategy.base import StrategyBase, StrategyRegistry, StrategyContext
from backend.gold.core.models import GoldBarData, SignalDirection
from loguru import logger


@StrategyRegistry.register("ml_predictor")
class MLPredictorStrategy(StrategyBase):
    """ML预测策略 — 滑动窗口预测"""

    strategy_name = "ml_predictor"
    strategy_type = "ml_predictor"
    description = "LightGBM/XGBoost/Ridge滑动窗口预测"
    default_params = {
        "window_size": 60,           # 滑动窗口大小（累积多少bar后开始预测）
        "predict_interval": 5,       # 每N根bar预测一次
        "model_type": "lightgbm",    # lightgbm / xgboost / ridge
        "prediction_mode": "regression",  # regression / triple_barrier
        "change_threshold": 0.003,   # 回归模式：涨跌幅阈值（0.3%）
        "max_holding_bars": 20,      # 最大持仓bar数
        "atr_stop_multiplier": 2.0,  # ATR止损倍数
        "position_size": 1,
        "horizon_days": 1,           # 预测周期
    }
    param_ranges = {
        "window_size": [40, 60, 80, 100, 120],
        "predict_interval": [1, 3, 5, 10],
        "change_threshold": [0.001, 0.002, 0.003, 0.005, 0.01],
        "max_holding_bars": [5, 10, 20, 30],
        "atr_stop_multiplier": [1.5, 2.0, 2.5, 3.0],
    }

    def on_init(self, context: StrategyContext):
        self._bars: list[GoldBarData] = []
        self._position: int = 0
        self._entry_price: float = 0
        self._entry_bar: int = 0
        self._bar_count: int = 0
        self._predictor = None
        self._predictor_failed: bool = False  # 初始化失败标记，避免重复重试
        self._atr_value: float = 0
        self._last_predict_bar: int = -999  # 上次预测的bar序号

    def on_bar(self, bar: GoldBarData):
        self._bars.append(bar)
        self._bar_count += 1

        # 限制窗口大小
        max_keep = max(self.window_size + 100, 300)
        if len(self._bars) > max_keep:
            self._bars = self._bars[-max_keep:]

        # 计算ATR（止损用）
        self._calc_atr()

        # 累积不足窗口，跳过
        if len(self._bars) < self.window_size:
            return

        # 持仓管理：检查止损和最大持仓
        if self._position != 0:
            self._check_exit(bar)
            if self._position == 0:
                return  # 已平仓，本bar不再开仓

        # 按predict_interval间隔预测
        if self._bar_count - self._last_predict_bar < self.predict_interval:
            return

        # 无持仓时才预测开仓
        if self._position == 0:
            self._predict_and_signal(bar)

    def _predict_and_signal(self, bar: GoldBarData):
        """执行预测并发出信号"""
        try:
            predictor = self._get_predictor()
            if predictor is None:
                return

            df = self._bars_to_dataframe()
            if df.empty or len(df) < self.window_size:
                return

            price = bar.close
            dt = bar.datetime

            if self.prediction_mode == "triple_barrier":
                direction = self._predict_tb(predictor, df)
                if direction is None:
                    return

                if direction == 1:
                    sl = price - self._atr_value * self.atr_stop_multiplier
                    self.emit_signal(SignalDirection.LONG, bar.symbol, price,
                                     self.position_size, stop_loss=sl,
                                     confidence=0.6,
                                     reason=f"ML-TB看涨",
                                     bar_datetime=dt)
                    self._position = 1
                    self._entry_price = price
                    self._entry_bar = self._bar_count
                elif direction == -1:
                    sl = price + self._atr_value * self.atr_stop_multiplier
                    self.emit_signal(SignalDirection.SHORT, bar.symbol, price,
                                     self.position_size, stop_loss=sl,
                                     confidence=0.6,
                                     reason=f"ML-TB看跌",
                                     bar_datetime=dt)
                    self._position = -1
                    self._entry_price = price
                    self._entry_bar = self._bar_count
            else:
                # 回归模式
                change_pct = self._predict_regression(predictor, df)
                if change_pct is None:
                    return

                if change_pct > self.change_threshold:
                    sl = price - self._atr_value * self.atr_stop_multiplier
                    self.emit_signal(SignalDirection.LONG, bar.symbol, price,
                                     self.position_size, stop_loss=sl,
                                     confidence=min(0.9, abs(change_pct) / 0.01),
                                     reason=f"ML预测涨{change_pct*100:.2f}%",
                                     bar_datetime=dt)
                    self._position = 1
                    self._entry_price = price
                    self._entry_bar = self._bar_count
                elif change_pct < -self.change_threshold:
                    sl = price + self._atr_value * self.atr_stop_multiplier
                    self.emit_signal(SignalDirection.SHORT, bar.symbol, price,
                                     self.position_size, stop_loss=sl,
                                     confidence=min(0.9, abs(change_pct) / 0.01),
                                     reason=f"ML预测跌{change_pct*100:.2f}%",
                                     bar_datetime=dt)
                    self._position = -1
                    self._entry_price = price
                    self._entry_bar = self._bar_count

            self._last_predict_bar = self._bar_count

        except Exception as e:
            logger.debug(f"ML prediction failed: {e}")

    def _check_exit(self, bar: GoldBarData):
        """检查平仓条件"""
        price = bar.close
        dt = bar.datetime

        # ATR止损
        if self._position == 1:
            sl = self._entry_price - self._atr_value * self.atr_stop_multiplier
            if price < sl:
                self.emit_signal(SignalDirection.CLOSE_LONG, bar.symbol, price,
                                 self.position_size, reason="ATR止损", bar_datetime=dt)
                self._position = 0
                return
        elif self._position == -1:
            sl = self._entry_price + self._atr_value * self.atr_stop_multiplier
            if price > sl:
                self.emit_signal(SignalDirection.CLOSE_SHORT, bar.symbol, price,
                                 self.position_size, reason="ATR止损", bar_datetime=dt)
                self._position = 0
                return

        # 最大持仓bar数
        holding_bars = self._bar_count - self._entry_bar
        if holding_bars >= self.max_holding_bars:
            if self._position == 1:
                self.emit_signal(SignalDirection.CLOSE_LONG, bar.symbol, price,
                                 self.position_size, reason="最大持仓期", bar_datetime=dt)
            elif self._position == -1:
                self.emit_signal(SignalDirection.CLOSE_SHORT, bar.symbol, price,
                                 self.position_size, reason="最大持仓期", bar_datetime=dt)
            self._position = 0

    def _get_predictor(self):
        """获取或初始化预测器（懒加载，失败后不重试）"""
        if self._predictor is not None:
            return self._predictor
        if self._predictor_failed:
            return None

        try:
            from backend.gold_prediction import (
                GoldPricePredictor, ModelType, PredictionHorizon, model_manager,
            )

            model_map = {
                "lightgbm": ModelType.LIGHTGBM,
                "xgboost": ModelType.XGBOOST,
                "ridge": ModelType.RIDGE,
            }
            horizon_map = {1: PredictionHorizon.SHORT, 5: PredictionHorizon.MEDIUM, 20: PredictionHorizon.LONG}

            mt = model_map.get(self.model_type, ModelType.LIGHTGBM)
            horizon = horizon_map.get(self.horizon_days, PredictionHorizon.SHORT)

            # 尝试从缓存加载
            predictor = model_manager.get_predictor(mt, horizon)
            if predictor is not None:
                self._predictor = predictor
                return predictor

            # 无缓存 — 回测模式下用当前窗口数据训练
            # 注意：这有look-ahead bias，但V1先这样，V2做walk-forward
            df = self._bars_to_dataframe()
            if df.empty or len(df) < 100:
                return None

            predictor = GoldPricePredictor()
            if self.prediction_mode == "triple_barrier":
                predictor.train_tb(df, mt)
            else:
                predictor.train(df, mt, horizon)

            self._predictor = predictor
            return predictor

        except Exception as e:
            logger.warning(f"ML predictor init failed: {e}")
            self._predictor_failed = True
            return None

    def _predict_regression(self, predictor, df: pd.DataFrame) -> Optional[float]:
        """回归预测 → 返回预测涨跌幅"""
        try:
            from backend.gold_prediction import ModelType, PredictionHorizon

            mt = ModelType(self.model_type)
            horizon_map = {1: PredictionHorizon.SHORT, 5: PredictionHorizon.MEDIUM, 20: PredictionHorizon.LONG}
            horizon = horizon_map.get(self.horizon_days, PredictionHorizon.SHORT)

            result = predictor.predict(df, mt, horizon, use_last_known_price=True)
            return result.predicted_change_percent / 100  # 转为小数
        except Exception as e:
            logger.debug(f"Regression predict failed: {e}")
            return None

    def _predict_tb(self, predictor, df: pd.DataFrame) -> Optional[int]:
        """Triple-Barrier预测 → 返回方向 1/-1"""
        try:
            from backend.gold_prediction import ModelType

            mt = ModelType(self.model_type)
            result = predictor.predict_tb(df, mt)
            return result.direction
        except Exception as e:
            logger.debug(f"TB predict failed: {e}")
            return None

    def _bars_to_dataframe(self) -> pd.DataFrame:
        """将GoldBarData列表转为GoldPricePredictor所需的DataFrame"""
        if not self._bars:
            return pd.DataFrame()

        rows = []
        for b in self._bars:
            rows.append({
                "date": b.datetime.strftime("%Y-%m-%d"),
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "volume": b.volume,
            })

        df = pd.DataFrame(rows)
        # 添加宏观数据列（如果有的话，没有就填NaN，FeatureEngineer会处理）
        for col in ["DXY_value", "VIX_value", "US10Y_value", "TIPS_value", "BREAKEVEN_value"]:
            if col not in df.columns:
                df[col] = np.nan

        return df

    def _calc_atr(self):
        """计算ATR"""
        if len(self._bars) < 15:
            self._atr_value = 0
            return

        trs = []
        for i in range(1, len(self._bars)):
            bar, prev = self._bars[i], self._bars[i - 1]
            tr = max(bar.high - bar.low,
                     abs(bar.high - prev.close),
                     abs(bar.low - prev.close))
            trs.append(tr)
        self._atr_value = sum(trs[-14:]) / 14
