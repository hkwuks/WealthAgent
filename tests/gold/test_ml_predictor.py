"""ML预测器测试 — 特征工程 + 训练 + 预测"""

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from datetime import datetime, timedelta
import pytest
import pandas as pd
import numpy as np

from gold.ml import FeatureEngineer, ModelType, PredictionHorizon, GoldPricePredictor


def make_price_df(n=200) -> pd.DataFrame:
    """生成模拟黄金价格DataFrame"""
    np.random.seed(42)
    dates = [(datetime(2024, 1, 1) + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(n)]
    price = 500.0
    prices = []
    for i in range(n):
        price *= (1 + np.random.normal(0, 0.008))
        prices.append(round(price, 2))

    df = pd.DataFrame({"date": dates, "close": prices})
    df["open"] = df["close"] * (1 + np.random.uniform(-0.005, 0.005, n))
    df["high"] = df[["open", "close"]].max(axis=1) * (1 + abs(np.random.normal(0, 0.003, n)))
    df["low"] = df[["open", "close"]].min(axis=1) * (1 - abs(np.random.normal(0, 0.003, n)))
    df["volume"] = np.random.randint(1000, 5000, n)

    # Add macro columns
    df["DXY_value"] = 100 + np.random.normal(0, 1, n).cumsum() * 0.1
    df["VIX_value"] = 15 + np.random.normal(0, 0.5, n).cumsum() * 0.05
    df["US10Y_value"] = 4.0 + np.random.normal(0, 0.1, n).cumsum() * 0.01
    df["TIPS_value"] = 1.5 + np.random.normal(0, 0.05, n).cumsum() * 0.01
    df["BREAKEVEN_value"] = df["US10Y_value"] - df["TIPS_value"]

    return df


class TestFeatureEngineer:
    def test_create_technical_features(self):
        fe = FeatureEngineer()
        df = make_price_df(100)
        result = fe.create_technical_features(df)
        expected_cols = [
            "returns", "log_returns", "momentum_5", "momentum_10", "momentum_21",
            "ma_ratio_20", "ma_ratio_60", "ma5_ma20_ratio",
            "atr_20", "atr_ratio", "hv_20", "hv_60", "parkinson_vol",
            "adx_14", "rsi_14", "rsi_7",
            "macd", "macd_signal", "macd_diff", "macd_histogram",
            "bb_position", "bb_width", "bb_%b",
            "obv", "obv_ma_ratio", "vwap_deviation", "volume_change", "volume_ma_ratio", "vpin",
            "close_position", "hl_spread_ratio", "overnight_gap",
        ]
        for col in expected_cols:
            assert col in result.columns, f"Missing feature: {col}"
        assert len(result.columns) >= 30

    def test_create_macro_features(self):
        fe = FeatureEngineer()
        df = make_price_df(100)
        result = fe.create_macro_features(df)
        assert "DXY_change" in result.columns
        assert "VIX_change" in result.columns
        assert "US10Y_change" in result.columns

    def test_prepare_features(self):
        fe = FeatureEngineer()
        df = make_price_df(200)
        X, y = fe.prepare_features(df, target_horizon=1)
        assert len(X) > 0
        assert len(y) > 0
        assert len(X) == len(y)

    def test_prepare_features_for_prediction_has_no_target(self):
        fe = FeatureEngineer()
        df = make_price_df(200)
        X = fe.prepare_features_for_prediction(df)
        assert len(X) > 0
        assert "target" not in X.columns


class TestGoldPricePredictor:
    def test_train_ridge(self):
        df = make_price_df(200)
        predictor = GoldPricePredictor()
        result = predictor.train(df, ModelType.RIDGE, PredictionHorizon.SHORT)
        assert result["model_type"] == "ridge"
        assert "metrics" in result
        assert result["metrics"]["r2"] is not None

    def test_train_and_predict_ridge(self):
        df = make_price_df(200)
        predictor = GoldPricePredictor()
        predictor.train(df, ModelType.RIDGE, PredictionHorizon.SHORT)
        result = predictor.predict(df, ModelType.RIDGE, PredictionHorizon.SHORT)
        assert result.predicted_change_percent is not None
        assert isinstance(result.predicted_change_percent, float)

    def test_insufficient_data_raises(self):
        df = make_price_df(30)
        predictor = GoldPricePredictor()
        with pytest.raises(ValueError, match="Insufficient"):
            predictor.train(df, ModelType.RIDGE, PredictionHorizon.SHORT)

    def test_predict_before_train_raises(self):
        df = make_price_df(200)
        predictor = GoldPricePredictor()
        with pytest.raises(ValueError):
            predictor.predict(df, ModelType.RIDGE, PredictionHorizon.SHORT)

    def test_feature_count(self):
        fe = FeatureEngineer()
        df = make_price_df(200)
        X, y = fe.prepare_features(df, target_horizon=1)
        X_selected, _ = fe.select_features(X, y)
        assert X_selected.shape[1] >= 10  # at least 10 features survive selection

    def test_oos_error_std_tracked(self):
        df = make_price_df(200)
        predictor = GoldPricePredictor()
        predictor.train(df, ModelType.RIDGE, PredictionHorizon.SHORT)
        assert "ridge" in predictor.oos_error_std
        assert predictor.oos_error_std["ridge"] > 0

    def test_ridge_coef_nonzero(self):
        """Ridge coef used as feature importance"""
        df = make_price_df(200)
        predictor = GoldPricePredictor()
        predictor.train(df, ModelType.RIDGE, PredictionHorizon.SHORT)
        model = predictor.models["ridge"]
        assert model.coef_ is not None
        assert np.any(model.coef_ != 0)
