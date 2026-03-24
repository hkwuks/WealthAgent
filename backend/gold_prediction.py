"""
黄金价格预测模块

提供多模型黄金价格预测能力：
1. XGBoost - 基于宏观因子的预测
2. LSTM - 基于时序模式的预测
3. 集成模型 - 多模型融合
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum
import pickle
import os

from sklearn.preprocessing import StandardScaler, MinMaxScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

from loguru import logger

logger.add("./logs/gold_prediction.log", encoding="utf-8", rotation="10 MB")


class ModelType(Enum):
    """模型类型"""
    XGBOOST = "xgboost"
    LSTM = "lstm"
    ENSEMBLE = "ensemble"


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


class FeatureEngineer:
    """特征工程"""

    def __init__(self):
        self.scaler = StandardScaler()

    def create_technical_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """创建技术指标特征"""
        df = df.copy()

        # 价格特征
        df['returns'] = df['close'].pct_change()
        df['log_returns'] = np.log(df['close'] / df['close'].shift(1))

        # 移动平均线
        for window in [5, 10, 20, 60]:
            df[f'ma_{window}'] = df['close'].rolling(window=window).mean()
            df[f'ma_ratio_{window}'] = df['close'] / df[f'ma_{window}']

        # 波动率
        for window in [5, 20]:
            df[f'volatility_{window}'] = df['returns'].rolling(window=window).std()

        # RSI
        df['rsi_14'] = self._calculate_rsi(df['close'], 14)

        # MACD
        df['macd'], df['macd_signal'], df['macd_hist'] = self._calculate_macd(df['close'])

        # 布林带
        df['bb_upper'], df['bb_middle'], df['bb_lower'] = self._calculate_bollinger(df['close'])
        df['bb_position'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])

        # 价格位置
        df['high_low_range'] = df['high'] - df['low']
        df['close_position'] = (df['close'] - df['low']) / (df['high'] - df['low'] + 1e-10)

        return df

    def create_macro_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """创建宏观特征"""
        df = df.copy()

        # 美元指数相关
        if 'DXY_value' in df.columns:
            df['DXY_change'] = df['DXY_value'].pct_change()
            df['DXY_ma_5'] = df['DXY_value'].rolling(5).mean()
            df['gold_dxy_ratio'] = df['close'] / df['DXY_value']

        # VIX相关
        if 'VIX_value' in df.columns:
            df['VIX_change'] = df['VIX_value'].pct_change()
            df['VIX_ma_5'] = df['VIX_value'].rolling(5).mean()

        # 利率相关
        if 'US10Y_value' in df.columns:
            df['US10Y_change'] = df['US10Y_value'].pct_change()
            df['real_rate_proxy'] = df['US10Y_value'] - df.get('inflation_expectation', 2.0)

        return df

    def create_lag_features(self, df: pd.DataFrame, lags: List[int] = None) -> pd.DataFrame:
        """创建滞后特征"""
        if lags is None:
            lags = [1, 2, 3, 5, 10]

        df = df.copy()
        feature_cols = ['close', 'returns', 'volume']

        for col in feature_cols:
            if col in df.columns:
                for lag in lags:
                    df[f'{col}_lag_{lag}'] = df[col].shift(lag)

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
        # 创建特征
        df = self.create_technical_features(df)
        df = self.create_macro_features(df)
        df = self.create_lag_features(df)

        # 创建目标变量（未来收益率）- 仅用于训练
        df['target'] = df['close'].shift(-target_horizon) / df['close'] - 1

        # 选择特征列
        feature_cols = [c for c in df.columns if c not in [
            'target', 'date', 'open', 'high', 'low', 'close', 'volume',
            'asset_code', 'asset_type', 'source', 'amount', 'change'
        ]]

        # 删除NaN
        df_clean = df[feature_cols + ['target']].dropna()

        X = df_clean[feature_cols]
        y = df_clean['target']

        return X, y

    def prepare_features_for_prediction(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        准备特征用于预测（不包含未来信息）

        Args:
            df: 原始数据，最后一行应该是预测基准日（通常是上一交易日）

        Returns:
            特征DataFrame（仅包含可用于预测的特征）
        """
        # 创建特征（不使用未来数据）
        df = self.create_technical_features(df)
        df = self.create_macro_features(df)
        df = self.create_lag_features(df)

        # 选择特征列（不包含target）
        feature_cols = [c for c in df.columns if c not in [
            'target', 'date', 'open', 'high', 'low', 'close', 'volume',
            'asset_code', 'asset_type', 'source', 'amount', 'change'
        ]]

        # 只保留有完整特征的行
        X = df[feature_cols].dropna()

        return X

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


class GoldPricePredictor:
    """黄金价格预测器"""

    def __init__(self, model_dir: str = "data/models"):
        self.model_dir = model_dir
        os.makedirs(model_dir, exist_ok=True)

        self.feature_engineer = FeatureEngineer()
        self.models = {}
        self.scalers = {}

    def train(self, df: pd.DataFrame, model_type: ModelType = ModelType.XGBOOST,
              horizon: PredictionHorizon = PredictionHorizon.SHORT,
              test_size: float = 0.2) -> Dict[str, Any]:
        """
        训练模型

        Args:
            df: 训练数据
            model_type: 模型类型
            horizon: 预测周期
            test_size: 测试集比例

        Returns:
            训练结果
        """
        logger.info(f"Training {model_type.value} model for {horizon.name} horizon")

        # 准备特征
        X, y = self.feature_engineer.prepare_features(df, target_horizon=horizon.value)

        if len(X) < 100:
            raise ValueError(f"Insufficient data: {len(X)} samples")

        # 划分训练测试集
        split_idx = int(len(X) * (1 - test_size))
        X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
        y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

        # 标准化
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        self.scalers[model_type.value] = scaler

        # 训练模型
        if model_type == ModelType.XGBOOST:
            model = self._train_xgboost(X_train_scaled, y_train)
        elif model_type == ModelType.LSTM:
            model = self._train_lstm(X_train_scaled, y_train)
        else:
            raise ValueError(f"Unsupported model type: {model_type}")

        self.models[model_type.value] = model

        # 评估
        y_pred = self._predict_model(model, model_type, X_test_scaled)

        metrics = {
            'rmse': np.sqrt(mean_squared_error(y_test, y_pred)),
            'mae': mean_absolute_error(y_test, y_pred),
            'r2': r2_score(y_test, y_pred),
            'directional_accuracy': self._directional_accuracy(y_test, y_pred),
            'test_samples': len(y_test)
        }

        logger.info(f"Training completed: {metrics}")

        return {
            'model_type': model_type.value,
            'horizon': horizon.value,
            'metrics': metrics,
            'feature_count': X.shape[1],
            'features': list(X.columns)
        }

    def predict(self, df: pd.DataFrame, model_type: ModelType = ModelType.XGBOOST,
                horizon: PredictionHorizon = PredictionHorizon.SHORT,
                use_last_known_price: bool = True) -> PredictionResult:
        """
        预测黄金价格

        Args:
            df: 历史数据（至少包含最近60天）
            model_type: 模型类型
            horizon: 预测周期
            use_last_known_price: 是否使用最后一个已知收盘价作为基准（True=上一交易日收盘价，False=当前实时价格）

        Returns:
            预测结果
        """
        if model_type.value not in self.models:
            raise ValueError(f"Model {model_type.value} not trained. Call train() first.")

        # 使用预测专用的特征工程（不包含未来信息）
        X = self.feature_engineer.prepare_features_for_prediction(df)

        if len(X) == 0:
            raise ValueError("No valid features for prediction")

        # 使用最新数据
        X_latest = X.iloc[-1:]
        scaler = self.scalers[model_type.value]
        X_scaled = scaler.transform(X_latest)

        # 预测
        model = self.models[model_type.value]
        predicted_return = self._predict_model(model, model_type, X_scaled)[0].item()

        # 基准价格：使用最后一个已知收盘价（上一交易日）
        # 避免使用当天收盘价，防止数据泄露
        if use_last_known_price:
            # 使用数据集中最后一个收盘价作为基准
            current_price = df['close'].iloc[-1]
        else:
            # 如果需要实时价格，应该由调用方传入，而不是从df中获取
            raise ValueError("Real-time price prediction not implemented. Please use last known price.")

        predicted_price = current_price * (1 + predicted_return)

        # 计算置信度（基于历史预测误差）
        confidence = self._calculate_confidence(model_type, X_scaled)

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
                'note': 'Prediction based on last known closing price to avoid data leakage'
            }
        )

    def _train_xgboost(self, X_train: np.ndarray, y_train: pd.Series) -> Any:
        """训练XGBoost模型"""
        try:
            import xgboost as xgb

            model = xgb.XGBRegressor(
                n_estimators=100,
                max_depth=5,
                learning_rate=0.1,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=42
            )
            model.fit(X_train, y_train)
            return model

        except ImportError:
            logger.warning("XGBoost not installed, using RandomForest")
            from sklearn.ensemble import RandomForestRegressor
            model = RandomForestRegressor(n_estimators=100, random_state=42)
            model.fit(X_train, y_train)
            return model

    def _train_lstm(self, X_train: np.ndarray, y_train: pd.Series) -> Any:
        """训练LSTM模型 (PyTorch)"""
        try:
            import torch
            import torch.nn as nn
            from torch.utils.data import DataLoader, TensorDataset

            device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

            # 重塑数据为LSTM格式 (samples, timesteps, features)
            X_train_lstm = X_train.reshape((X_train.shape[0], 1, X_train.shape[1]))
            X_tensor = torch.FloatTensor(X_train_lstm).to(device)
            y_tensor = torch.FloatTensor(y_train.values.reshape(-1, 1)).to(device)

            class LSTMModel(nn.Module):
                def __init__(self, input_size, hidden_size=50, num_layers=2):
                    super().__init__()
                    self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True, dropout=0.2)
                    self.fc = nn.Sequential(
                        nn.Linear(hidden_size, 25),
                        nn.ReLU(),
                        nn.Linear(25, 1)
                    )

                def forward(self, x):
                    lstm_out, _ = self.lstm(x)
                    return self.fc(lstm_out[:, -1, :])

            model = LSTMModel(X_train.shape[1]).to(device)
            optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
            criterion = nn.MSELoss()

            dataset = TensorDataset(X_tensor, y_tensor)
            loader = DataLoader(dataset, batch_size=32, shuffle=True)

            model.train()
            for epoch in range(50):
                for batch_X, batch_y in loader:
                    optimizer.zero_grad()
                    outputs = model(batch_X)
                    loss = criterion(outputs, batch_y)
                    loss.backward()
                    optimizer.step()

            model.eval()
            return model

        except ImportError:
            logger.warning("PyTorch not installed, using XGBoost for LSTM fallback")
            return self._train_xgboost(X_train, y_train)

    def _predict_model(self, model: Any, model_type: ModelType, X: np.ndarray) -> np.ndarray:
        """使用模型进行预测"""
        if model_type == ModelType.LSTM:
            import torch
            device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
            X = X.reshape((X.shape[0], 1, X.shape[1]))
            X_tensor = torch.FloatTensor(X).to(device)
            model.eval()
            with torch.no_grad():
                return model(X_tensor).cpu().numpy()
        return model.predict(X)

    def _calculate_confidence(self, model_type: ModelType, X: np.ndarray) -> float:
        """计算预测置信度（简化版）"""
        # 实际应用中应基于验证集误差计算
        return 0.75

    @staticmethod
    def _directional_accuracy(y_true: pd.Series, y_pred: np.ndarray) -> float:
        """计算方向准确率"""
        true_direction = np.sign(y_true.values)
        pred_direction = np.sign(y_pred)
        return np.mean(true_direction == pred_direction)

    def save_model(self, model_type: ModelType, filename: str = None):
        """保存模型"""
        if filename is None:
            filename = f"gold_predictor_{model_type.value}_{datetime.now().strftime('%Y%m%d')}.pkl"

        filepath = os.path.join(self.model_dir, filename)

        model_data = {
            'model': self.models.get(model_type.value),
            'scaler': self.scalers.get(model_type.value),
            'model_type': model_type.value,
            'saved_at': datetime.now()
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
        self.models[model_type] = model_data['model']
        self.scalers[model_type] = model_data['scaler']

        logger.info(f"Model loaded from {filepath}")


class EnsemblePredictor:
    """集成预测器 - 融合多个模型"""

    def __init__(self):
        self.predictors = []
        self.weights = []

    def add_predictor(self, predictor: GoldPricePredictor, weight: float = 1.0):
        """添加预测器"""
        self.predictors.append(predictor)
        self.weights.append(weight)

    def predict(self, df: pd.DataFrame, horizon: PredictionHorizon = PredictionHorizon.SHORT) -> PredictionResult:
        """集成预测"""
        predictions = []

        for predictor in self.predictors:
            try:
                pred = predictor.predict(df, ModelType.XGBOOST, horizon)
                predictions.append(pred)
            except Exception as e:
                logger.error(f"Predictor failed: {e}")

        if not predictions:
            raise ValueError("All predictors failed")

        # 加权平均
        total_weight = sum(self.weights[:len(predictions)])
        weighted_price = sum(
            p.predicted_price * w for p, w in zip(predictions, self.weights[:len(predictions)])
        ) / total_weight

        # 取最保守的置信度
        min_confidence = min(p.confidence for p in predictions)

        base_pred = predictions[0]

        return PredictionResult(
            asset_code=base_pred.asset_code,
            current_price=base_pred.current_price,
            predicted_price=round(weighted_price, 2),
            predicted_change=round(weighted_price - base_pred.current_price, 2),
            predicted_change_percent=round((weighted_price / base_pred.current_price - 1) * 100, 2),
            confidence=round(min_confidence * 0.9, 2),  # 集成略有降低
            horizon=horizon.value,
            model_type='ensemble',
            features_used=list(set(f for p in predictions for f in p.features_used)),
            timestamp=datetime.now(),
            metadata={'individual_predictions': [
                {'model': p.model_type, 'price': p.predicted_price, 'confidence': p.confidence}
                for p in predictions
            ]}
        )


# 便捷函数
def train_and_predict(df: pd.DataFrame, horizon_days: int = 1) -> PredictionResult:
    """
    训练并预测（一站式函数）

    Args:
        df: 历史数据DataFrame
        horizon_days: 预测天数 (1, 5, 20)

    Returns:
        预测结果
    """
    horizon_map = {1: PredictionHorizon.SHORT, 5: PredictionHorizon.MEDIUM, 20: PredictionHorizon.LONG}
    horizon = horizon_map.get(horizon_days, PredictionHorizon.SHORT)

    predictor = GoldPricePredictor()

    # 训练
    predictor.train(df, ModelType.XGBOOST, horizon)

    # 预测
    return predictor.predict(df, ModelType.XGBOOST, horizon)