"""
黄金价格预测模型回测引擎
使用滚动窗口回测（Walk-Forward Analysis）+ Purging + Embargo
支持 CPCV（Combinatorial Purged Cross-Validation）
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, field
from itertools import combinations
from loguru import logger

from backend.gold_prediction import GoldPricePredictor, ModelType, PredictionHorizon

EMBARGO_DAYS = 20  # 训练集尾部去除天数，防止MA/RSI等滞后特征泄露
PURGE_DAYS = 1     # 测试集头部去除天数，防止标签重叠（=预测horizon）


@dataclass
class CostModel:
    """动态交易成本模型"""
    commission_rate: float = 0.0005       # 0.05% 佣金
    slippage_base: float = 0.0003         # 0.03% 基础滑点
    slippage_vol_multiplier: float = 0.002  # 滑点随波动率增加（年化vol → bps）
    roll_cost: float = 0.0005             # 展期成本（期货）
    margin_opportunity: float = 0.0001    # 保证金机会成本

    def round_trip_cost(self, volatility: float = 0.0) -> float:
        """
        计算单边交易成本（含动态滑点）

        Args:
            volatility: 近期波动率（年化），用于动态调整滑点

        Returns:
            单边交易成本比例
        """
        slippage = self.slippage_base + self.slippage_vol_multiplier * volatility
        return self.commission_rate + slippage

    def full_cycle_cost(self, volatility: float = 0.0) -> float:
        """完整交易周期成本（开仓+平仓+期货相关）"""
        return 2 * self.round_trip_cost(volatility) + self.roll_cost + self.margin_opportunity


class BacktestEngine:
    """回测引擎（带Purging + Embargo的Walk-Forward）"""

    def __init__(self, train_window: int = 252, test_window: int = 20,
                 embargo_days: int = EMBARGO_DAYS, purge_days: int = PURGE_DAYS,
                 cost_model: CostModel = None):
        """
        Args:
            train_window: 训练窗口天数
            test_window: 测试窗口天数
            embargo_days: 训练集尾部去除天数（防滞后特征泄露）
            purge_days: 测试集头部去除天数（防标签重叠）
            cost_model: 交易成本模型，None则使用默认
        """
        self.train_window = train_window
        self.test_window = test_window
        self.embargo_days = embargo_days
        self.purge_days = purge_days
        self.cost_model = cost_model or CostModel()

    def run_backtest(
        self,
        df: pd.DataFrame,
        model_types: List[ModelType],
        horizon: PredictionHorizon = PredictionHorizon.SHORT
    ) -> Dict[str, Any]:
        """
        执行滚动窗口回测

        数据时间线:
        |----Train----|--Embargo--|--Purge--|--Test--|
                      ↑ 去掉尾部   ↑ 去掉头部
                      (MA等滞后     (标签可能
                       特征泄露)    重叠)
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
        """回测单个模型（带Purging + Embargo）"""
        equity_curve = [1.0]
        predictions_log = []
        monthly_returns = {}

        i = self.train_window
        while i + self.embargo_days + self.purge_days + horizon.value < len(df):
            # 训练数据：[i-train_window, i-1]，去除尾部embargo天
            # Embargo: 去除训练集最后embargo_days天，防止MA/RSI等滞后特征泄露到测试期
            train_end = i - self.embargo_days
            if train_end <= i - self.train_window:
                # embargo比训练窗口还大，跳过
                i += self.test_window
                continue

            train_df = df.iloc[i - self.train_window:train_end].copy()

            # 测试数据：从 i + purge_days 开始
            # Purging: 去除测试集头部purge_days天，防止标签重叠
            test_start = i + self.purge_days
            test_end = test_start + horizon.value

            if test_end >= len(df):
                break

            # 预测基准价格：使用test_start前一日的收盘价（即训练集最后一个有效日）
            prediction_base_price = df["close"].iloc[test_start - 1]
            test_end_price = df["close"].iloc[test_end]

            # 实际收益率（持有 horizon 天的收益率）
            actual_return = (test_end_price - prediction_base_price) / prediction_base_price

            predictor = GoldPricePredictor()
            try:
                predictor.train(train_df, model_type, horizon)

                # 预测：传入到 test_start-1 为止的数据（即训练集+已知的最新数据）
                predict_df = df.iloc[:test_start].copy()
                result = predictor.predict(
                    predict_df, model_type, horizon, use_last_known_price=True
                )

                predicted_return = result.predicted_change_percent / 100

                # 模拟交易（只做多不做空）
                MIN_PREDICTION_THRESHOLD = 0.001

                # 动态交易成本：基于近期波动率
                recent_returns = train_df['close'].pct_change().dropna()
                recent_vol = recent_returns.tail(20).std() * np.sqrt(252) if len(recent_returns) >= 20 else 0.15
                single_cost = self.cost_model.round_trip_cost(recent_vol)

                if predicted_return > MIN_PREDICTION_THRESHOLD:
                    ret = actual_return - single_cost
                elif predicted_return < -MIN_PREDICTION_THRESHOLD:
                    ret = 0  # 空仓
                else:
                    ret = 0  # 不交易

                equity_curve.append(equity_curve[-1] * (1 + ret))

                date = df["date"].iloc[test_start]
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
                equity_curve.append(equity_curve[-1])

            i += self.test_window

        return self._calculate_metrics(equity_curve, predictions_log, monthly_returns, horizon)

    def _calculate_metrics(self, equity_curve: List[float], predictions_log: List[Dict],
                           monthly_returns: Dict, horizon: PredictionHorizon = PredictionHorizon.SHORT) -> Dict[str, Any]:
        """计算回测指标"""
        equity_curve = np.array(equity_curve)
        returns = np.diff(equity_curve) / equity_curve[:-1]

        total_return = equity_curve[-1] - 1
        periods = len(equity_curve) - 1

        # 年化收益：使用对数收益率年化，避免极端值
        # total_return = (1 + r1)(1 + r2)...(1 + rn) - 1
        # 年化 = exp(ln(1 + total_return) * periods_per_year / periods) - 1
        periods_per_year = 252 / horizon.value if horizon else 12.6
        if periods > 0 and total_return > -1:
            log_total = np.log(1 + total_return)
            annualized_return = np.exp(log_total * periods_per_year / periods) - 1
        else:
            annualized_return = 0

        # 最大回撤
        peak = np.maximum.accumulate(equity_curve)
        drawdown = (equity_curve - peak) / peak
        max_drawdown = np.min(drawdown)

        # 波动率（年化）
        volatility = np.std(returns) * np.sqrt(periods_per_year) if len(returns) > 0 else 0

        # 夏普比率
        risk_free = 0.03
        sharpe_ratio = (annualized_return - risk_free) / volatility if volatility > 0 else 0

        # Sortino Ratio（下行风险调整）
        downside_returns = returns[returns < 0]
        downside_std = np.std(downside_returns) * np.sqrt(periods_per_year) if len(downside_returns) > 0 else volatility
        sortino_ratio = (annualized_return - risk_free) / downside_std if downside_std > 0 else 0

        # Calmar Ratio
        calmar_ratio = annualized_return / abs(max_drawdown) if max_drawdown != 0 else 0

        # 胜率 & 方向准确率
        correct_count = sum(1 for p in predictions_log if p["correct_direction"])
        da = correct_count / len(predictions_log) if predictions_log else 0

        # 盈利交易占比
        traded = [p for p in predictions_log if p.get("traded")]
        win_count = sum(1 for p in traded if p["actual"] > 0)
        win_rate = win_count / len(traded) if traded else 0

        # RMSE, MAE
        if predictions_log:
            pred_arr = np.array([p["predicted"] for p in predictions_log])
            actual_arr = np.array([p["actual"] for p in predictions_log])
            rmse = np.sqrt(np.mean((pred_arr - actual_arr) ** 2))
            mae = np.mean(np.abs(pred_arr - actual_arr))
        else:
            rmse = mae = 0

        # Information Ratio（相对基准的超额收益/跟踪误差）
        benchmark_returns = np.full_like(returns, np.mean(returns)) if len(returns) > 0 else returns
        tracking_error = np.std(returns - benchmark_returns) * np.sqrt(periods_per_year) if len(returns) > 1 else 0
        information_ratio = (annualized_return - risk_free) / tracking_error if tracking_error > 0 else 0

        # Profit Factor（盈利总和 / 亏损总和）
        trade_returns = [p["actual"] for p in traded] if traded else []
        gross_profit = sum(r for r in trade_returns if r > 0)
        gross_loss = abs(sum(r for r in trade_returns if r < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf') if gross_profit > 0 else 0

        # Max Consecutive Losses
        max_consec_loss = 0
        current_streak = 0
        for r in trade_returns:
            if r < 0:
                current_streak += 1
                max_consec_loss = max(max_consec_loss, current_streak)
            else:
                current_streak = 0

        # Average Holding Period Return
        avg_holding_return = np.mean(trade_returns) * 100 if trade_returns else 0

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
            "sortino_ratio": round(sortino_ratio, 2),
            "calmar_ratio": round(calmar_ratio, 2),
            "win_rate": round(win_rate * 100, 2),
            "directional_accuracy": round(da * 100, 2),
            "information_ratio": round(information_ratio, 2),
            "profit_factor": round(profit_factor, 2) if profit_factor != float('inf') else None,
            "max_consecutive_losses": max_consec_loss,
            "avg_holding_return": round(avg_holding_return, 4),
            "rmse": round(rmse, 6),
            "mae": round(mae, 6),
            "trade_count": len(predictions_log),
            "embargo_days": self.embargo_days,
            "purge_days": self.purge_days,
            "cost_model": {
                "commission_rate": self.cost_model.commission_rate,
                "slippage_base": self.cost_model.slippage_base,
                "slippage_vol_multiplier": self.cost_model.slippage_vol_multiplier,
                "typical_single_cost": self.cost_model.round_trip_cost()
            },
            "equity_curve": [round(v, 4) for v in equity_curve.tolist()],
            "monthly_returns": monthly_avg
        }

    def _calculate_benchmark(self, df: pd.DataFrame, horizon: PredictionHorizon = PredictionHorizon.SHORT) -> Dict[str, Any]:
        """计算买入持有基准"""
        prices = df["close"].values
        start_idx = self.train_window

        if start_idx >= len(prices):
            return {"total_return": 0, "annualized_return": 0, "max_drawdown": 0, "sharpe_ratio": 0}

        equity_curve = [1.0]
        single_cost = self.cost_model.round_trip_cost()

        i = start_idx
        while i + horizon.value < len(prices):
            if i == start_idx:
                ret = (prices[i + horizon.value] - prices[i - 1]) / prices[i - 1] - single_cost
            else:
                ret = (prices[i + horizon.value] - prices[i]) / prices[i]

            equity_curve.append(equity_curve[-1] * (1 + ret))
            i += horizon.value

        metrics = self._calculate_metrics(equity_curve, [], {}, horizon)

        metrics.update({
            "win_rate": None,
            "directional_accuracy": None,
            "information_ratio": None,
            "profit_factor": None,
            "max_consecutive_losses": None,
            "avg_holding_return": None,
            "rmse": None,
            "mae": None,
            "trade_count": 1,
            "note": "买入持有策略 - 预测指标不适用"
        })

        return metrics


class CPCVEngine:
    """
    Combinatorial Purged Cross-Validation 回测引擎

    将数据分成 N 个连续组，枚举所有 C(N, k) 组合（k 组测试，N-k 组训练），
    每条路径独立训练+预测，最后聚合指标。

    参考：López de Prado, "Advances in Financial Machine Learning", Ch.12
    """

    def __init__(
        self,
        n_groups: int = 6,
        k_test: int = 2,
        embargo_days: int = EMBARGO_DAYS,
        purge_days: int = PURGE_DAYS,
        cost_model: CostModel = None,
    ):
        """
        Args:
            n_groups: 数据分组数（默认6）
            k_test: 测试组数（默认2，C(6,2)=15条路径）
            embargo_days: 训练集尾部去除天数
            purge_days: 测试集头部去除天数
            cost_model: 交易成本模型
        """
        self.n_groups = n_groups
        self.k_test = k_test
        self.embargo_days = embargo_days
        self.purge_days = purge_days
        self.cost_model = cost_model or CostModel()

    def run_cpcv(
        self,
        df: pd.DataFrame,
        model_types: List[ModelType],
        horizon: PredictionHorizon = PredictionHorizon.SHORT,
    ) -> Dict[str, Any]:
        """
        执行 CPCV 回测

        Returns:
            每个模型的 CPCV 结果，含各路径指标和聚合统计
        """
        df = df.sort_values("date").reset_index(drop=True)

        # 自适应分组：确保训练数据特征工程后至少有50个样本
        # 特征工程大约丢弃前100行（MA200等），训练原始数据至少需要150行
        min_train_raw_rows = 120
        n_train_groups = self.n_groups - self.k_test
        group_rows = len(df) // self.n_groups
        estimated_train_rows = group_rows * n_train_groups - self.embargo_days * n_train_groups
        if estimated_train_rows < min_train_raw_rows and self.n_groups > 3:
            # 减少分组数以增加每组数据量
            # 目标：n_groups 使得 group_rows * (n_groups - k_test) - embargo * (n_groups - k_test) >= min_train_raw_rows
            # group_rows = len(df) / n_groups, k_test ≈ n_groups/3
            # 简化：逐步减少 n_groups 直到满足条件
            for n in range(self.n_groups - 1, 2, -1):
                k = max(1, n // 3)
                gr = len(df) // n
                est = gr * (n - k) - self.embargo_days * (n - k)
                if est >= min_train_raw_rows:
                    self.n_groups = n
                    self.k_test = k
                    logger.info(f"CPCV adjusted: n_groups={self.n_groups}, k_test={self.k_test} (estimated train rows={estimated_train_rows} < {min_train_raw_rows})")
                    break
            else:
                self.n_groups = 3
                self.k_test = 1
                logger.info(f"CPCV adjusted to minimum: n_groups=3, k_test=1")

        groups = self._split_into_groups(df)
        n_paths = len(list(combinations(range(self.n_groups), self.k_test)))
        logger.info(f"CPCV: {self.n_groups} groups, {self.k_test} test, {n_paths} paths, {len(df)} data points")

        results = {}
        for model_type in model_types:
            logger.info(f"CPCV backtesting: {model_type.value}")
            path_results = self._run_cpcv_model(df, groups, model_type, horizon)
            aggregated = self._aggregate_paths(path_results, horizon)
            aggregated["model_type"] = model_type.value
            aggregated["n_groups"] = self.n_groups
            aggregated["k_test"] = self.k_test
            aggregated["n_paths"] = n_paths
            results[model_type.value] = aggregated

        # 买入持有基准（单路径，用全量数据）
        results["benchmark"] = self._cpcv_benchmark(df, horizon)

        # PBO 计算
        pbo = self._compute_pbo(results, model_types)
        results["pbo_analysis"] = pbo

        return results

    def _split_into_groups(self, df: pd.DataFrame) -> List[Tuple[int, int]]:
        """将数据分成 n_groups 个连续组，返回 [(start_idx, end_idx), ...]"""
        n = len(df)
        group_size = n // self.n_groups
        groups = []
        for i in range(self.n_groups):
            start = i * group_size
            end = (i + 1) * group_size if i < self.n_groups - 1 else n
            groups.append((start, end))
        return groups

    def _run_cpcv_model(
        self,
        df: pd.DataFrame,
        groups: List[Tuple[int, int]],
        model_type: ModelType,
        horizon: PredictionHorizon,
    ) -> List[Dict[str, Any]]:
        """对单个模型运行所有 CPCV 路径"""
        all_test_groups = list(combinations(range(self.n_groups), self.k_test))
        path_results = []

        for path_idx, test_group_indices in enumerate(all_test_groups):
            train_group_indices = [i for i in range(self.n_groups) if i not in test_group_indices]

            # 组装训练数据和测试数据的索引范围
            train_ranges = [groups[i] for i in train_group_indices]
            test_ranges = [groups[i] for i in test_group_indices]

            # 应用 embargo 和 purge
            train_indices, test_indices = self._apply_purge_embargo(
                train_ranges, test_ranges
            )

            if not train_indices or not test_indices:
                continue

            train_df = df.iloc[train_indices].copy()
            test_df = df.iloc[test_indices].copy()

            if len(train_df) < 100 or len(test_df) < 5:
                continue

            # 训练模型
            predictor = GoldPricePredictor()
            try:
                predictor.train(train_df, model_type, horizon)
            except Exception as e:
                logger.warning(f"CPCV path {path_idx} train failed: {e}")
                continue

            # 在测试集上逐点预测
            equity_curve = [1.0]
            predictions_log = []
            MIN_THRESHOLD = 0.001

            recent_returns = train_df['close'].pct_change().dropna()
            recent_vol = recent_returns.tail(20).std() * np.sqrt(252) if len(recent_returns) >= 20 else 0.15
            single_cost = self.cost_model.round_trip_cost(recent_vol)

            # 获取训练集最后一个已知价格
            last_train_price = train_df['close'].iloc[-1]

            for idx in test_indices:
                if idx + horizon.value >= len(df):
                    break

                # 用截至当天的所有可用数据来预测（模拟当时已知的数据）
                pred_df = df.iloc[:idx].copy()

                try:
                    result = predictor.predict(pred_df, model_type, horizon, use_last_known_price=True)
                    predicted_return = result.predicted_change_percent / 100
                except Exception as e:
                    logger.debug(f"CPCV predict failed at idx {idx}: {e}")
                    predicted_return = 0

                # 实际收益率
                actual_return = (df['close'].iloc[idx + horizon.value] - df['close'].iloc[idx]) / df['close'].iloc[idx]

                if predicted_return > MIN_THRESHOLD:
                    ret = actual_return - single_cost
                elif predicted_return < -MIN_THRESHOLD:
                    ret = 0  # 空仓
                else:
                    ret = 0

                equity_curve.append(equity_curve[-1] * (1 + ret))
                predictions_log.append({
                    "predicted": predicted_return,
                    "actual": actual_return,
                    "correct_direction": (predicted_return * actual_return) > 0,
                    "traded": predicted_return > MIN_THRESHOLD,
                })

            if len(equity_curve) > 1:
                metrics = self._calculate_path_metrics(equity_curve, predictions_log, horizon)
                metrics["path_idx"] = path_idx
                metrics["test_groups"] = list(test_group_indices)
                metrics["train_groups"] = train_group_indices
                path_results.append(metrics)

        return path_results

    def _apply_purge_embargo(
        self,
        train_ranges: List[Tuple[int, int]],
        test_ranges: List[Tuple[int, int]],
    ) -> Tuple[List[int], List[int]]:
        """
        应用 Purging 和 Embargo

        - Embargo: 从训练集尾部去除 embargo_days 天
        - Purging: 从测试集头部去除 purge_days 天
        """
        train_indices = []
        for start, end in train_ranges:
            # Embargo: 去除尾部
            embargoed_end = max(start, end - self.embargo_days)
            train_indices.extend(range(start, embargoed_end))

        test_indices = []
        for start, end in test_ranges:
            # Purging: 去除头部
            purged_start = min(start + self.purge_days, end)
            test_indices.extend(range(purged_start, end))

        return train_indices, test_indices

    def _calculate_path_metrics(
        self,
        equity_curve: List[float],
        predictions_log: List[Dict],
        horizon: PredictionHorizon,
    ) -> Dict[str, Any]:
        """计算单条路径的回测指标"""
        equity_arr = np.array(equity_curve)
        returns = np.diff(equity_arr) / equity_arr[:-1]

        total_return = equity_arr[-1] - 1
        periods = len(equity_arr) - 1
        periods_per_year = 252 / horizon.value

        if periods > 0 and total_return > -1:
            log_total = np.log(1 + total_return)
            annualized_return = np.exp(log_total * periods_per_year / periods) - 1
        else:
            annualized_return = 0

        peak = np.maximum.accumulate(equity_arr)
        drawdown = (equity_arr - peak) / peak
        max_drawdown = np.min(drawdown) if len(drawdown) > 0 else 0

        volatility = np.std(returns) * np.sqrt(periods_per_year) if len(returns) > 0 else 0
        risk_free = 0.03
        sharpe_ratio = (annualized_return - risk_free) / volatility if volatility > 0 else 0

        # 方向准确率
        correct = sum(1 for p in predictions_log if p.get("correct_direction"))
        da = correct / len(predictions_log) if predictions_log else 0

        # Sortino
        downside_returns = returns[returns < 0]
        downside_std = np.std(downside_returns) * np.sqrt(periods_per_year) if len(downside_returns) > 0 else volatility
        sortino_ratio = (annualized_return - risk_free) / downside_std if downside_std > 0 else 0

        # Calmar
        calmar_ratio = annualized_return / abs(max_drawdown) if max_drawdown != 0 else 0

        # 胜率
        traded = [p for p in predictions_log if p.get("traded")]
        win_count = sum(1 for p in traded if p["actual"] > 0)
        win_rate = win_count / len(traded) if traded else 0

        # 信息比率
        benchmark_returns = np.full_like(returns, np.mean(returns)) if len(returns) > 0 else returns
        tracking_error = np.std(returns - benchmark_returns) * np.sqrt(periods_per_year) if len(returns) > 1 else 0
        information_ratio = (annualized_return - risk_free) / tracking_error if tracking_error > 0 else 0

        # 盈亏比
        trade_returns = [p["actual"] for p in traded] if traded else []
        gross_profit = sum(r for r in trade_returns if r > 0)
        gross_loss = abs(sum(r for r in trade_returns if r < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else (float('inf') if gross_profit > 0 else 0)

        # 最大连亏
        max_consec_loss = 0
        current_streak = 0
        for r in trade_returns:
            if r < 0:
                current_streak += 1
                max_consec_loss = max(max_consec_loss, current_streak)
            else:
                current_streak = 0

        # 均持仓收益
        avg_holding_return = np.mean(trade_returns) * 100 if trade_returns else 0

        return {
            "total_return": round(total_return * 100, 2),
            "annualized_return": round(annualized_return * 100, 2),
            "max_drawdown": round(max_drawdown * 100, 2),
            "sharpe_ratio": round(sharpe_ratio, 2),
            "sortino_ratio": round(sortino_ratio, 2),
            "calmar_ratio": round(calmar_ratio, 2),
            "directional_accuracy": round(da * 100, 2),
            "win_rate": round(win_rate * 100, 2),
            "information_ratio": round(information_ratio, 2),
            "profit_factor": round(profit_factor, 2) if profit_factor != float('inf') else None,
            "max_consecutive_losses": max_consec_loss,
            "avg_holding_return": round(avg_holding_return, 4),
            "trade_count": len(predictions_log),
            "equity_curve": [round(v, 4) for v in equity_curve],
        }

    def _aggregate_paths(
        self,
        path_results: List[Dict[str, Any]],
        horizon: PredictionHorizon,
    ) -> Dict[str, Any]:
        """聚合所有路径的指标"""
        if not path_results:
            return {
                "total_return": 0,
                "annualized_return": 0,
                "max_drawdown": 0,
                "sharpe_ratio": 0,
                "sortino_ratio": 0,
                "calmar_ratio": 0,
                "directional_accuracy": 0,
                "win_rate": 0,
                "information_ratio": 0,
                "profit_factor": 0,
                "max_consecutive_losses": 0,
                "avg_holding_return": 0,
                "trade_count": 0,
                "path_count": 0,
                "paths": [],
            }

        # 各路径关键指标
        returns = [p["total_return"] for p in path_results]
        annualized = [p["annualized_return"] for p in path_results]
        max_dds = [p["max_drawdown"] for p in path_results]
        sharpes = [p["sharpe_ratio"] for p in path_results]
        sortinos = [p["sortino_ratio"] for p in path_results]
        calmars = [p["calmar_ratio"] for p in path_results]
        das = [p["directional_accuracy"] for p in path_results]
        win_rates = [p["win_rate"] for p in path_results]
        information_ratios = [p["information_ratio"] for p in path_results]
        profit_factors = [p["profit_factor"] for p in path_results if p["profit_factor"] is not None]
        max_consec_losses = [p["max_consecutive_losses"] for p in path_results]
        avg_holding_returns = [p["avg_holding_return"] for p in path_results]

        # 聚合的权益曲线（各路径平均）
        max_len = max(len(p["equity_curve"]) for p in path_results)
        avg_curve = []
        for j in range(max_len):
            vals = [p["equity_curve"][j] for p in path_results if j < len(p["equity_curve"])]
            avg_curve.append(round(np.mean(vals), 4))

        return {
            "total_return": round(np.mean(returns), 2),
            "total_return_std": round(np.std(returns), 2),
            "annualized_return": round(np.mean(annualized), 2),
            "annualized_return_std": round(np.std(annualized), 2),
            "max_drawdown": round(np.mean(max_dds), 2),
            "max_drawdown_std": round(np.std(max_dds), 2),
            "sharpe_ratio": round(np.mean(sharpes), 2),
            "sharpe_ratio_std": round(np.std(sharpes), 2),
            "sortino_ratio": round(np.mean(sortinos), 2),
            "calmar_ratio": round(np.mean(calmars), 2),
            "directional_accuracy": round(np.mean(das), 2),
            "directional_accuracy_std": round(np.std(das), 2),
            "win_rate": round(np.mean(win_rates), 2),
            "information_ratio": round(np.mean(information_ratios), 2),
            "profit_factor": round(np.mean(profit_factors), 2) if profit_factors else None,
            "max_consecutive_losses": round(np.mean(max_consec_losses), 1),
            "avg_holding_return": round(np.mean(avg_holding_returns), 4),
            "trade_count": sum(p["trade_count"] for p in path_results),
            "path_count": len(path_results),
            "equity_curve": avg_curve,
            "paths": path_results,
        }

    def _compute_pbo(
        self,
        results: Dict[str, Any],
        model_types: List[ModelType],
    ) -> Dict[str, Any]:
        """
        Probability of Backtest Overfitting (PBO)

        PBO = 在所有CPCV路径中，最优策略的OOS表现低于中位数的概率。
        PBO越高，说明回测过拟合风险越大。

        简化实现：比较各模型在各路径上的表现分布
        """
        if len(model_types) < 2:
            return {"pbo": None, "note": "需要至少2个模型才能计算PBO"}

        # 收集各模型在各路径的 Sharpe ratio
        model_sharpes = {}
        for mt in model_types:
            mt_result = results.get(mt.value, {})
            paths = mt_result.get("paths", [])
            if paths:
                model_sharpes[mt.value] = [p["sharpe_ratio"] for p in paths]

        if len(model_sharpes) < 2:
            return {"pbo": None, "note": "路径数据不足"}

        # 对每条路径，找出IS最优模型（最高Sharpe），记录其OOS表现
        # 由于CPCV每条路径本身就是OOS，直接统计最优路径的风险
        all_sharpes = []
        for mt, sharpes in model_sharpes.items():
            all_sharpes.extend(sharpes)

        if not all_sharpes:
            return {"pbo": None, "note": "无有效Sharpe数据"}

        # PBO: 最优路径Sharpe < 整体中位数的比例
        median_sharpe = np.median(all_sharpes)
        best_per_path = []
        n_paths = max(len(v) for v in model_sharpes.values())

        for i in range(n_paths):
            path_sharpes = {}
            for mt, sharpes in model_sharpes.items():
                if i < len(sharpes):
                    path_sharpes[mt] = sharpes[i]
            if path_sharpes:
                best_sharpe = max(path_sharpes.values())
                best_per_path.append(best_sharpe)

        if not best_per_path:
            return {"pbo": None, "note": "无有效路径数据"}

        pbo = sum(1 for s in best_per_path if s < median_sharpe) / len(best_per_path)

        return {
            "pbo": round(pbo, 4),
            "median_sharpe": round(median_sharpe, 4),
            "interpretation": "PBO<0.3 低过拟合风险, 0.3-0.5 中等, >0.5 高风险",
            "model_sharpe_distributions": {
                mt: {
                    "mean": round(np.mean(sharpes), 2),
                    "std": round(np.std(sharpes), 2),
                    "min": round(min(sharpes), 2),
                    "max": round(max(sharpes), 2),
                }
                for mt, sharpes in model_sharpes.items()
            },
        }

    def _cpcv_benchmark(self, df: pd.DataFrame, horizon: PredictionHorizon) -> Dict[str, Any]:
        """CPCV 模式下的买入持有基准"""
        engine = BacktestEngine(
            train_window=min(252, len(df) // 4),
            test_window=horizon.value,
            embargo_days=self.embargo_days,
            purge_days=self.purge_days,
            cost_model=self.cost_model,
        )
        return engine._calculate_benchmark(df, horizon)


class TrendFollowingStrategy:
    """
    趋势跟踪策略：50/200日MA交叉 + ATR止损

    信号逻辑：
    - 金叉（MA50 > MA200）→ 做多
    - 死叉（MA50 < MA200）→ 空仓（只做多不做空）
    - ATR止损：持仓期间若价格跌破入场价 - ATR(20) * sl_multiplier 则止损
    """

    def __init__(
        self,
        fast_ma: int = 50,
        slow_ma: int = 200,
        atr_window: int = 20,
        sl_multiplier: float = 2.0,
        cost_model: CostModel = None,
    ):
        """
        Args:
            fast_ma: 快速均线天数
            slow_ma: 慢速均线天数
            atr_window: ATR计算窗口
            sl_multiplier: 止损倍数（ATR * sl_multiplier）
            cost_model: 交易成本模型
        """
        self.fast_ma = fast_ma
        self.slow_ma = slow_ma
        self.atr_window = atr_window
        self.sl_multiplier = sl_multiplier
        self.cost_model = cost_model or CostModel()

    @staticmethod
    def compute_atr_for_signal(df: pd.DataFrame, window: int = 20) -> pd.Series:
        """计算ATR供外部使用"""
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift(1)).abs()
        low_close = (df['low'] - df['close'].shift(1)).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return tr.rolling(window).mean()

    def run_backtest(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        运行趋势跟踪策略回测

        Returns:
            策略绩效指标
        """
        df = df.sort_values('date').reset_index(drop=True)
        close = df['close']

        # 计算MA
        ma_fast = close.rolling(self.fast_ma).mean()
        ma_slow = close.rolling(self.slow_ma).mean()

        # 计算ATR
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift(1)).abs()
        low_close = (df['low'] - df['close'].shift(1)).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = tr.rolling(self.atr_window).mean()

        equity_curve = [1.0]
        trades_log = []
        monthly_returns = {}

        position = 0  # 0=空仓, 1=多头
        entry_price = 0.0
        entry_idx = 0
        last_equity = 1.0  # 记录上次更新权益时的值
        position_start_price = 0.0  # 记录入场时的价格，用于计算持仓期间权益

        # 需要足够的MA预热天数
        start_idx = self.slow_ma + 10

        for i in range(start_idx, len(df)):
            if np.isnan(ma_fast.iloc[i]) or np.isnan(ma_slow.iloc[i]) or np.isnan(atr.iloc[i]):
                equity_curve.append(last_equity)
                continue

            # 信号
            golden_cross = ma_fast.iloc[i] > ma_slow.iloc[i]
            death_cross = ma_fast.iloc[i] < ma_slow.iloc[i]

            if position == 0 and golden_cross:
                # 金叉入场
                position = 1
                entry_price = close.iloc[i]
                position_start_price = close.iloc[i]
                entry_idx = i
                equity_curve.append(last_equity)

            elif position == 1:
                # ATR止损检查
                stop_loss = entry_price - atr.iloc[i] * self.sl_multiplier
                if close.iloc[i] < stop_loss:
                    # 止损出场
                    recent_vol = close.pct_change().dropna().tail(20).std() * np.sqrt(252) if i > 20 else 0.15
                    single_cost = self.cost_model.round_trip_cost(recent_vol)
                    ret = (close.iloc[i] - entry_price) / entry_price - single_cost
                    last_equity = last_equity * (1 + ret)
                    equity_curve.append(last_equity)
                    trades_log.append({
                        'entry_date': df['date'].iloc[entry_idx],
                        'exit_date': df['date'].iloc[i],
                        'entry_price': entry_price,
                        'exit_price': close.iloc[i],
                        'return': ret,
                        'exit_reason': 'stop_loss',
                        'holding_days': i - entry_idx,
                    })
                    position = 0

                elif death_cross:
                    # 死叉出场
                    recent_vol = close.pct_change().dropna().tail(20).std() * np.sqrt(252) if i > 20 else 0.15
                    single_cost = self.cost_model.round_trip_cost(recent_vol)
                    ret = (close.iloc[i] - entry_price) / entry_price - single_cost
                    last_equity = last_equity * (1 + ret)
                    equity_curve.append(last_equity)
                    trades_log.append({
                        'entry_date': df['date'].iloc[entry_idx],
                        'exit_date': df['date'].iloc[i],
                        'entry_price': entry_price,
                        'exit_price': close.iloc[i],
                        'return': ret,
                        'exit_reason': 'death_cross',
                        'holding_days': i - entry_idx,
                    })
                    position = 0
                else:
                    # 持仓不变，根据当日价格更新权益（模拟持仓期间的每日波动）
                    daily_ret = (close.iloc[i] - position_start_price) / position_start_price
                    equity_curve.append(last_equity * (1 + daily_ret))

            else:
                # 空仓，不交易
                equity_curve.append(last_equity)

        # 如果到末尾还持仓，强制出场
        if position == 1:
            recent_vol = close.pct_change().dropna().tail(20).std() * np.sqrt(252) if len(df) > 20 else 0.15
            single_cost = self.cost_model.round_trip_cost(recent_vol)
            ret = (close.iloc[-1] - entry_price) / entry_price - single_cost
            last_equity = last_equity * (1 + ret)
            # 替换最后一个值（因为循环中已经append了）
            equity_curve[-1] = last_equity
            trades_log.append({
                'entry_date': df['date'].iloc[entry_idx],
                'exit_date': df['date'].iloc[-1],
                'entry_price': entry_price,
                'exit_price': close.iloc[-1],
                'return': ret,
                'exit_reason': 'end_of_data',
                'holding_days': len(df) - 1 - entry_idx,
            })

        # 计算指标
        return self._calculate_metrics(equity_curve, trades_log)

    def _calculate_metrics(
        self,
        equity_curve: List[float],
        trades_log: List[Dict],
    ) -> Dict[str, Any]:
        """计算策略绩效指标"""
        equity_arr = np.array(equity_curve)
        if len(equity_arr) < 2:
            return {
                "total_return": 0,
                "annualized_return": 0,
                "max_drawdown": 0,
                "sharpe_ratio": 0,
                "trade_count": 0,
                "win_rate": 0,
                "strategy": "trend_following",
                "parameters": {
                    "fast_ma": self.fast_ma,
                    "slow_ma": self.slow_ma,
                    "atr_window": self.atr_window,
                    "sl_multiplier": self.sl_multiplier,
                },
            }

        returns = np.diff(equity_arr) / equity_arr[:-1]
        total_return = equity_arr[-1] - 1
        periods = len(equity_arr) - 1
        periods_per_year = 252

        # 年化收益：使用对数收益率避免极端值
        if periods > 0 and total_return > -1:
            log_total = np.log(1 + total_return)
            annualized_return = np.exp(log_total * periods_per_year / periods) - 1
        else:
            annualized_return = 0

        peak = np.maximum.accumulate(equity_arr)
        drawdown = (equity_arr - peak) / peak
        max_drawdown = np.min(drawdown)

        volatility = np.std(returns) * np.sqrt(periods_per_year) if len(returns) > 0 else 0
        risk_free = 0.03
        sharpe_ratio = (annualized_return - risk_free) / volatility if volatility > 0 else 0

        # Sortino
        downside = returns[returns < 0]
        downside_std = np.std(downside) * np.sqrt(periods_per_year) if len(downside) > 0 else volatility
        sortino = (annualized_return - risk_free) / downside_std if downside_std > 0 else 0

        # Calmar
        calmar = annualized_return / abs(max_drawdown) if max_drawdown != 0 else 0

        # 胜率
        trade_returns = [t['return'] for t in trades_log]
        wins = sum(1 for r in trade_returns if r > 0)
        win_rate = wins / len(trade_returns) if trade_returns else 0

        # 平均持有期
        avg_holding = np.mean([t['holding_days'] for t in trades_log]) if trades_log else 0

        # Profit Factor
        gross_profit = sum(r for r in trade_returns if r > 0)
        gross_loss = abs(sum(r for r in trade_returns if r < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf') if gross_profit > 0 else 0

        # 出场原因分布
        exit_reasons = {}
        for t in trades_log:
            reason = t['exit_reason']
            exit_reasons[reason] = exit_reasons.get(reason, 0) + 1

        return {
            "total_return": round(total_return * 100, 2),
            "annualized_return": round(annualized_return * 100, 2),
            "max_drawdown": round(max_drawdown * 100, 2),
            "sharpe_ratio": round(sharpe_ratio, 2),
            "sortino_ratio": round(sortino, 2),
            "calmar_ratio": round(calmar, 2),
            "win_rate": round(win_rate * 100, 2),
            "profit_factor": round(profit_factor, 2) if profit_factor != float('inf') else None,
            "trade_count": len(trades_log),
            "avg_holding_days": round(avg_holding, 1),
            "volatility": round(volatility * 100, 2),
            "exit_reasons": exit_reasons,
            "equity_curve": [round(v, 4) for v in (equity_curve.tolist() if hasattr(equity_curve, 'tolist') else equity_curve)],
            "strategy": "trend_following",
            "parameters": {
                "fast_ma": self.fast_ma,
                "slow_ma": self.slow_ma,
                "atr_window": self.atr_window,
                "sl_multiplier": self.sl_multiplier,
            },
            "cost_model": {
                "commission_rate": self.cost_model.commission_rate,
                "slippage_base": self.cost_model.slippage_base,
                "typical_single_cost": self.cost_model.round_trip_cost(),
            },
        }
