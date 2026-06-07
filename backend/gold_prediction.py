"""
黄金价格预测模块

提供多模型黄金价格预测能力：
1. LightGBM - 主力模型（样本效率高、可解释）
2. XGBoost - 备选模型
3. Ridge - 线性基准线（必须首先建立，打不过就别用复杂模型）
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum
import pickle
import os
import json
import threading

from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

from loguru import logger

logger.add("./logs/gold_prediction.log", encoding="utf-8", rotation="10 MB")


class ModelType(Enum):
    """模型类型"""
    LIGHTGBM = "lightgbm"
    XGBOOST = "xgboost"
    RIDGE = "ridge"


class PredictionHorizon(Enum):
    """预测周期"""
    SHORT = 1      # 1天
    MEDIUM = 5     # 1周
    LONG = 20      # 1月


@dataclass
class PredictionResult:
    """预测结果"""
    asset_code: str
    current_price: float
    predicted_price: float
    predicted_change: float
    predicted_change_percent: float
    confidence: float
    horizon: int
    model_type: str
    features_used: List[str]
    timestamp: datetime
    metadata: Dict[str, Any]


@dataclass
class TripleBarrierResult:
    """Triple-Barrier 标注结果"""
    asset_code: str
    current_price: float
    direction: int              # 1=看涨, -1=看跌, 0=中性
    direction_probability: float  # 方向概率 [0, 1]
    tp_level: float             # 止盈价格
    sl_level: float             # 止损价格
    max_holding_days: int       # 最大持有期
    atr_value: float            # 当前ATR值
    confidence: float
    model_type: str
    features_used: List[str]
    timestamp: datetime
    metadata: Dict[str, Any]


class FeatureEngineer:
    """特征工程"""

    def __init__(self):
        self.scaler = StandardScaler()
        self.selected_features_: Optional[List[str]] = None  # 因子筛选后保留的特征

    def create_technical_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """创建技术指标特征（精选，避免冗余）"""
        df = df.copy()

        # 收益率
        df['returns'] = df['close'].pct_change()
        df['log_returns'] = np.log(df['close'] / df['close'].shift(1))

        # MA比率（不保留MA值本身，避免冗余）
        for window in [20, 60]:
            ma = df['close'].rolling(window=window).mean()
            df[f'ma_ratio_{window}'] = df['close'] / ma

        # ATR(20)替代多个volatility窗口
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift(1)).abs()
        low_close = (df['low'] - df['close'].shift(1)).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr_20'] = tr.rolling(window=20).mean()
        df['atr_ratio'] = df['atr_20'] / df['close']

        # RSI(14) — 仅保留一个周期
        df['rsi_14'] = self._calculate_rsi(df['close'], 14)

        # MACD(12,26,9) — 不再单独保留hist
        df['macd'], df['macd_signal'], _ = self._calculate_macd(df['close'])
        df['macd_diff'] = df['macd'] - df['macd_signal']

        # 布林带位置（不保留upper/middle/lower）
        _, _, bb_lower = self._calculate_bollinger(df['close'])
        bb_upper, bb_middle, _ = self._calculate_bollinger(df['close'])
        df['bb_position'] = (df['close'] - bb_lower) / (bb_upper - bb_lower + 1e-10)

        # 价格位置
        df['close_position'] = (df['close'] - df['low']) / (df['high'] - df['low'] + 1e-10)

        return df

    def create_macro_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """创建宏观特征（含TIPS和Breakeven）"""
        df = df.copy()

        # 美元指数
        if 'DXY_value' in df.columns:
            df['DXY_change'] = df['DXY_value'].pct_change()
            df['DXY_ma_5'] = df['DXY_value'].rolling(5).mean()
            df['gold_dxy_ratio'] = df['close'] / df['DXY_value']

        # VIX
        if 'VIX_value' in df.columns:
            df['VIX_change'] = df['VIX_value'].pct_change()
            df['VIX_ma_5'] = df['VIX_value'].rolling(5).mean()

        # 10Y国债收益率
        if 'US10Y_value' in df.columns:
            df['US10Y_change'] = df['US10Y_value'].pct_change()

        # 实际利率（TIPS）— 黄金最重要驱动因子
        if 'TIPS_value' in df.columns:
            df['TIPS_change'] = df['TIPS_value'].pct_change()
            df['TIPS_level'] = df['TIPS_value']
            # 如果同时有10Y收益率，计算实际利率变化率
            if 'US10Y_value' in df.columns:
                df['real_rate_proxy'] = df['US10Y_value'] - df['TIPS_value']

        # 通胀预期（Breakeven）— 正相关
        if 'BREAKEVEN_value' in df.columns:
            df['BREAKEVEN_change'] = df['BREAKEVEN_value'].pct_change()
            df['BREAKEVEN_level'] = df['BREAKEVEN_value']
        elif 'US10Y_value' in df.columns and 'TIPS_value' in df.columns:
            # 手动计算Breakeven = 10Y名义 - TIPS实际
            df['BREAKEVEN_level'] = df['US10Y_value'] - df['TIPS_value']
            df['BREAKEVEN_change'] = df['BREAKEVEN_level'].pct_change()

        return df

    def create_lag_features(self, df: pd.DataFrame, lags: List[int] = None) -> pd.DataFrame:
        """创建滞后特征（精简版，减少维度）"""
        if lags is None:
            lags = [1, 2, 5]

        df = df.copy()
        # 仅对returns做滞后，不对close做（close滞后=returns本身）
        for lag in lags:
            if 'returns' in df.columns:
                df[f'returns_lag_{lag}'] = df['returns'].shift(lag)

        return df

    def prepare_features(self, df: pd.DataFrame, target_horizon: int = 1) -> Tuple[pd.DataFrame, pd.Series]:
        """
        准备特征和标签（用于训练）

        Args:
            df: 原始数据
            target_horizon: 预测周期（天数）

        Returns:
            (特征DataFrame, 标签Series)
        """
        df = self.create_technical_features(df)
        df = self.create_macro_features(df)
        df = self.create_lag_features(df)

        # 目标变量：未来收益率
        df['target'] = df['close'].shift(-target_horizon) / df['close'] - 1

        # 选择特征列
        feature_cols = [c for c in df.columns if c not in [
            'target', 'date', 'open', 'high', 'low', 'close', 'volume',
            'asset_code', 'asset_type', 'source', 'amount', 'change',
            'ma_5', 'ma_10', 'ma_20', 'ma_60',  # 保留ratio，去掉绝对值
            'volatility_5', 'volatility_20',  # 用ATR替代
            'macd_hist',  # 用macd_diff替代
            'bb_upper', 'bb_middle', 'bb_lower',  # 用bb_position替代
            'high_low_range',  # 用ATR替代
        ]]

        df_clean = df[feature_cols + ['target']].dropna()
        X = df_clean[feature_cols]
        y = df_clean['target']

        return X, y

    def prepare_features_for_prediction(self, df: pd.DataFrame) -> pd.DataFrame:
        """准备特征用于预测（不包含未来信息，使用筛选后的特征）"""
        df = self.create_technical_features(df)
        df = self.create_macro_features(df)
        df = self.create_lag_features(df)

        feature_cols = [c for c in df.columns if c not in [
            'target', 'date', 'open', 'high', 'low', 'close', 'volume',
            'asset_code', 'asset_type', 'source', 'amount', 'change',
            'ma_5', 'ma_10', 'ma_20', 'ma_60',
            'volatility_5', 'volatility_20',
            'macd_hist',
            'bb_upper', 'bb_middle', 'bb_lower',
            'high_low_range',
        ]]

        X = df[feature_cols].dropna()

        # 如果已经做过因子筛选，只用选中的特征
        if self.selected_features_ is not None:
            available = [f for f in self.selected_features_ if f in X.columns]
            if available:
                X = X[available]

        return X

    def select_features(self, X: pd.DataFrame, y: pd.Series,
                        mi_threshold: float = 0.01,
                        corr_threshold: float = 0.8,
                        shap_model=None) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        因子筛选：互信息 + 相关性去冗余 + SHAP验证

        Args:
            X: 特征DataFrame
            y: 目标变量Series
            mi_threshold: 互信息最低阈值，低于此值的因子被剔除
            corr_threshold: 因子间相关性阈值，>此值时保留MI更高的那个
            shap_model: 已训练的树模型（用于SHAP值计算），None则跳过SHAP

        Returns:
            (筛选后的特征DataFrame, 筛选报告dict)
        """
        report = {
            'original_features': list(X.columns),
            'original_count': len(X.columns),
            'steps': {}
        }

        # Step 1: 互信息筛选
        mi_scores = self._compute_mi_scores(X, y)
        mi_selected = [col for col, score in mi_scores.items() if score >= mi_threshold]
        report['steps']['mi_filter'] = {
            'threshold': mi_threshold,
            'removed': [col for col in X.columns if col not in mi_selected],
            'removed_count': len(X.columns) - len(mi_selected),
            'scores': {k: round(v, 4) for k, v in sorted(mi_scores.items(), key=lambda x: -x[1])}
        }

        X_mi = X[mi_selected]

        # Step 2: 相关性去冗余
        X_corr, corr_removed = self._remove_correlated_features(X_mi, mi_scores, corr_threshold)
        report['steps']['correlation_filter'] = {
            'threshold': corr_threshold,
            'removed': corr_removed,
            'removed_count': len(corr_removed)
        }

        # Step 3: SHAP验证（如果提供了树模型）
        if shap_model is not None:
            shap_importance = self._compute_shap_importance(shap_model, X_corr)
            mean_shap = np.mean(list(shap_importance.values()))
            shap_selected = [col for col, imp in shap_importance.items() if imp >= mean_shap]
            shap_removed = [col for col in X_corr.columns if col not in shap_selected]
            report['steps']['shap_filter'] = {
                'mean_importance': round(mean_shap, 6),
                'removed': shap_removed,
                'removed_count': len(shap_removed),
                'importance': {k: round(v, 6) for k, v in sorted(shap_importance.items(), key=lambda x: -x[1])}
            }
            X_final = X_corr[shap_selected]
        else:
            X_final = X_corr
            report['steps']['shap_filter'] = {'skipped': True, 'reason': 'no model provided'}

        self.selected_features_ = list(X_final.columns)
        report['selected_features'] = self.selected_features_
        report['selected_count'] = len(self.selected_features_)
        report['reduction_pct'] = round((1 - len(self.selected_features_) / max(len(X.columns), 1)) * 100, 1)

        logger.info(f"Factor screening: {len(X.columns)} -> {len(self.selected_features_)} features "
                     f"({report['reduction_pct']}% reduction)")

        return X_final, report

    def _compute_mi_scores(self, X: pd.DataFrame, y: pd.Series) -> Dict[str, float]:
        """计算各特征与目标变量的互信息"""
        from sklearn.feature_selection import mutual_info_regression

        X_clean = X.fillna(0)
        mi = mutual_info_regression(X_clean, y, random_state=42, n_neighbors=5)
        return dict(zip(X.columns, mi))

    def _remove_correlated_features(self, X: pd.DataFrame,
                                     mi_scores: Dict[str, float],
                                     threshold: float = 0.8) -> Tuple[pd.DataFrame, List[str]]:
        """去除高相关冗余特征，保留MI更高的"""
        corr_matrix = X.corr().abs()
        upper = corr_matrix.where(np.triu(np.ones(corr_matrix.shape), k=1).astype(bool))

        removed = []
        for col in upper.columns:
            correlated = upper.index[upper[col] > threshold].tolist()
            for corr_col in correlated:
                # 保留MI更高的那个
                if mi_scores.get(col, 0) >= mi_scores.get(corr_col, 0):
                    if corr_col not in removed:
                        removed.append(corr_col)
                else:
                    if col not in removed:
                        removed.append(col)

        X_filtered = X.drop(columns=removed, errors='ignore')
        return X_filtered, removed

    @staticmethod
    def _compute_shap_importance(model, X: pd.DataFrame) -> Dict[str, float]:
        """计算SHAP特征重要性"""
        try:
            import shap
            explainer = shap.TreeExplainer(model)
            shap_values = explainer.shap_values(X.iloc[:200])  # 采样200条加速
            mean_abs_shap = np.abs(shap_values).mean(axis=0)
            return dict(zip(X.columns, mean_abs_shap))
        except ImportError:
            logger.warning("shap not installed, skipping SHAP importance")
            # fallback: 用树模型的feature_importances_
            if hasattr(model, 'feature_importances_'):
                return dict(zip(X.columns, model.feature_importances_))
            return {col: 1.0 / len(X.columns) for col in X.columns}
        except Exception as e:
            logger.warning(f"SHAP computation failed: {e}, using feature_importances_")
            if hasattr(model, 'feature_importances_'):
                return dict(zip(X.columns, model.feature_importances_))
            return {col: 1.0 / len(X.columns) for col in X.columns}

    @staticmethod
    def _calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
        """计算RSI"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    @staticmethod
    def _calculate_macd(prices: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """计算MACD"""
        ema_fast = prices.ewm(span=fast).mean()
        ema_slow = prices.ewm(span=slow).mean()
        macd = ema_fast - ema_slow
        macd_signal = macd.ewm(span=signal).mean()
        macd_hist = macd - macd_signal
        return macd, macd_signal, macd_hist

    @staticmethod
    def _calculate_bollinger(prices: pd.Series, window: int = 20, num_std: int = 2) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """计算布林带"""
        middle = prices.rolling(window=window).mean()
        std = prices.rolling(window=window).std()
        upper = middle + num_std * std
        lower = middle - num_std * std
        return upper, middle, lower


class TripleBarrierLabeler:
    """
    Triple-Barrier Labeling

    基于 López de Prado 的方法，为每条数据设置三个屏障：
    1. 止盈屏障 (Take Profit): 当前价 + ATR(20) * tp_multiplier
    2. 止损屏障 (Stop Loss): 当前价 - ATR(20) * sl_multiplier
    3. 时间屏障 (Max Holding): max_holding_days 天后平仓

    先触碰哪个屏障决定了标签：
    - 触碰止盈 → 标签=1（看涨）
    - 触碰止损 → 标签=-1（看跌）
    - 时间到期 → 标签=sign(到期收益率)
    """

    def __init__(
        self,
        atr_window: int = 20,
        tp_multiplier: float = 1.5,
        sl_multiplier: float = 1.0,
        max_holding_days: int = 5,
    ):
        """
        Args:
            atr_window: ATR计算窗口
            tp_multiplier: 止盈 = ATR * tp_multiplier（1.5倍ATR）
            sl_multiplier: 止损 = ATR * sl_multiplier（1.0倍ATR）
            max_holding_days: 最大持有天数
        """
        self.atr_window = atr_window
        self.tp_multiplier = tp_multiplier
        self.sl_multiplier = sl_multiplier
        self.max_holding_days = max_holding_days

    def compute_atr(self, df: pd.DataFrame) -> pd.Series:
        """计算ATR"""
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift(1)).abs()
        low_close = (df['low'] - df['close'].shift(1)).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return tr.rolling(window=self.atr_window).mean()

    def label(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        为数据生成 Triple-Barrier 标签

        Returns:
            DataFrame 新增列:
            - tb_label: 1=看涨, -1=看跌
            - tb_touch_day: 触碰屏障的天数（0-based）
            - tb_barrier_type: 'tp'/'sl'/'time'
            - tb_return: 屏障触碰时的收益率
            - tb_tp: 止盈价格
            - tb_sl: 止损价格
        """
        df = df.copy()
        atr = self.compute_atr(df)

        labels = []
        touch_days = []
        barrier_types = []
        returns = []
        tp_levels = []
        sl_levels = []

        close = df['close'].values
        atr_vals = atr.values

        for i in range(len(df)):
            if i >= len(df) - self.max_holding_days or np.isnan(atr_vals[i]):
                labels.append(0)
                touch_days.append(0)
                barrier_types.append('none')
                returns.append(0.0)
                tp_levels.append(np.nan)
                sl_levels.append(np.nan)
                continue

            current_price = close[i]
            atr_val = atr_vals[i]

            tp_price = current_price + atr_val * self.tp_multiplier
            sl_price = current_price - atr_val * self.sl_multiplier

            tp_levels.append(tp_price)
            sl_levels.append(sl_price)

            # 检查未来 max_holding_days 天内哪个屏障先触碰
            touched = False
            for d in range(1, self.max_holding_days + 1):
                if i + d >= len(df):
                    break

                future_high = df['high'].iloc[i + d]
                future_low = df['low'].iloc[i + d]

                # 先检查止损（同一天内止损优先，更保守）
                if future_low <= sl_price:
                    labels.append(-1)
                    touch_days.append(d)
                    barrier_types.append('sl')
                    ret = (sl_price - current_price) / current_price
                    returns.append(ret)
                    touched = True
                    break

                # 再检查止盈
                if future_high >= tp_price:
                    labels.append(1)
                    touch_days.append(d)
                    barrier_types.append('tp')
                    ret = (tp_price - current_price) / current_price
                    returns.append(ret)
                    touched = True
                    break

            if not touched:
                # 时间屏障：到期平仓
                end_idx = min(i + self.max_holding_days, len(df) - 1)
                end_price = close[end_idx]
                ret = (end_price - current_price) / current_price
                labels.append(1 if ret > 0 else -1)
                touch_days.append(self.max_holding_days)
                barrier_types.append('time')
                returns.append(ret)

        df['tb_label'] = labels
        df['tb_touch_day'] = touch_days
        df['tb_barrier_type'] = barrier_types
        df['tb_return'] = returns
        df['tb_tp'] = tp_levels
        df['tb_sl'] = sl_levels

        return df

    def prepare_tb_features(self, df: pd.DataFrame, target_horizon: int = 1) -> Tuple[pd.DataFrame, pd.Series]:
        """
        准备 Triple-Barrier 模式的特征和标签

        标签为分类：1=看涨, -1=看跌
        """
        df = self.label(df)
        fe = FeatureEngineer()

        df = fe.create_technical_features(df)
        df = fe.create_macro_features(df)
        df = fe.create_lag_features(df)

        feature_cols = [c for c in df.columns if c not in [
            'target', 'date', 'open', 'high', 'low', 'close', 'volume',
            'asset_code', 'asset_type', 'source', 'amount', 'change',
            'ma_5', 'ma_10', 'ma_20', 'ma_60',
            'volatility_5', 'volatility_20',
            'macd_hist',
            'bb_upper', 'bb_middle', 'bb_lower',
            'high_low_range',
            'tb_label', 'tb_touch_day', 'tb_barrier_type', 'tb_return', 'tb_tp', 'tb_sl',
        ]]

        df_clean = df[feature_cols + ['tb_label']].dropna()
        # 只保留有效标签（非0）
        df_clean = df_clean[df_clean['tb_label'] != 0]

        X = df_clean[feature_cols]
        y = df_clean['tb_label']

        return X, y


class GoldPricePredictor:
    """黄金价格预测器"""

    def __init__(self, model_dir: str = "data/models"):
        self.model_dir = model_dir
        os.makedirs(model_dir, exist_ok=True)

        self.feature_engineer = FeatureEngineer()
        self.models = {}
        self.scalers = {}
        self.oos_error_std = {}  # 每个模型的OOS误差标准差

    def train(self, df: pd.DataFrame, model_type: ModelType = ModelType.LIGHTGBM,
              horizon: PredictionHorizon = PredictionHorizon.SHORT,
              test_size: float = 0.2) -> Dict[str, Any]:
        """
        训练模型（含因子筛选）

        Args:
            df: 训练数据
            model_type: 模型类型
            horizon: 预测周期
            test_size: 测试集比例

        Returns:
            训练结果
        """
        logger.info(f"Training {model_type.value} model for {horizon.name} horizon")

        X, y = self.feature_engineer.prepare_features(df, target_horizon=horizon.value)

        if len(X) < 50:
            raise ValueError(f"Insufficient data: {len(X)} samples (minimum 50)")

        # 因子筛选（互信息 + 相关性去冗余）
        X_selected, screening_report = self.feature_engineer.select_features(X, y)

        # 时序划分（不用random split）
        split_idx = int(len(X_selected) * (1 - test_size))
        X_train, X_test = X_selected.iloc[:split_idx], X_selected.iloc[split_idx:]
        y_aligned = y.loc[X_selected.index]
        y_train, y_test = y_aligned.iloc[:split_idx], y_aligned.iloc[split_idx:]

        # 标准化
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        self.scalers[model_type.value] = scaler

        # 训练模型
        if model_type == ModelType.LIGHTGBM:
            model = self._train_lightgbm(X_train_scaled, y_train)
        elif model_type == ModelType.XGBOOST:
            model = self._train_xgboost(X_train_scaled, y_train)
        elif model_type == ModelType.RIDGE:
            model = self._train_ridge(X_train_scaled, y_train)
        else:
            raise ValueError(f"Unsupported model type: {model_type}")

        self.models[model_type.value] = model

        # SHAP验证（树模型）— 仅报告，不改变特征集
        shap_report = {}
        if model_type in (ModelType.LIGHTGBM, ModelType.XGBOOST):
            _, shap_report = self.feature_engineer.select_features(
                X_selected, y_aligned, shap_model=model
            )
            # SHAP验证仅作为报告，selected_features_已经由MI+corr确定
            # 恢复MI+corr筛选的特征集
            self.feature_engineer.selected_features_ = list(X_selected.columns)

        # 评估
        y_pred = model.predict(X_test_scaled)

        # 记录OOS误差标准差（用于置信度估算）
        oos_errors = (y_test.values - y_pred)
        self.oos_error_std[model_type.value] = np.std(oos_errors)

        metrics = {
            'rmse': np.sqrt(mean_squared_error(y_test, y_pred)),
            'mae': mean_absolute_error(y_test, y_pred),
            'r2': r2_score(y_test, y_pred),
            'directional_accuracy': self._directional_accuracy(y_test, y_pred),
            'oos_error_std': float(self.oos_error_std[model_type.value]),
            'test_samples': len(y_test)
        }

        logger.info(f"Training completed: {metrics}")

        return {
            'model_type': model_type.value,
            'horizon': horizon.value,
            'metrics': metrics,
            'feature_count': X_selected.shape[1],
            'features': list(X_selected.columns),
            'screening_report': screening_report,
            'shap_report': shap_report
        }

    def predict(self, df: pd.DataFrame, model_type: ModelType = ModelType.LIGHTGBM,
                horizon: PredictionHorizon = PredictionHorizon.SHORT,
                use_last_known_price: bool = True) -> PredictionResult:
        """预测黄金价格"""
        if model_type.value not in self.models:
            raise ValueError(f"Model {model_type.value} not trained. Call train() first.")

        X = self.feature_engineer.prepare_features_for_prediction(df)

        if len(X) == 0:
            raise ValueError("No valid features for prediction")

        X_latest = X.iloc[-1:]
        scaler = self.scalers[model_type.value]
        X_scaled = scaler.transform(X_latest)

        model = self.models[model_type.value]
        predicted_return = model.predict(X_scaled)[0].item()

        if use_last_known_price:
            current_price = df['close'].iloc[-1]
        else:
            raise ValueError("Real-time price prediction not implemented. Please use last known price.")

        predicted_price = current_price * (1 + predicted_return)

        # 基于OOS误差分布的置信度
        confidence = self._calculate_confidence(model_type, predicted_return)

        return PredictionResult(
            asset_code='GC',
            current_price=round(current_price, 2),
            predicted_price=round(predicted_price, 2),
            predicted_change=round(predicted_price - current_price, 2),
            predicted_change_percent=round(predicted_return * 100, 2),
            confidence=round(confidence, 2),
            horizon=horizon.value,
            model_type=model_type.value,
            features_used=list(X.columns),
            timestamp=datetime.now(),
            metadata={
                'price_reference_date': df['date'].iloc[-1] if 'date' in df.columns else None,
                'oos_error_std': self.oos_error_std.get(model_type.value),
                'note': 'Prediction based on last known closing price to avoid data leakage'
            }
        )

    def train_tb(self, df: pd.DataFrame, model_type: ModelType = ModelType.LIGHTGBM,
                 test_size: float = 0.2) -> Dict[str, Any]:
        """
        使用 Triple-Barrier 标签训练分类模型

        Returns:
            训练结果
        """
        logger.info(f"Training TB classifier: {model_type.value}")

        labeler = TripleBarrierLabeler()
        X, y = labeler.prepare_tb_features(df)

        if len(X) < 50:
            raise ValueError(f"Insufficient data for TB: {len(X)} samples (minimum 50)")

        # 因子筛选
        X_selected, screening_report = self.feature_engineer.select_features(X, y)

        # 时序划分
        split_idx = int(len(X_selected) * (1 - test_size))
        X_train, X_test = X_selected.iloc[:split_idx], X_selected.iloc[split_idx:]
        y_aligned = y.loc[X_selected.index]
        y_train, y_test = y_aligned.iloc[:split_idx], y_aligned.iloc[split_idx:]

        # 标准化
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        tb_key = f"tb_{model_type.value}"
        self.scalers[tb_key] = scaler

        # 训练分类器
        if model_type in (ModelType.LIGHTGBM, ModelType.XGBOOST):
            model = self._train_tb_classifier(X_train_scaled, y_train, model_type)
        elif model_type == ModelType.RIDGE:
            model = self._train_tb_ridge(X_train_scaled, y_train)
        else:
            raise ValueError(f"Unsupported model type: {model_type}")

        self.models[tb_key] = model

        # 评估
        y_pred = model.predict(X_test_scaled)

        # 方向准确率
        da = float(np.mean(y_pred * y_test.values > 0))

        # 分类准确率
        accuracy = float(np.mean(y_pred == y_test.values))

        metrics = {
            'directional_accuracy': round(da, 4),
            'accuracy': round(accuracy, 4),
            'test_samples': len(y_test),
            'label_distribution': {
                'bull': int((y_test == 1).sum()),
                'bear': int((y_test == -1).sum()),
            }
        }

        logger.info(f"TB training completed: {metrics}")

        return {
            'model_type': model_type.value,
            'mode': 'triple_barrier',
            'metrics': metrics,
            'feature_count': X_selected.shape[1],
            'features': list(X_selected.columns),
            'screening_report': screening_report,
        }

    def predict_tb(self, df: pd.DataFrame, model_type: ModelType = ModelType.LIGHTGBM) -> TripleBarrierResult:
        """
        使用 Triple-Barrier 模型预测方向概率

        Returns:
            TripleBarrierResult
        """
        tb_key = f"tb_{model_type.value}"
        if tb_key not in self.models:
            raise ValueError(f"TB model {model_type.value} not trained. Call train_tb() first.")

        labeler = TripleBarrierLabeler()
        X = self.feature_engineer.prepare_features_for_prediction(df)

        if len(X) == 0:
            raise ValueError("No valid features for TB prediction")

        X_latest = X.iloc[-1:]
        scaler = self.scalers[tb_key]
        X_scaled = scaler.transform(X_latest)

        model = self.models[tb_key]
        current_price = df['close'].iloc[-1]

        # 计算ATR和屏障
        atr = labeler.compute_atr(df)
        atr_val = atr.iloc[-1] if not atr.empty else 0

        tp_level = current_price + atr_val * labeler.tp_multiplier
        sl_level = current_price - atr_val * labeler.sl_multiplier

        # 预测
        if hasattr(model, 'predict_proba'):
            proba = model.predict_proba(X_scaled)[0]
            # 二分类：class顺序可能是 [-1, 1] 或 [1, -1]
            classes = model.classes_
            bull_idx = list(classes).index(1) if 1 in classes else 1
            bear_idx = list(classes).index(-1) if -1 in classes else 0
            direction_prob = float(proba[bull_idx])
            direction = 1 if direction_prob > 0.5 else -1
        else:
            raw_pred = model.predict(X_scaled)[0]
            direction = 1 if raw_pred > 0 else -1
            direction_prob = 0.5 + abs(float(raw_pred)) * 0.3  # 简单映射

        direction_prob = min(0.95, max(0.05, direction_prob))
        confidence = abs(direction_prob - 0.5) * 2  # 距离0.5越远越确信

        return TripleBarrierResult(
            asset_code='GC',
            current_price=round(current_price, 2),
            direction=direction,
            direction_probability=round(direction_prob, 4),
            tp_level=round(tp_level, 2),
            sl_level=round(sl_level, 2),
            max_holding_days=labeler.max_holding_days,
            atr_value=round(atr_val, 4),
            confidence=round(confidence, 4),
            model_type=model_type.value,
            features_used=list(X.columns),
            timestamp=datetime.now(),
            metadata={
                'price_reference_date': df['date'].iloc[-1] if 'date' in df.columns else None,
                'mode': 'triple_barrier',
            }
        )

    def _train_tb_classifier(self, X_train: np.ndarray, y_train: pd.Series, model_type: ModelType) -> Any:
        """训练 TB 分类器（LightGBM/XGBoost）"""
        # 将标签从 [-1, 1] 映射到 [0, 1]
        y_mapped = y_train.map({-1: 0, 1: 1})

        if model_type == ModelType.LIGHTGBM:
            try:
                import lightgbm as lgb
                model = lgb.LGBMClassifier(
                    n_estimators=200,
                    max_depth=5,
                    learning_rate=0.05,
                    subsample=0.8,
                    colsample_bytree=0.8,
                    reg_alpha=0.1,
                    reg_lambda=0.1,
                    min_child_samples=20,
                    random_state=42,
                    verbose=-1,
                )
                model.fit(X_train, y_mapped)
                return model
            except ImportError:
                pass

        # XGBoost or LightGBM fallback
        try:
            import xgboost as xgb
            model = xgb.XGBClassifier(
                n_estimators=200,
                max_depth=5,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8,
                reg_alpha=0.1,
                reg_lambda=0.1,
                random_state=42,
                verbosity=0,
                use_label_encoder=False,
            )
            model.fit(X_train, y_mapped)
            return model
        except ImportError:
            return self._train_tb_ridge(X_train, y_train)

    def _train_tb_ridge(self, X_train: np.ndarray, y_train: pd.Series) -> Any:
        """Ridge 分类器（作为基准线）"""
        from sklearn.linear_model import RidgeClassifier
        model = RidgeClassifier(alpha=1.0, random_state=42)
        model.fit(X_train, y_train)
        return model

    def _train_lightgbm(self, X_train: np.ndarray, y_train: pd.Series) -> Any:
        """训练LightGBM模型"""
        try:
            import lightgbm as lgb

            model = lgb.LGBMRegressor(
                n_estimators=200,
                max_depth=5,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8,
                reg_alpha=0.1,
                reg_lambda=0.1,
                min_child_samples=20,
                random_state=42,
                verbose=-1
            )
            model.fit(X_train, y_train)
            return model

        except ImportError:
            logger.warning("LightGBM not installed, falling back to XGBoost")
            return self._train_xgboost(X_train, y_train)

    def _train_xgboost(self, X_train: np.ndarray, y_train: pd.Series) -> Any:
        """训练XGBoost模型"""
        try:
            import xgboost as xgb

            model = xgb.XGBRegressor(
                n_estimators=200,
                max_depth=5,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8,
                reg_alpha=0.1,
                reg_lambda=0.1,
                random_state=42,
                verbosity=0
            )
            model.fit(X_train, y_train)
            return model

        except ImportError:
            logger.warning("XGBoost not installed, falling back to Ridge")
            return self._train_ridge(X_train, y_train)

    def _train_ridge(self, X_train: np.ndarray, y_train: pd.Series) -> Any:
        """训练Ridge基准模型"""
        model = Ridge(alpha=1.0, random_state=42)
        model.fit(X_train, y_train)
        return model

    def compute_factor_importance(self, model_type: ModelType = ModelType.LIGHTGBM) -> Dict[str, Any]:
        """
        计算因子重要性（MI + SHAP/feature_importance）

        Returns:
            因子重要性报告
        """
        model = self.models.get(model_type.value)
        if model is None:
            return {'error': f'Model {model_type.value} not trained'}

        selected_features = self.feature_engineer.selected_features_ or []

        if model_type in (ModelType.LIGHTGBM, ModelType.XGBOOST):
            # 用feature_importances_（比SHAP更稳定，不需要原始数据）
            if hasattr(model, 'feature_importances_') and selected_features:
                importance = dict(zip(selected_features, model.feature_importances_))
                method = 'feature_importances_'
            else:
                importance = {}
                method = 'unknown'
        elif model_type == ModelType.RIDGE:
            if hasattr(model, 'coef_') and selected_features:
                importance = dict(zip(selected_features, np.abs(model.coef_)))
                method = 'ridge_abs_coef'
            else:
                importance = {}
                method = 'unknown'
        else:
            importance = {}
            method = 'unknown'

        # 排序
        sorted_importance = dict(sorted(importance.items(), key=lambda x: -x[1]))

        return {
            'model_type': model_type.value,
            'method': method,
            'features': sorted_importance,
            'selected_count': len(selected_features)
        }

    def _calculate_confidence(self, model_type: ModelType, predicted_return: float) -> float:
        """基于walk-forward OOS误差分布计算置信度"""
        error_std = self.oos_error_std.get(model_type.value)
        if error_std is None or error_std < 1e-10:
            return 0.5

        # 信号强度相对于历史误差
        signal_to_noise = np.abs(predicted_return) / error_std
        # 映射到[0.3, 0.95]，信号越强置信度越高
        confidence = min(0.95, max(0.3, 1 - np.exp(-signal_to_noise)))
        return confidence

    @staticmethod
    def _directional_accuracy(y_true: pd.Series, y_pred: np.ndarray) -> float:
        """计算方向准确率"""
        true_direction = np.sign(y_true.values)
        pred_direction = np.sign(y_pred)
        return float(np.mean(true_direction == pred_direction))

    def save_model(self, model_type: ModelType, filename: str = None, mode: str = "regression"):
        """保存模型

        Args:
            model_type: 模型类型
            filename: 文件名
            mode: 'regression' 或 'triple_barrier'
        """
        prefix = "gold_predictor" if mode == "regression" else "gold_tb_predictor"
        if filename is None:
            filename = f"{prefix}_{model_type.value}_{datetime.now().strftime('%Y%m%d')}.pkl"

        filepath = os.path.join(self.model_dir, filename)

        key = f"tb_{model_type.value}" if mode == "triple_barrier" else model_type.value

        model_data = {
            'model': self.models.get(key),
            'scaler': self.scalers.get(key),
            'oos_error_std': self.oos_error_std.get(model_type.value) if mode == "regression" else None,
            'selected_features': self.feature_engineer.selected_features_,
            'model_type': model_type.value,
            'mode': mode,
            'feature_engineer_version': 2,
            'saved_at': datetime.now().isoformat()
        }

        with open(filepath, 'wb') as f:
            pickle.dump(model_data, f)

        logger.info(f"Model saved to {filepath}")
        return filepath

    def load_model(self, filepath: str):
        """加载模型"""
        with open(filepath, 'rb') as f:
            model_data = pickle.load(f)

        model_type = model_data['model_type']
        mode = model_data.get('mode', 'regression')
        key = f"tb_{model_type}" if mode == "triple_barrier" else model_type

        self.models[key] = model_data['model']
        self.scalers[key] = model_data['scaler']
        if mode == "regression":
            self.oos_error_std[model_type] = model_data.get('oos_error_std')

        # 恢复筛选后的特征列表
        selected = model_data.get('selected_features')
        if selected:
            self.feature_engineer.selected_features_ = selected

        logger.info(f"Model loaded from {filepath} (mode={mode})")


class ModelManager:
    """模型管理器：持久化、缓存、退化检测"""

    _instance = None
    _lock = threading.Lock()
    DRIFT_WINDOW = 20       # 检测窗口：最近N次预测
    DRIFT_THRESHOLD = 0.50  # 方向准确率低于此值触发重训

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, model_dir: str = "data/models", max_age_days: int = 7):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        self.model_dir = model_dir
        self.max_age_days = max_age_days
        self._predictors: Dict[str, GoldPricePredictor] = {}
        self._lock = threading.Lock()
        self._prediction_log: Dict[str, List[Dict]] = {}  # key -> [{date, predicted_dir, actual_dir}]
        os.makedirs(model_dir, exist_ok=True)
        self._load_prediction_log()

    def _key(self, model_type: ModelType, horizon: PredictionHorizon) -> str:
        return f"{model_type.value}_{horizon.value}"

    def get_predictor(self, model_type: ModelType, horizon: PredictionHorizon) -> Optional[GoldPricePredictor]:
        """获取预测器（优先内存缓存，其次磁盘）"""
        key = self._key(model_type, horizon)

        with self._lock:
            if key in self._predictors:
                return self._predictors[key]

        # 尝试从磁盘加载
        model_path = self._find_latest_model(model_type, horizon)
        if model_path and self._is_model_fresh(model_path):
            predictor = GoldPricePredictor(self.model_dir)
            try:
                predictor.load_model(model_path)
                with self._lock:
                    self._predictors[key] = predictor
                logger.info(f"Loaded cached model from {model_path}")
                return predictor
            except Exception as e:
                logger.warning(f"Failed to load model from {model_path}: {e}")

        return None

    def save_predictor(self, predictor: GoldPricePredictor,
                       model_type: ModelType, horizon: PredictionHorizon,
                       metrics: Dict = None, mode: str = "regression") -> str:
        """保存预测器到内存和磁盘"""
        # TB 模型使用不同的 key
        key = f"tb_{model_type.value}_{horizon.value}" if mode == "triple_barrier" else self._key(model_type, horizon)

        with self._lock:
            self._predictors[key] = predictor

        filepath = predictor.save_model(model_type, mode=mode)

        # 保存元数据
        meta_path = filepath.replace('.pkl', '.meta.json')
        meta = {
            'model_type': model_type.value,
            'horizon': horizon.value,
            'saved_at': datetime.now().isoformat(),
            'metrics': metrics,
            'filepath': filepath
        }
        with open(meta_path, 'w') as f:
            json.dump(meta, f, indent=2, default=str)

        return filepath

    def get_or_train(self, df: pd.DataFrame,
                     model_type: ModelType = ModelType.LIGHTGBM,
                     horizon: PredictionHorizon = PredictionHorizon.SHORT) -> Tuple[GoldPricePredictor, Dict]:
        """
        获取模型或训练新模型

        Returns:
            (predictor, train_result)
        """
        predictor = self.get_predictor(model_type, horizon)
        if predictor is not None:
            return predictor, {'model_type': model_type.value, 'source': 'cache'}

        # 训练新模型
        logger.info(f"No cached model for {model_type.value}/{horizon.name}, training...")
        predictor = GoldPricePredictor(self.model_dir)
        train_result = predictor.train(df, model_type, horizon)

        self.save_predictor(predictor, model_type, horizon, train_result.get('metrics'))

        return predictor, train_result

    def invalidate(self, model_type: ModelType = None, horizon: PredictionHorizon = None):
        """清除缓存"""
        with self._lock:
            if model_type is None and horizon is None:
                self._predictors.clear()
            else:
                keys_to_remove = []
                for key in self._predictors:
                    parts = key.rsplit('_', 1)
                    mt, h = parts[0], int(parts[1])
                    if model_type and mt == model_type.value:
                        keys_to_remove.append(key)
                    elif horizon and h == horizon.value:
                        keys_to_remove.append(key)
                for key in keys_to_remove:
                    del self._predictors[key]

    def check_model_drift(self, model_type: ModelType, horizon: PredictionHorizon,
                          recent_accuracy: float, threshold: float = 0.50) -> bool:
        """检测模型退化，返回True表示需要重训"""
        if recent_accuracy < threshold:
            logger.warning(
                f"Model drift detected: {model_type.value}/{horizon.name} "
                f"accuracy={recent_accuracy:.2%} < threshold={threshold:.2%}"
            )
            self.invalidate(model_type, horizon)
            return True
        return False

    def record_prediction(self, model_type: ModelType, horizon: PredictionHorizon,
                          predicted_direction: int, date: str = None):
        """记录一次预测方向（1=看涨, -1=看跌, 0=中性）"""
        key = self._key(model_type, horizon)
        if key not in self._prediction_log:
            self._prediction_log[key] = []

        entry = {
            'date': date or datetime.now().strftime('%Y-%m-%d'),
            'predicted_dir': predicted_direction,
            'actual_dir': None  # 待后续更新
        }
        self._prediction_log[key].append(entry)
        self._save_prediction_log()

    def record_actual(self, model_type: ModelType, horizon: PredictionHorizon,
                      date: str, actual_direction: int):
        """更新实际方向（1=涨, -1=跌, 0=平）"""
        key = self._key(model_type, horizon)
        entries = self._prediction_log.get(key, [])

        # 找到对应日期的未更新记录
        for entry in reversed(entries):
            if entry['date'] == date and entry['actual_dir'] is None:
                entry['actual_dir'] = actual_direction
                break

        self._save_prediction_log()

    def get_drift_status(self, model_type: ModelType = None,
                         horizon: PredictionHorizon = None) -> Dict[str, Any]:
        """
        获取模型漂移状态

        Returns:
            每个模型的漂移状态报告
        """
        result = {}
        for key, entries in self._prediction_log.items():
            parts = key.rsplit('_', 1)
            mt, h = parts[0], int(parts[1])

            if model_type and mt != model_type.value:
                continue
            if horizon and h != horizon.value:
                continue

            # 计算最近N次预测的方向准确率
            verified = [e for e in entries if e['actual_dir'] is not None]
            recent = verified[-self.DRIFT_WINDOW:]

            if not recent:
                result[key] = {
                    'model_type': mt,
                    'horizon': h,
                    'total_predictions': len(entries),
                    'verified_predictions': 0,
                    'directional_accuracy': None,
                    'drift_detected': False,
                    'status': 'no_data'
                }
                continue

            correct = sum(1 for e in recent if e['predicted_dir'] * e['actual_dir'] > 0)
            da = correct / len(recent)

            drift = da < self.DRIFT_THRESHOLD and len(recent) >= 5

            result[key] = {
                'model_type': mt,
                'horizon': h,
                'total_predictions': len(entries),
                'verified_predictions': len(verified),
                'recent_window': len(recent),
                'directional_accuracy': round(da, 4),
                'drift_detected': drift,
                'drift_threshold': self.DRIFT_THRESHOLD,
                'status': 'drift_detected' if drift else 'healthy' if da >= 0.55 else 'warning'
            }

        # 如果没有指定模型，返回所有；如果指定但没有数据，返回空
        if not result and (model_type or horizon):
            key = self._key(model_type or ModelType.LIGHTGBM, horizon or PredictionHorizon.SHORT)
            result[key] = {
                'model_type': (model_type or ModelType.LIGHTGBM).value,
                'horizon': (horizon or PredictionHorizon.SHORT).value,
                'total_predictions': 0,
                'verified_predictions': 0,
                'directional_accuracy': None,
                'drift_detected': False,
                'status': 'no_data'
            }

        return result

    def auto_drift_check(self, df: pd.DataFrame) -> Dict[str, bool]:
        """
        自动漂移检测：对比历史预测与实际结果

        Args:
            df: 含close列的DataFrame，需要有date列

        Returns:
            {model_key: needs_retrain}
        """
        retrain_needed = {}

        for key, entries in self._prediction_log.items():
            verified = [e for e in entries if e['actual_dir'] is not None]
            recent = verified[-self.DRIFT_WINDOW:]

            if len(recent) < 5:
                retrain_needed[key] = False
                continue

            correct = sum(1 for e in recent if e['predicted_dir'] * e['actual_dir'] > 0)
            da = correct / len(recent)

            if da < self.DRIFT_THRESHOLD:
                parts = key.rsplit('_', 1)
                mt_str, h = parts[0], int(parts[1])
                mt_map = {m.value: m for m in ModelType}
                h_map = {h.value: h for h in PredictionHorizon}

                mt_enum = mt_map.get(mt_str)
                h_enum = h_map.get(h)

                if mt_enum and h_enum:
                    logger.warning(f"Auto drift: {key} DA={da:.2%}, triggering retrain")
                    self.invalidate(mt_enum, h_enum)
                    retrain_needed[key] = True
                else:
                    retrain_needed[key] = False
            else:
                retrain_needed[key] = False

        return retrain_needed

    def _prediction_log_path(self) -> str:
        return os.path.join(self.model_dir, 'prediction_log.json')

    def _save_prediction_log(self):
        """持久化预测记录到磁盘"""
        try:
            with open(self._prediction_log_path(), 'w') as f:
                json.dump(self._prediction_log, f, indent=2, default=str)
        except Exception as e:
            logger.warning(f"Failed to save prediction log: {e}")

    def _load_prediction_log(self):
        """从磁盘加载预测记录"""
        try:
            path = self._prediction_log_path()
            if os.path.exists(path):
                with open(path, 'r') as f:
                    self._prediction_log = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load prediction log: {e}")
            self._prediction_log = {}

    def _find_latest_model(self, model_type: ModelType, horizon: PredictionHorizon) -> Optional[str]:
        """查找最新的模型文件"""
        prefix = f"gold_predictor_{model_type.value}_"
        candidates = []

        for f in os.listdir(self.model_dir):
            if f.startswith(prefix) and f.endswith('.pkl'):
                filepath = os.path.join(self.model_dir, f)
                # 检查meta文件中的horizon是否匹配
                meta_path = filepath.replace('.pkl', '.meta.json')
                if os.path.exists(meta_path):
                    try:
                        with open(meta_path, 'r') as mf:
                            meta = json.load(mf)
                        if meta.get('horizon') == horizon.value:
                            candidates.append(filepath)
                    except Exception:
                        continue
                else:
                    # 无meta文件，用文件名日期排序
                    candidates.append(filepath)

        if not candidates:
            return None

        # 按修改时间排序，取最新
        candidates.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        return candidates[0]

    def _is_model_fresh(self, model_path: str) -> bool:
        """模型是否新鲜"""
        mtime = datetime.fromtimestamp(os.path.getmtime(model_path))
        age = (datetime.now() - mtime).days
        return age <= self.max_age_days


# 全局ModelManager实例
model_manager = ModelManager()


# 便捷函数
def train_and_predict(df: pd.DataFrame, horizon_days: int = 1) -> PredictionResult:
    """训练并预测（一站式函数）"""
    horizon_map = {1: PredictionHorizon.SHORT, 5: PredictionHorizon.MEDIUM, 20: PredictionHorizon.LONG}
    horizon = horizon_map.get(horizon_days, PredictionHorizon.SHORT)

    predictor, _ = model_manager.get_or_train(df, ModelType.LIGHTGBM, horizon)
    return predictor.predict(df, ModelType.LIGHTGBM, horizon, use_last_known_price=True)
