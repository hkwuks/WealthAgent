---
name: wealth-agent-reference
description: 智能理财Agent参考文档 — API 端点、请求参数、响应结构
---

# 参考文档

> 端点前缀 `/api`，完整 URL 如 `/api/funds`。后端运行在 `http://localhost:8000`。

---

## 基金管理

| 方法 | 端点 | 描述 | 请求体 |
|------|------|------|--------|
| GET | `/funds` | 持仓基金列表 | — |
| GET | `/funds/{code}` | 基金详情 & 外部信息 | — |
| POST | `/funds/add` | 添加基金 | `{fund_code, fund_name, fund_type, total_shares}` |
| DELETE | `/funds/{code}` | 删除持仓 | — |
| PUT | `/funds/{code}` | 更新持仓（份额等） | `{total_shares}` |
| POST | `/funds/clear` | 清空所有持仓 | — |
| GET | `/funds/query/{code}` | 从外部数据源查询基金 | — |
| GET | `/funds/{code}/holdings` | 基金持仓（季报） | — |
| GET | `/funds/{code}/nav-history` | 净值历史 | — |

## 估值计算

| 方法 | 端点 | 描述 | 参数 |
|------|------|------|------|
| GET | `/valuation/{code}` | 单基金估值 | `?prefer_holdings=true` |
| GET | `/valuation/{code}/detail` | 估值详情（含持仓贡献） | — |
| POST | `/valuation/batch` | 批量估值 | `{fund_codes: [...]}` |
| POST | `/valuation/batch/stream` | 流式批量估值 SSE | `{fund_codes: [...]}` |
| GET | `/valuation/{code}/accuracy` | 估值准确率验证 | — |
| GET | `/valuation/info/types` | 估值类型说明 | — |

## 市场数据

| 方法 | 端点 | 描述 |
|------|------|------|
| GET | `/market/stock/{code}` | A 股实时行情 |
| GET | `/market/etf/{code}` | 场内 ETF 行情 |
| GET | `/market/index/{code}` | 国内指数行情 |
| GET | `/market/global-index/{code}` | 海外指数行情 |
| GET | `/market/indices` | 支持的指数列表 |
| POST | `/market/stock/batch` | 批量股票查询 |
| POST | `/market/index/batch` | 批量指数查询 |
| POST | `/market/global-index/batch` | 批量海外指数查询 |
| POST | `/market/etf/batch` | 批量 ETF 查询 |
| POST | `/market/index/batch/stream` | 流式批量指数 SSE |
| POST | `/market/cache/clear` | 清除缓存 |

## 黄金量化交易

所有黄金量化端点都以 `/gold/trading` 开头。

### 系统 & 策略

| 方法 | 端点 | 描述 |
|------|------|------|
| GET | `/gold/trading/status` | 系统状态 |
| GET | `/gold/trading/strategies` | 策略列表 |
| GET | `/gold/trading/strategies/{name}` | 策略详情 + 参数 |

### 回测

| 方法 | 端点 | 描述 | 关键字段 |
|------|------|------|----------|
| POST | `/gold/trading/backtest` | 单策略回测 | `strategy_name, start_date, end_date, capital, method` |
| POST | `/gold/trading/compare` | 多策略对比 | `strategy_names: [...]` |
| POST | `/gold/trading/backtest/sensitivity` | 参数敏感性分析 | `param_ranges: {key: [values]}` |
| POST | `/gold/trading/backtest/validation` | 样本内外验证 | `in_sample_ratio, scenario_name` |
| POST | `/gold/trading/backtest/walk-forward` | 滚动窗口回测 | `train_window, test_window` |
| POST | `/gold/trading/backtest/cpcv` | CPCV 组合验证 | `n_groups, k_test` |
| POST | `/gold/trading/backtest/monte-carlo` | Monte Carlo 模拟 | `n_simulations` |

### 信号 & 风控

| 方法 | 端点 | 描述 |
|------|------|------|
| GET | `/gold/trading/signals` | 交易信号列表 |
| POST | `/gold/trading/signal/generate` | 手动触发信号生成 |
| GET | `/gold/trading/risk/status` | 风控状态 |

### 数据 & 分析

| 方法 | 端点 | 描述 |
|------|------|------|
| GET | `/gold/trading/market-data` | 市场数据仪表盘（含宏观指标） |
| GET | `/gold/trading/analysis` | 技术分析（RSI/MA/布林带） |
| GET | `/gold/trading/bars` | K 线数据 |
| GET | `/gold/trading/feature-importance` | ML 特征重要性 |
| POST | `/gold/trading/label/triple-barrier` | Triple-Barrier 标注 |
| POST | `/gold/trading/sync-data` | 数据同步 |
| GET | `/gold/trading/config` | 系统配置 |
| GET | `/gold/trading/strategy-comparison` | 策略市场适配度对比 |

### 回测请求体

```json
{
  "strategy_name": "trend_following",
  "symbol": "AU0", "period": "d",
  "start_date": "2020-01-01",
  "end_date": "2025-12-31",
  "capital": 1000000,
  "params": { "fast_ma": 5, "slow_ma": 20 },
  "method": "auto"
}
```

`method`: `simple` / `walk_forward` / `auto`（ML 策略自动 WF）

### 回测响应结构

```json
{
  "success": true,
  "data": {
    "strategy": "trend_following",
    "report": {
      "total_return": 58.32,
      "annualized_return": 48.46,
      "max_drawdown": -17.32,
      "sharpe_ratio": 1.76,
      "win_rate": 100.0,
      "trade_count": 1,
      "benchmark": { "total_return": 40.82, "annualized_return": 42.0, "sharpe_ratio": 1.41 }
    },
    "signals": [],
    "trades": []
  }
}
```

### 回测指标

| 指标 | 说明 |
|------|------|
| total_return | 累计收益率 |
| annualized_return | 年化收益率（对数法） |
| max_drawdown | 最大回撤 |
| sharpe_ratio | 夏普比率（无风险 3%） |
| sortino_ratio | 下行波动调整 |
| calmar_ratio | 年化/最大回撤 |
| win_rate | 胜率（%） |
| directional_accuracy | 方向准确率（%） |
| profit_factor | 盈亏比 |
| max_consecutive_losses | 最大连亏次数 |
| avg_holding_return | 平均每笔收益率 |

---

## 响应示例

### 估值

```json
{
  "success": true,
  "data": {
    "fund_code": "110022",
    "fund_name": "易方达消费行业股票",
    "estimated_nav": 3.2342,
    "estimated_change_percent": 0.31,
    "previous_nav": 3.2240,
    "nav_date": "2026-03-11",
    "valuation_type": "holdings_based",
    "confidence": 0.75
  }
}
```

### 行情

```json
{
  "success": true,
  "data": {
    "code": "600519", "name": "贵州茅台",
    "price": 1400.0, "change": -1.88,
    "change_percent": -0.13, "volume": 1234567
  }
}
```

### 信号

```json
{
  "success": true,
  "data": {
    "signal_id": "tf_20260627_120000_signal",
    "strategy": "trend_following",
    "direction": "long",
    "price": 420.50,
    "stop_loss": 415.20,
    "confidence": 0.75,
    "reason": "MA5上穿MA20"
  }
}
```

---

## 估值类型

| 类型 | 置信度 | 适用 |
|------|--------|------|
| real_time_price | 100% | ETF/LOF |
| index_based | 85% | 指数基金/ETF联接 |
| holdings_based | 60-80% | 主动股票/混合型 |
| hybrid_bond | 70% | 偏债混合/二级债基 |
| hybrid_qdii | 70% | QDII |
| benchmark_only | 30% | 数据缺失 |

---

## 风控检查

| 检查 | WARNING | REJECT |
|------|---------|--------|
| 回撤 | 当日 > 5% | 当日 > 10% |
| 单日亏损 | > 2% | > 5% |
| 信号频率 | 同方向 5min 内重复 | — |
| VaR(95%) | > 5% 总资产 | > 10% 总资产 |
| 波动率 | ATR/价 > 5% | ATR/价 > 10% |

---

## MCP 工具

MCP 服务挂载在 `/mcp`，总共 **30 个工具**。

### 基金/市场（12 个）

`get_fund_list`, `add_fund`, `delete_fund`, `get_fund_info`, `get_valuation`, `get_batch_valuation`, `get_stock_price`, `get_etf_price`, `get_index_price`, `get_global_index_price`, `get_valuation_types`, `get_supported_indices`

### 黄金量化（18 个）

`get_gold_status`, `get_gold_strategies`, `get_gold_strategy_detail`, `get_gold_signals`, `generate_gold_signal`, `run_gold_strategy_backtest`, `compare_gold_strategies`, `run_gold_sensitivity`, `run_gold_validation`, `run_gold_walk_forward`, `run_gold_cpcv`, `run_gold_monte_carlo`, `get_gold_risk_status`, `get_gold_market_data`, `get_gold_analysis`, `get_gold_feature_importance`, `run_gold_triple_barrier_label`, `get_gold_config`

---

## MCP 配置

```bash
claude mcp add http wealth-agent http://127.0.0.1:8000/mcp
```

或 `.mcp.json`：

```json
{
  "mcpServers": {
    "wealth-agent": {
      "type": "http",
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

---

## 相关文件

- [SKILL.md](../SKILL.md) — 技能使用指南
- [CLAUDE.md](../../CLAUDE.md) — 项目开发指南
- [README.md](../../README.md) — 项目说明
