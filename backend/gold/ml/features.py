"""
特征工程 — 技术指标 + 宏观因子
"""
import numpy as np
import pandas as pd
from typing import Any, Dict, List, Optional, Tuple, Sequence
from sklearn.preprocessing import StandardScaler
from loguru import logger


class FeatureEngineer:
    """特征工程"""

    def __init__(self):
        self.scaler = StandardScaler()
        self.selected_features_: Optional[List[str]] = None

    def create_technical_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """创建技术指标特征（35+ 因子）"""
        df = df.copy()
        df['returns'] = df['close'].pct_change()
        df['log_returns'] = np.log(df['close'] / df['close'].shift(1))
        for window in [5, 10, 21]:
            df[f'momentum_{window}'] = df['close'].pct_change(window)
        df['roc_accel'] = df['close'].pct_change(5) - df['close'].pct_change(10).shift(5)
        for window in [20, 60]:
            ma = df['close'].rolling(window=window).mean()
            df[f'ma_ratio_{window}'] = df['close'] / ma
        ma5 = df['close'].rolling(5).mean()
        ma20 = df['close'].rolling(20).mean()
        df['ma5_ma20_ratio'] = ma5 / ma20
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift(1)).abs()
        low_close = (df['low'] - df['close'].shift(1)).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr_20'] = tr.rolling(window=20).mean()
        df['atr_ratio'] = df['atr_20'] / df['close']
        df['hv_20'] = df['returns'].rolling(20).std() * np.sqrt(252)
        df['hv_60'] = df['returns'].rolling(60).std() * np.sqrt(252)
        df['hv_ratio'] = df['hv_20'] / (df['hv_60'] + 1e-10)
        df['parkinson_vol'] = np.sqrt(
            (1 / (4 * np.log(2))) * (np.log(df['high'] / df['low']) ** 2).rolling(20).mean()
        )
        atr14 = tr.rolling(14).mean()
        plus_dm = (df['high'].diff() > df['low'].diff().abs()) * df['high'].diff().clip(0)
        minus_dm = (df['low'].diff().abs() > df['high'].diff()) * df['low'].diff().abs().clip(0)
        plus_di = 100 * plus_dm.rolling(14).mean() / (atr14 + 1e-10)
        minus_di = 100 * minus_dm.rolling(14).mean() / (atr14 + 1e-10)
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-10)
        df['adx_14'] = dx.rolling(14).mean()
        df['rsi_14'] = self._calculate_rsi(df['close'], 14)
        df['rsi_7'] = self._calculate_rsi(df['close'], 7)
        df['macd'], df['macd_signal'], _ = self._calculate_macd(df['close'])
        df['macd_diff'] = df['macd'] - df['macd_signal']
        df['macd_histogram'] = df['macd_diff'] - df['macd_diff'].rolling(9).mean()
        _, _, bb_lower = self._calculate_bollinger(df['close'])
        bb_upper, bb_middle, _ = self._calculate_bollinger(df['close'])
        df['bb_position'] = (df['close'] - bb_lower) / (bb_upper - bb_lower + 1e-10)
        df['bb_width'] = (bb_upper - bb_lower) / (bb_middle + 1e-10)
        df['bb_%b'] = (df['close'] - bb_lower) / (bb_upper - bb_lower + 1e-10)
        if 'volume' in df.columns:
            close_diff = df['close'].diff()
            direction = np.sign(close_diff)
            df['obv'] = (direction * df['volume']).fillna(0).cumsum()
            df['obv_ma_ratio'] = df['obv'] / (df['obv'].rolling(20).mean() + 1e-10)
            vwap = (df['volume'] * df['close']).rolling(20).sum() / (df['volume'].rolling(20).sum() + 1e-10)
            df['vwap_deviation'] = (df['close'] - vwap) / (vwap + 1e-10)
            df['volume_change'] = df['volume'].pct_change()
            df['volume_ma_ratio'] = df['volume'] / (df['volume'].rolling(5).mean() + 1e-10)
            signed_vol = direction * df['volume']
            df['vpin'] = signed_vol.rolling(20).sum() / (df['volume'].rolling(20).sum() + 1e-10)
        df['close_position'] = (df['close'] - df['low']) / (df['high'] - df['low'] + 1e-10)
        df['hl_spread_ratio'] = (df['high'] - df['low']) / (df['close'] + 1e-10)
        df['overnight_gap'] = df['open'] / df['close'].shift(1) - 1
        return df

    def create_macro_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """创建宏观特征"""
        df = df.copy()
        if 'DXY_value' in df.columns:
            df['DXY_change'] = df['DXY_value'].pct_change()
            df['DXY_ma_5'] = df['DXY_value'].rolling(5).mean()
            df['gold_dxy_ratio'] = df['close'] / df['DXY_value']
        if 'VIX_value' in df.columns:
            df['VIX_change'] = df['VIX_value'].pct_change()
            df['VIX_ma_5'] = df['VIX_value'].rolling(5).mean()
        if 'US10Y_value' in df.columns:
            df['US10Y_change'] = df['US10Y_value'].pct_change()
        if 'TIPS_value' in df.columns:
            df['TIPS_change'] = df['TIPS_value'].pct_change()
            df['TIPS_level'] = df['TIPS_value']
            if 'US10Y_value' in df.columns:
                df['real_rate_proxy'] = df['US10Y_value'] - df['TIPS_value']
        if 'BREAKEVEN_value' in df.columns:
            df['BREAKEVEN_change'] = df['BREAKEVEN_value'].pct_change()
            df['BREAKEVEN_level'] = df['BREAKEVEN_value']
        elif 'US10Y_value' in df.columns and 'TIPS_value' in df.columns:
            df['BREAKEVEN_level'] = df['US10Y_value'] - df['TIPS_value']
            df['BREAKEVEN_change'] = df['BREAKEVEN_level'].pct_change()
        if 'spec_net' in df.columns:
            df['spec_net_change'] = df['spec_net'].pct_change()
            df['spec_net_ma_4'] = df['spec_net'].rolling(4).mean()
        if 'spec_net_ratio' in df.columns:
            df['spec_ratio_change'] = df['spec_net_ratio'].diff()
        return df

    def create_lag_features(self, df: pd.DataFrame, lags: Optional[List[int]] = None) -> pd.DataFrame:
        """创建滞后特征"""
        if lags is None:
            lags = [1, 2, 5]
        df = df.copy()
        for lag in lags:
            if 'returns' in df.columns:
                df[f'returns_lag_{lag}'] = df['returns'].shift(lag)
        return df

    def prepare_features(self, df: pd.DataFrame, target_horizon: int = 1) -> Tuple[pd.DataFrame, pd.Series]:
        """准备特征和标签（用于训练）"""
        df = self.create_technical_features(df)
        df = self.create_macro_features(df)
        df = self.create_lag_features(df)
        df['target'] = df['close'].shift(-target_horizon) / df['close'] - 1
        feature_cols = [c for c in df.columns if c not in [
            'target', 'date', 'open', 'high', 'low', 'close', 'volume',
            'asset_code', 'asset_type', 'source', 'amount', 'change',
            'ma_5', 'ma_10', 'ma_20', 'ma_60',
            'volatility_5', 'volatility_20',
            'macd_hist',
            'bb_upper', 'bb_middle', 'bb_lower',
            'high_low_range',
        ]]
        df_clean = df[feature_cols + ['target']].replace([np.inf, -np.inf], np.nan).dropna()
        X = df_clean[feature_cols]
        y = df_clean['target']
        return X, y

    def prepare_features_for_prediction(self, df: pd.DataFrame) -> pd.DataFrame:
        """准备特征用于预测"""
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
        X = df[feature_cols].replace([np.inf, -np.inf], np.nan).dropna()
        if self.selected_features_ is not None:
            available = [f for f in self.selected_features_ if f in X.columns]
            if available:
                X = X[available]
        return X

    def select_features(self, X: pd.DataFrame, y: pd.Series,
                        mi_threshold: float = 0.01,
                        corr_threshold: float = 0.8,
                        shap_model=None) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """因子筛选：互信息 + 相关性去冗余 + SHAP验证"""
        report = {
            'original_features': list(X.columns),
            'original_count': len(X.columns),
            'steps': {}
        }
        mi_scores = self._compute_mi_scores(X, y)
        mi_selected = [col for col, score in mi_scores.items() if score >= mi_threshold]
        report['steps']['mi_filter'] = {
            'threshold': mi_threshold,
            'removed': [col for col in X.columns if col not in mi_selected],
            'removed_count': len(X.columns) - len(mi_selected),
            'scores': {k: round(v, 4) for k, v in sorted(mi_scores.items(), key=lambda x: -x[1])}
        }
        X_mi = X[mi_selected]
        X_corr, corr_removed = self._remove_correlated_features(X_mi, mi_scores, corr_threshold)
        report['steps']['correlation_filter'] = {
            'threshold': corr_threshold,
            'removed': corr_removed,
            'removed_count': len(corr_removed)
        }
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
        return X_final, report

    def _compute_mi_scores(self, X: pd.DataFrame, y: pd.Series) -> Dict[str, float]:
        """计算各特征与目标变量的互信息"""
        from sklearn.feature_selection import mutual_info_regression
        X_clean = X.fillna(0)
        mi = mutual_info_regression(X_clean, y, random_state=42, n_neighbors=5)
        return dict(zip(X.columns, mi))

    def _remove_correlated_features(self, X: pd.DataFrame, mi_scores: Dict[str, float],
                                     threshold: float = 0.8) -> Tuple[pd.DataFrame, List[str]]:
        """去除高相关冗余特征，保留MI更高的"""
        corr_matrix = X.corr().abs()
        upper = corr_matrix.where(np.triu(np.ones(corr_matrix.shape), k=1).astype(bool))
        removed = []
        for col in upper.columns:
            correlated = upper.index[upper[col] > threshold].tolist()
            for corr_col in correlated:
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
        try:
            import shap
            explainer = shap.TreeExplainer(model)
            shap_values = explainer.shap_values(X.iloc[:200])
            mean_abs_shap = np.abs(shap_values).mean(axis=0)
            return dict(zip(X.columns, mean_abs_shap))
        except ImportError:
            if hasattr(model, 'feature_importances_'):
                return dict(zip(X.columns, model.feature_importances_))
            return {col: 1.0 / len(X.columns) for col in X.columns}
        except Exception:
            if hasattr(model, 'feature_importances_'):
                return dict(zip(X.columns, model.feature_importances_))
            return {col: 1.0 / len(X.columns) for col in X.columns}

    @staticmethod
    def _calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    @staticmethod
    def _calculate_macd(prices: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
        ema_fast = prices.ewm(span=fast).mean()
        ema_slow = prices.ewm(span=slow).mean()
        macd = ema_fast - ema_slow
        macd_signal = macd.ewm(span=signal).mean()
        macd_hist = macd - macd_signal
        return macd, macd_signal, macd_hist

    @staticmethod
    def _calculate_bollinger(prices: pd.Series, window: int = 20, num_std: int = 2) -> Tuple[pd.Series, pd.Series, pd.Series]:
        middle = prices.rolling(window=window).mean()
        std = prices.rolling(window=window).std()
        upper = middle + num_std * std
        lower = middle - num_std * std
        return upper, middle, lower
