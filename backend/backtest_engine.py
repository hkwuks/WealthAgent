"""
黄金价格预测模型回测引擎
使用滚动窗口回测（Walk-Forward Analysis）
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Any
from datetime import datetime
from loguru import logger

from backend.gold_prediction import GoldPricePredictor, ModelType, PredictionHorizon


class BacktestEngine:
    """回测引擎"""

    def __init__(self, train_window: int = 252, test_window: int = 20):
        """
        Args:
            train_window: 训练窗口天数（默认1年252交易日）
            test_window: 测试窗口天数（默认20个交易日）
        """
        self.train_window = train_window
        self.test_window = test_window

    def run_backtest(
        self,
        df: pd.DataFrame,
        model_types: List[ModelType],
        horizon: PredictionHorizon = PredictionHorizon.SHORT
    ) -> Dict[str, Any]:
        """
        执行滚动窗口回测

        Returns:
            回测结果字典
        """
        df = df.sort_values("date").reset_index(drop=True)

        results = {}
        for model_type in model_types:
            logger.info(f"回测模型: {model_type.value}")
            result = self._backtest_single_model(df, model_type, horizon)
            results[model_type.value] = result

        # 基准（买入持有）
        results["benchmark"] = self._calculate_benchmark(df, horizon)

        return results

    def _backtest_single_model(
        self,
        df: pd.DataFrame,
        model_type: ModelType,
        horizon: PredictionHorizon
    ) -> Dict[str, Any]:
        """回测单个模型"""
        equity_curve = [1.0]  # 从1开始
        predictions_log = []
        monthly_returns = {}

        i = self.train_window
        while i + horizon.value < len(df):  # 改为 < 避免越界
            # 训练数据：严格使用 [i-train_window, i-1] 的数据
            # 确保不包含第 i 天的信息
            train_df = df.iloc[i - self.train_window:i].copy()

            # 预测基准价格：使用第 i-1 天的收盘价（最后一个已知价格）
            prediction_base_price = train_df["close"].iloc[-1]

            # 测试窗口实际价格
            # test_start_price 应该是第 i 天的开盘价或第 i-1 天的收盘价
            test_start_price = prediction_base_price  # 使用已知价格作为交易基准
            test_end_idx = i + horizon.value
            test_end_price = df["close"].iloc[test_end_idx]

            # 实际收益率（从预测基准到测试结束）
            actual_return = (test_end_price - test_start_price) / test_start_price

            predictor = GoldPricePredictor()
            try:
                predictor.train(train_df, model_type, horizon)

                # 使用修复后的 predict 方法，明确指定使用最后已知价格
                result = predictor.predict(
                    train_df, model_type, horizon, use_last_known_price=True
                )

                # 预测收益率（predicted_change_percent 已经是百分比）
                predicted_return = result.predicted_change_percent / 100

                # 验证预测基准价格一致
                assert abs(result.current_price - prediction_base_price) < 0.01, \
                    f"Price mismatch: {result.current_price} vs {prediction_base_price}"

                # 模拟交易（根据预测方向做多，但只在预测显著时交易）
                # 注意：简化处理，只做多不做空，更符合黄金投资实际
                MIN_PREDICTION_THRESHOLD = 0.001  # 0.1% 最小阈值
                TRANSACTION_COST = 0.001  # 0.1% 交易成本

                if predicted_return > MIN_PREDICTION_THRESHOLD:
                    # 做多，扣除交易成本
                    ret = actual_return - TRANSACTION_COST
                elif predicted_return < -MIN_PREDICTION_THRESHOLD:
                    # 预测下跌，空仓观望（不做空）
                    ret = 0
                else:
                    # 预测不显著，不交易
                    ret = 0

                # 更新权益曲线
                equity_curve.append(equity_curve[-1] * (1 + ret))

                # 记录月度收益
                date = df["date"].iloc[i]
                if isinstance(date, str) and len(date) >= 7:
                    year_month = date[:7]
                else:
                    year_month = str(date)[:7]
                if year_month not in monthly_returns:
                    monthly_returns[year_month] = []
                monthly_returns[year_month].append(ret)

                predictions_log.append({
                    "date": date,
                    "prediction_base_price": prediction_base_price,
                    "test_end_price": test_end_price,
                    "predicted": predicted_return,
                    "actual": actual_return,
                    "correct_direction": (predicted_return * actual_return) > 0,
                    "traded": predicted_return > MIN_PREDICTION_THRESHOLD
                })

            except Exception as e:
                logger.warning(f"预测失败 at index {i}: {e}")
                # 预测失败时保持仓位不变
                equity_curve.append(equity_curve[-1])

            i += horizon.value  # 使用 horizon 作为步长

        # 计算指标（显式传递 horizon 以计算年化收益）
        return self._calculate_metrics(equity_curve, predictions_log, monthly_returns, horizon)

    def _calculate_metrics(self, equity_curve: List[float], predictions_log: List[Dict], monthly_returns: Dict, horizon: PredictionHorizon = PredictionHorizon.SHORT) -> Dict[str, Any]:
        """计算回测指标"""
        equity_curve = np.array(equity_curve)
        returns = np.diff(equity_curve) / equity_curve[:-1]

        total_return = equity_curve[-1] - 1
        periods = len(equity_curve) - 1

        # 计算年化收益（用实际 horizon 计算每年周期数）
        periods_per_year = 252 / horizon.value if horizon else 12.6
        annualized_return = (1 + total_return) ** (periods_per_year / max(periods, 1)) - 1 if periods > 0 else 0

        # 最大回撤
        peak = np.maximum.accumulate(equity_curve)
        drawdown = (equity_curve - peak) / peak
        max_drawdown = np.min(drawdown)

        # 波动率（年化）
        volatility = np.std(returns) * np.sqrt(periods_per_year) if len(returns) > 0 else 0

        # 夏普比率（假设无风险利率为3%）
        risk_free = 0.03
        sharpe_ratio = (annualized_return - risk_free) / volatility if volatility > 0 else 0

        # 胜率
        correct_count = sum(1 for p in predictions_log if p["correct_direction"])
        win_rate = correct_count / len(predictions_log) if predictions_log else 0

        # 方向准确率
        da = correct_count / len(predictions_log) if predictions_log else 0

        # RMSE, MAE
        if predictions_log:
            pred_arr = np.array([p["predicted"] for p in predictions_log])
            actual_arr = np.array([p["actual"] for p in predictions_log])
            rmse = np.sqrt(np.mean((pred_arr - actual_arr) ** 2))
            mae = np.mean(np.abs(pred_arr - actual_arr))
        else:
            rmse = mae = 0

        # 月度收益
        monthly_avg = {
            month: round(np.mean(rets) * 100, 2)
            for month, rets in monthly_returns.items()
        }

        return {
            "total_return": round(total_return * 100, 2),
            "annualized_return": round(annualized_return * 100, 2),
            "max_drawdown": round(max_drawdown * 100, 2),
            "volatility": round(volatility * 100, 2),
            "sharpe_ratio": round(sharpe_ratio, 2),
            "win_rate": round(win_rate * 100, 2),
            "directional_accuracy": round(da * 100, 2),
            "rmse": round(rmse, 6),
            "mae": round(mae, 6),
            "trade_count": len(predictions_log),
            "equity_curve": [round(v, 4) for v in equity_curve.tolist()],
            "monthly_returns": monthly_avg
        }

    def _calculate_benchmark(self, df: pd.DataFrame, horizon: PredictionHorizon = PredictionHorizon.SHORT) -> Dict[str, Any]:
        """计算买入持有基准"""
        prices = df["close"].values
        start_idx = self.train_window

        if start_idx >= len(prices):
            return {"total_return": 0, "annualized_return": 0, "max_drawdown": 0, "sharpe_ratio": 0}

        # 构建equity curve（使用与预测模型相同的逻辑）
        # 基准策略：从 train_window-1 的价格开始持有
        # 这样与预测模型的基准价格一致（都是最后一个训练日的收盘价）
        equity_curve = [1.0]
        TRANSACTION_COST = 0.001  # 与策略相同的交易成本

        i = start_idx
        while i + horizon.value < len(prices):
            # 使用与预测模型相同的基准价格（第 i-1 天的收盘价）
            # 但基准策略在开始时买入，所以使用第 start_idx-1 天作为成本基准
            if i == start_idx:
                # 第一次交易，扣除买入成本
                ret = (prices[i + horizon.value] - prices[i - 1]) / prices[i - 1] - TRANSACTION_COST
            else:
                # 后续持有
                ret = (prices[i + horizon.value] - prices[i]) / prices[i]

            equity_curve.append(equity_curve[-1] * (1 + ret))
            i += horizon.value

        metrics = self._calculate_metrics(equity_curve, [], {}, horizon)

        # 买入持有策略不适用于预测相关指标
        metrics.update({
            "win_rate": None,
            "directional_accuracy": None,
            "rmse": None,
            "mae": None,
            "trade_count": 1,  # 一次买入持有
            "note": "买入持有策略 - 预测指标不适用"
        })

        return metrics
