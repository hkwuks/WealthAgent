"""
GoldPricePredictor — ML 模型训练与预测
"""
import numpy as np
import pandas as pd
import pickle
import os
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge, RidgeClassifier
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

from backend.gold.ml.types import ModelType, PredictionHorizon, PredictionResult, TripleBarrierResult
from backend.gold.ml.features import FeatureEngineer
from backend.config import settings
from loguru import logger


class GoldPricePredictor:
    """黄金价格预测器"""

    def __init__(self, model_dir: str = None):
        if model_dir is None:
            model_dir = settings.MODEL_DIR
        self.model_dir = model_dir
        os.makedirs(model_dir, exist_ok=True)
        self.feature_engineer = FeatureEngineer()
        self.models: dict = {}
        self.scalers: dict = {}
        self.oos_error_std: dict = {}

    def train(self, df: pd.DataFrame, model_type: ModelType = ModelType.LIGHTGBM,
              horizon: PredictionHorizon = PredictionHorizon.SHORT,
              test_size: float = 0.2) -> Dict[str, Any]:
        """训练模型（含因子筛选）"""
        X, y = self.feature_engineer.prepare_features(df, target_horizon=horizon.value)
        if len(X) < 50:
            raise ValueError(f"Insufficient data: {len(X)} samples (minimum 50)")

        split_idx = int(len(X) * (1 - test_size))
        X_train_raw, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
        y_train_raw, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

        X_selected, screening_report = self.feature_engineer.select_features(X_train_raw, y_train_raw)
        X_train = X_selected
        X_test_sel = X_test[X_selected.columns]

        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test_sel)
        self.scalers[model_type.value] = scaler

        if model_type == ModelType.LIGHTGBM:
            model = self._train_lightgbm(X_train_scaled, y_train_raw)
        elif model_type == ModelType.XGBOOST:
            model = self._train_xgboost(X_train_scaled, y_train_raw)
        elif model_type == ModelType.RIDGE:
            model = self._train_ridge(X_train_scaled, y_train_raw)
        else:
            raise ValueError(f"Unsupported model type: {model_type}")

        self.models[model_type.value] = model

        y_pred = model.predict(X_test_scaled)
        oos_errors = (y_test.values - y_pred)
        self.oos_error_std[model_type.value] = float(np.std(oos_errors))

        metrics = {
            'rmse': float(np.sqrt(mean_squared_error(y_test, y_pred))),
            'mae': float(mean_absolute_error(y_test, y_pred)),
            'r2': float(r2_score(y_test, y_pred)),
            'directional_accuracy': float(self._directional_accuracy(y_test, y_pred)),
            'oos_error_std': float(self.oos_error_std[model_type.value]),
            'test_samples': len(y_test),
        }

        r2 = metrics.get('r2', -1)
        da = metrics.get('directional_accuracy', 0)
        if r2 < 0 or da < 0.5:
            quality = "poor"
        elif r2 < 0.3 or da < 0.55:
            quality = "mediocre"
        else:
            quality = "good"

        return {
            'model_type': model_type.value,
            'horizon': horizon.value,
            'metrics': metrics,
            'quality': quality,
            'feature_count': X_selected.shape[1],
            'features': list(X_selected.columns),
            'screening_report': screening_report,
        }

    def predict(self, df: pd.DataFrame, model_type: ModelType = ModelType.LIGHTGBM,
                horizon: PredictionHorizon = PredictionHorizon.SHORT,
                use_last_known_price: bool = True) -> PredictionResult:
        """预测"""
        if model_type.value not in self.models:
            raise ValueError(f"Model {model_type.value} not trained.")

        X = self.feature_engineer.prepare_features_for_prediction(df)
        if len(X) == 0:
            raise ValueError("No valid features for prediction")

        X_latest = X.iloc[-1:]
        scaler = self.scalers[model_type.value]
        X_scaled = scaler.transform(X_latest)
        model = self.models[model_type.value]
        predicted_return = float(model.predict(X_scaled)[0])

        current_price = float(df['close'].iloc[-1])
        predicted_price = current_price * (1 + predicted_return)
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
                'oos_error_std': self.oos_error_std.get(model_type.value),
            }
        )

    def train_tb(self, df: pd.DataFrame, model_type: ModelType = ModelType.LIGHTGBM,
                 test_size: float = 0.2) -> Dict[str, Any]:
        """Triple-Barrier 分类训练"""
        from backend.gold.data.labeling import TripleBarrierLabeler

        labeler = TripleBarrierLabeler()
        X, y = labeler.prepare_tb_features(df)
        if len(X) < 50:
            raise ValueError(f"Insufficient data for TB: {len(X)} samples")

        X_selected, screening_report = self.feature_engineer.select_features(X, y)
        split_idx = int(len(X_selected) * (1 - test_size))
        X_train, X_test = X_selected.iloc[:split_idx], X_selected.iloc[split_idx:]
        y_aligned = y.loc[X_selected.index]
        y_train, y_test = y_aligned.iloc[:split_idx], y_aligned.iloc[split_idx:]

        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        tb_key = f"tb_{model_type.value}"
        self.scalers[tb_key] = scaler

        if model_type in (ModelType.LIGHTGBM, ModelType.XGBOOST):
            model = self._train_tb_classifier(X_train_scaled, y_train, model_type)
        else:
            model = self._train_tb_ridge(X_train_scaled, y_train)

        self.models[tb_key] = model

        y_pred = model.predict(X_test_scaled)
        da = float(np.mean(y_pred * y_test.values > 0))
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
        return {
            'model_type': model_type.value,
            'mode': 'triple_barrier',
            'metrics': metrics,
            'feature_count': X_selected.shape[1],
            'features': list(X_selected.columns),
            'screening_report': screening_report,
        }

    def predict_tb(self, df: pd.DataFrame, model_type: ModelType = ModelType.LIGHTGBM) -> TripleBarrierResult:
        """TB 方向预测"""
        from backend.gold.data.labeling import TripleBarrierLabeler

        tb_key = f"tb_{model_type.value}"
        if tb_key not in self.models:
            raise ValueError(f"TB model {model_type.value} not trained.")

        labeler = TripleBarrierLabeler()
        X = self.feature_engineer.prepare_features_for_prediction(df)
        if len(X) == 0:
            raise ValueError("No valid features for TB prediction")

        X_latest = X.iloc[-1:]
        scaler = self.scalers[tb_key]
        X_scaled = scaler.transform(X_latest)
        model = self.models[tb_key]
        current_price = float(df['close'].iloc[-1])

        atr = labeler.compute_atr(df)
        atr_val = float(atr.iloc[-1]) if not atr.empty else 0
        tp_level = current_price + atr_val * labeler.tp_multiplier
        sl_level = current_price - atr_val * labeler.sl_multiplier

        if hasattr(model, 'predict_proba'):
            proba = model.predict_proba(X_scaled)[0]
            classes = model.classes_
            bull_idx = list(classes).index(1) if 1 in classes else 1
            direction_prob = float(proba[bull_idx])
            direction = 1 if direction_prob > 0.5 else -1
        else:
            raw_pred = float(model.predict(X_scaled)[0])
            direction = 1 if raw_pred > 0 else -1
            direction_prob = min(0.95, max(0.05, 0.5 + abs(raw_pred) * 0.3))

        confidence = abs(direction_prob - 0.5) * 2

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
            metadata={'mode': 'triple_barrier'},
        )

    def compute_factor_importance(self, model_type: ModelType = ModelType.LIGHTGBM) -> Dict[str, Any]:
        """计算因子重要性"""
        model = self.models.get(model_type.value)
        if model is None:
            return {'error': f'Model {model_type.value} not trained'}

        selected_features = self.feature_engineer.selected_features_ or []

        if model_type in (ModelType.LIGHTGBM, ModelType.XGBOOST) and hasattr(model, 'feature_importances_') and selected_features:
            importance = dict(zip(selected_features, model.feature_importances_))
            method = 'feature_importances_'
        elif model_type == ModelType.RIDGE and hasattr(model, 'coef_') and selected_features:
            importance = dict(zip(selected_features, np.abs(model.coef_)))
            method = 'ridge_abs_coef'
        else:
            importance = {}
            method = 'unknown'

        sorted_importance = dict(sorted(importance.items(), key=lambda x: -x[1]))
        return {
            'model_type': model_type.value,
            'method': method,
            'features': sorted_importance,
            'selected_count': len(selected_features),
        }

    def save_model(self, model_type: ModelType, filename: Optional[str] = None,
                   mode: str = "regression") -> str:
        """保存模型"""
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
            'saved_at': datetime.now().isoformat(),
        }
        with open(filepath, 'wb') as f:
            pickle.dump(model_data, f)
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
        selected = model_data.get('selected_features')
        if selected:
            self.feature_engineer.selected_features_ = selected

    def _calculate_confidence(self, model_type: ModelType, predicted_return: float) -> float:
        error_std = self.oos_error_std.get(model_type.value)
        if error_std is None or error_std < 1e-10:
            return 0.5
        signal_to_noise = abs(predicted_return) / error_std
        return min(0.95, max(0.3, 1 - np.exp(-signal_to_noise)))

    # ── 训练内部方法 ──

    def _train_lightgbm(self, X_train: np.ndarray, y_train: pd.Series):
        try:
            import lightgbm as lgb
            model = lgb.LGBMRegressor(
                n_estimators=200, max_depth=5, learning_rate=0.05,
                subsample=0.8, colsample_bytree=0.8,
                reg_alpha=0.1, reg_lambda=0.1, min_child_samples=20,
                random_state=42, verbose=-1)
            model.fit(X_train, y_train)
            return model
        except ImportError:
            return self._train_xgboost(X_train, y_train)

    def _train_xgboost(self, X_train: np.ndarray, y_train: pd.Series):
        try:
            import xgboost as xgb
            model = xgb.XGBRegressor(
                n_estimators=200, max_depth=5, learning_rate=0.05,
                subsample=0.8, colsample_bytree=0.8,
                reg_alpha=0.1, reg_lambda=0.1, random_state=42, verbosity=0)
            model.fit(X_train, y_train)
            return model
        except ImportError:
            return self._train_ridge(X_train, y_train)

    def _train_ridge(self, X_train: np.ndarray, y_train: pd.Series):
        return Ridge(alpha=1.0, random_state=42).fit(X_train, y_train)

    def _train_tb_classifier(self, X_train: np.ndarray, y_train: pd.Series, model_type: ModelType):
        y_mapped = y_train.map({-1: 0, 1: 1})
        if model_type == ModelType.LIGHTGBM:
            try:
                import lightgbm as lgb
                model = lgb.LGBMClassifier(
                    n_estimators=200, max_depth=5, learning_rate=0.05,
                    subsample=0.8, colsample_bytree=0.8,
                    reg_alpha=0.1, reg_lambda=0.1, min_child_samples=20,
                    random_state=42, verbose=-1)
                model.fit(X_train, y_mapped)
                return model
            except ImportError:
                pass
        try:
            import xgboost as xgb
            model = xgb.XGBClassifier(
                n_estimators=200, max_depth=5, learning_rate=0.05,
                subsample=0.8, colsample_bytree=0.8,
                reg_alpha=0.1, reg_lambda=0.1, random_state=42, verbosity=0)
            model.fit(X_train, y_mapped)
            return model
        except ImportError:
            return self._train_tb_ridge(X_train, y_train)

    def _train_tb_ridge(self, X_train: np.ndarray, y_train: pd.Series):
        return RidgeClassifier(alpha=1.0, random_state=42).fit(X_train, y_train)

    @staticmethod
    def _directional_accuracy(y_true: pd.Series, y_pred: np.ndarray) -> float:
        return float(np.mean(np.sign(y_true.values) == np.sign(y_pred)))
