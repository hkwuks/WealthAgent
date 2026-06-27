"""
LSTM 序列预测模型 — 可选扩展

依赖: torch, numpy

使用:
    from gold_prediction import GoldPricePredictorLSTM
    predictor = GoldPricePredictorLSTM(input_dim=30, hidden_dim=64, num_layers=2)
    predictor.train(df)
    result = predictor.predict(df)

架构: 2层 LSTM(64) → Dropout(0.2) → Dense(1)
"""

import numpy as np
import pandas as pd
from typing import Optional, Dict, Any
from datetime import datetime
from loguru import logger


class GoldPricePredictorLSTM:
    """
    LSTM 黄金价格预测器

    与 GoldPricePredictor 共享 FeatureEngineer，输出兼容 PredictionResult。
    未安装 torch 时抛出 ImportError。
    """

    def __init__(self, input_dim: int = 30, hidden_dim: int = 64,
                 num_layers: int = 2, dropout: float = 0.2,
                 sequence_length: int = 60, learning_rate: float = 0.001,
                 model_dir: str = "data/backend/models"):
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers
        self.dropout = dropout
        self.sequence_length = sequence_length
        self.learning_rate = learning_rate
        self.model_dir = model_dir
        self.model = None
        self.scaler = None
        self._is_trained = False

        # 延时导入 torch
        try:
            import torch
            self._torch = torch
        except ImportError:
            raise ImportError(
                "PyTorch 未安装，LSTM 预测不可用。安装方式: pip install torch"
            )

    def build_model(self):
        """构建 LSTM 模型"""
        import torch.nn as nn

        class LSTMPredictor(nn.Module):
            def __init__(self, input_dim, hidden_dim, num_layers, dropout):
                super().__init__()
                self.lstm = nn.LSTM(
                    input_dim, hidden_dim, num_layers,
                    batch_first=True, dropout=dropout if num_layers > 1 else 0
                )
                self.dropout = nn.Dropout(dropout)
                self.fc = nn.Linear(hidden_dim, 1)

            def forward(self, x):
                out, _ = self.lstm(x)
                out = self.dropout(out[:, -1, :])
                return self.fc(out).squeeze()

        self.model = LSTMPredictor(
            self.input_dim, self.hidden_dim,
            self.num_layers, self.dropout
        )

    def prepare_sequences(self, df: pd.DataFrame) -> tuple:
        """
        将 DataFrame 转为 LSTM 序列 (samples, seq_len, features)

        Args:
            df: 含特征的 DataFrame

        Returns:
            (X_seq, y) 用于训练
        """
        from sklearn.preprocessing import StandardScaler

        # 排除非特征列
        feature_cols = [c for c in df.columns if c not in (
            'target', 'date', 'open', 'high', 'low', 'close', 'volume'
        )]
        data = df[feature_cols].values

        scaler = StandardScaler()
        data_scaled = scaler.fit_transform(data)
        self.scaler = scaler

        X_seq, y = [], []
        for i in range(len(data_scaled) - self.sequence_length):
            X_seq.append(data_scaled[i:i + self.sequence_length])
            target = df['close'].iloc[i + self.sequence_length] / df['close'].iloc[i + self.sequence_length - 1] - 1
            y.append(target)

        return np.array(X_seq), np.array(y)

    def train(self, df: pd.DataFrame, epochs: int = 50, batch_size: int = 32) -> Dict[str, Any]:
        """训练 LSTM 模型"""
        import torch
        import torch.nn as nn
        import torch.optim as optim

        X_seq, y = self.prepare_sequences(df)
        if len(X_seq) < 10:
            raise ValueError(f"序列样本不足: {len(X_seq)} (最少 10)")

        self.build_model()
        criterion = nn.MSELoss()
        optimizer = optim.Adam(self.model.parameters(), lr=self.learning_rate)

        dataset = torch.utils.data.TensorDataset(
            torch.FloatTensor(X_seq), torch.FloatTensor(y)
        )
        loader = torch.utils.data.DataLoader(dataset, batch_size=batch_size, shuffle=True)

        self.model.train()
        for epoch in range(epochs):
            epoch_loss = 0
            for batch_X, batch_y in loader:
                optimizer.zero_grad()
                output = self.model(batch_X)
                loss = criterion(output, batch_y)
                loss.backward()
                optimizer.step()
                epoch_loss += loss.item()

            if (epoch + 1) % 10 == 0:
                logger.debug(f"LSTM Epoch {epoch+1}/{epochs}: loss={epoch_loss/len(loader):.6f}")

        self._is_trained = True
        logger.info(f"LSTM 训练完成: {len(X_seq)} 序列, {self.input_dim} 特征")
        return {"status": "trained", "samples": len(X_seq), "epochs": epochs}

    def predict(self, df: pd.DataFrame) -> Optional[float]:
        """预测下一个周期涨跌幅"""
        import torch
        if not self._is_trained or self.model is None:
            raise ValueError("模型未训练，请先调用 train()")

        feature_cols = [c for c in df.columns if c not in (
            'target', 'date', 'open', 'high', 'low', 'close', 'volume'
        )]
        data = df[feature_cols].values

        if self.scaler:
            data_scaled = self.scaler.transform(data)
        else:
            from sklearn.preprocessing import StandardScaler
            data_scaled = StandardScaler().fit_transform(data)

        if len(data_scaled) < self.sequence_length:
            raise ValueError(f"数据不足 {self.sequence_length} 条序列")

        seq = data_scaled[-self.sequence_length:].reshape(1, self.sequence_length, -1)
        seq_tensor = torch.FloatTensor(seq)

        self.model.eval()
        with torch.no_grad():
            pred = self.model(seq_tensor).item()

        return pred * 100  # 转为百分比
