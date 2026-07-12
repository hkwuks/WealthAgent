---
name: wealth-agent-reference
description: 智能理财Agent参考文档 - API 详情、数据模型、回测引擎、配置说明
---

# 智能理财Agent参考文档

## API 端点

### 系统 API

| 端点 | 方法 | 描述 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/docs` | GET | Swagger API 文档 |
| `/redoc` | GET | ReDoc API 文档 |

### 基金管理 API (`/api/funds`)

| 端点 | 方法 | 描述 | 请求体/参数 |
|------|------|------|------------|
| `/api/funds` | GET | 获取持仓基金列表 | - |
| `/api/funds/{code}` | GET | 获取单个基金详情 | - |
| `/api/funds/add` | POST | 添加基金到持仓 | `{fund_code, fund_name, fund_type, total_shares}` |
| `/api/funds/{code}` | DELETE | 删除持仓基金 | - |
| `/api/funds/query/{code}` | GET | 从外部数据源查询基金 | - |

**响应示例：**
```json
{
  "success": true,
  "data": {
    "fund_code": "110022",
    "fund_name": "易方达消费行业股票",
    "fund_type": "股票型",
    "nav": 3.2430,
    "nav_date": "2026-03-11"
  }
}
```

### 估值计算 API (`/api/valuation`)

| 端点 | 方法 | 描述 | 请求体/参数 |
|------|------|------|------------|
| `/api/valuation/{code}` | GET | 获取单基金估值 | `?prefer_holdings=true` |
| `/api/valuation/batch` | POST | 批量估值 | `{fund_codes: [...]}` |
| `/api/valuation/batch/stream` | POST | 流式批量估值 (SSE) | `{fund_codes: [...]}` |
| `/api/valuation/info/types` | GET | 获取估值类型说明 | - |

**响应示例：**
```json
{
  "success": true,
  "data": {
    "fund_code": "110022",
    "estimated_nav": 3.2342,
    "estimated_change_percent": 0.31,
    "previous_nav": 3.2240,
    "nav_date": "2026-03-11",
    "valuation_type": "holdings_based",
    "confidence": 0.75,
    "confidence_note": "基于前 10 大持仓计算"
  }
}
```

### 市场数据 API (`/api/market`)

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/market/stock/{code}` | GET | 获取 A 股股票行情 |
| `/api/market/etf/{code}` | GET | 获取场内 ETF 行情 |
| `/api/market/index/{code}` | GET | 获取国内指数行情 |
| `/api/market/global-index/{code}` | GET | 获取海外指数行情 |
| `/api/market/indices` | GET | 获取支持的指数列表 |

**响应示例：**
```json
{
  "success": true,
  "data": {
    "code": "600519",
    "name": "贵州茅台",
    "price": 1400.0,
    "change_percent": -0.13,
    "volume": 1234567,
    "timestamp": "2026-03-11T15:00:00+08:00"
  }
}
```

### 黄金预测 API (`/api/gold`)

| 端点 | 方法 | 描述 | 参数 |
|------|------|------|------|
| `/api/gold/predict` | POST | 预测黄金价格 | `symbol=GC`, `horizon_days=1|5|20`, `model_type=lightgbm|xgboost|ridge` |
| `/api/gold/predict-tb` | POST | Triple-Barrier方向预测 | `symbol=GC`, `model_type=lightgbm|xgboost|ridge` |
| `/api/gold/retrain` | POST | 强制重新训练模型 | `model_type`, `horizon_days`, `symbol=GC` |
| `/api/gold/history` | GET | 获取历史数据概览 | `symbol=GC` |
| `/api/gold/sync` | POST | 同步历史数据 | `years=5` |
| `/api/gold/current` | GET | 当前价格与宏观指标 | `symbol=GC` |
| `/api/gold/factors` | GET | 技术与宏观因子数据 | `symbol=GC` |
| `/api/gold/drift-status` | GET | 模型漂移检测状态 | `model_type`(可选), `horizon_days`(可选) |
| `/api/gold/record-actual` | POST | 记录实际涨跌方向 | `date`, `actual_direction=1|-1|0` |
| `/api/gold/factor-importance` | GET | 模型特征重要性 | `model_type`, `horizon_days` |
| `/api/gold/coverage` | GET | 数据覆盖率统计 | - |
| `/api/gold/backtest` | POST | 模型回测 | `years=1`, `model_types=lightgbm,xgboost,ridge`, `horizon_days=1`, `method=walk_forward|cpcv` |
| `/api/gold/backtest-trend` | POST | 趋势跟踪策略回测 | `years=2`, `fast_ma=50`, `slow_ma=200`, `sl_multiplier=2.0`, `symbol=GC` |
| `/api/gold/trend-signal` | GET | 当前趋势跟踪信号 | `symbol=GC` |

**预测响应示例：**
```json
{
  "success": true,
  "data": {
    "asset_code": "GC",
    "current_price": 2650.5,
    "predicted_price": 2658.2,
    "predicted_change": 7.7,
    "predicted_change_percent": 0.29,
    "confidence": 0.72,
    "horizon_days": 1,
    "model_type": "lightgbm",
    "features_used": ["return_1d", "return_5d", "ma_ratio_5_20", ...]
  }
}
```

**模型回测响应示例：**
```json
{
  "success": true,
  "data": {
    "backtest_id": "bt_20260607_220000",
    "method": "cpcv",
    "period_years": 1,
    "horizon_days": 1,
    "results": {
      "lightgbm": {
        "total_return": 0.91,
        "annualized_return": 3.53,
        "max_drawdown": -12.46,
        "sharpe_ratio": 0.13,
        "sortino_ratio": 0.16,
        "calmar_ratio": 0.95,
        "win_rate": 58.81,
        "directional_accuracy": 45.71,
        "information_ratio": 0.13,
        "profit_factor": 1.6,
        "max_consecutive_losses": 3.9,
        "avg_holding_return": 0.1964,
        "path_count": 15,
        "trade_count": 1610
      },
      "benchmark": {
        "total_return": 40.82,
        "annualized_return": 42.0,
        "max_drawdown": -17.25,
        "sharpe_ratio": 1.41
      }
    }
  }
}
```

**趋势回测响应示例：**
```json
{
  "success": true,
  "data": {
    "backtest_id": "trend_20260607_220000",
    "metrics": {
      "total_return": 58.32,
      "annualized_return": 48.46,
      "max_drawdown": -17.32,
      "sharpe_ratio": 1.76,
      "trade_count": 1,
      "win_rate": 100.0
    },
    "equity_curve": [1.0, 1.0, 0.9857, ...]
  }
}
```

## 数据模型

### Fund (持仓基金)
```json
{
  "fund_code": "110022",
  "fund_name": "易方达消费行业股票",
  "fund_type": "股票型",
  "total_shares": 1000.0,
  "holdings": []
}
```

### ValuationResult (估值结果)
```json
{
  "fund_code": "110022",
  "fund_name": "易方达消费行业股票",
  "estimated_nav": 3.2342,
  "estimated_change_percent": 0.31,
  "previous_nav": 3.2240,
  "latest_nav": 3.2430,
  "nav_date": "2026-03-11",
  "valuation_type": "holdings_based",
  "confidence": 0.75,
  "benchmark_info": {
    "name": "中证消费指数",
    "change_percent": 0.45
  }
}
```

### MarketData (市场行情)
```json
{
  "code": "600519",
  "name": "贵州茅台",
  "price": 1400.0,
  "change": -1.88,
  "change_percent": -0.13,
  "volume": 1234567,
  "high": 1420.0,
  "low": 1395.0,
  "open": 1410.0,
  "prev_close": 1401.88,
  "timestamp": "2026-03-11T15:00:00+08:00"
}
```

## 回测引擎架构

### Walk-Forward 回测 (`BacktestEngine`)

```
数据时间线:
|----Train----|--Embargo--|--Purge--|--Test--|
              ↑ 去掉尾部   ↑ 去掉头部
              (MA等滞后     (标签可能
               特征泄露)    重叠)

- 训练窗口: 252天（默认）
- 测试窗口: horizon_days
- Embargo: 20天（防滞后特征泄露）
- Purge: 1天（防标签重叠）
- 交易成本: 动态滑点 + 佣金
- 只做多不做空: predicted > 0.1% 才开仓
- 年化收益: 对数收益率年化 exp(ln(1+r)*252/n)
```

### CPCV 回测 (`CPCVEngine`)

```
参考: López de Prado, "Advances in Financial Machine Learning", Ch.12

1. 数据分成 N 组（默认6组）
2. 枚举 C(N, k) 组合（默认 k=2，C(6,2)=15条路径）
3. 每条路径: k组测试 + N-k组训练，独立训练+预测
4. 聚合: 各路径指标取均值
5. PBO: 过拟合概率（最优策略OOS表现低于中位数的概率）

自适应分组:
- 根据数据量自动调整 n_groups 和 k_test
- 确保训练数据特征工程后至少有50个样本
- 最小配置: n_groups=3, k_test=1, C(3,1)=3条路径
```

### 趋势跟踪策略 (`TrendFollowingStrategy`)

```
策略规则:
- 入场: 快速MA上穿慢速MA（金叉）
- 出场: 快速MA下穿慢速MA（死叉）或 ATR止损
- 止损: 收盘价 < 入场价 - sl_multiplier * ATR
- 权益曲线: 每日更新（持仓时按当日价格计算浮动盈亏）

默认参数:
- 快速MA: 50天
- 慢速MA: 200天
- ATR周期: 14天
- 止损倍数: 2.0倍ATR
```

## 回测指标说明

| 指标 | 英文 | 计算方法 |
|------|------|----------|
| 总收益率 | Total Return | equity_curve[-1] - 1 |
| 年化收益 | Annualized Return | exp(ln(1+total) * 252/horizon / periods) - 1 |
| 最大回撤 | Max Drawdown | min((equity - peak) / peak) |
| 夏普比率 | Sharpe Ratio | (annual - 3%) / vol |
| Sortino | Sortino Ratio | (annual - 3%) / downside_vol |
| Calmar | Calmar Ratio | annual / abs(max_drawdown) |
| 胜率 | Win Rate | 盈利交易数 / 总交易数 |
| 方向准确率 | DA | 预测方向正确次数 / 总预测次数 |
| 信息比率 | Information Ratio | (annual - 3%) / tracking_error |
| 盈亏比 | Profit Factor | gross_profit / gross_loss |
| 最大连亏 | Max Consecutive Losses | 连续亏损最大次数 |
| 均持仓收益 | Avg Holding Return | 交易收益均值 |

## MCP 服务器

MCP 服务器挂载在 FastAPI 应用的 `/mcp` 路径，使用 Streamable HTTP 传输。

### MCP Tools（26个）

#### 基金/市场工具（12个）

| 工具 | 参数 | 调用 API |
|------|------|----------|
| `get_fund_list` | - | `GET /api/funds` |
| `add_fund` | `fund_code`, `fund_name`, `fund_type`, `total_shares` | `POST /api/funds/add` |
| `delete_fund` | `fund_code` | `DELETE /api/funds/{code}` |
| `get_fund_info` | `fund_code` | `GET /api/funds/{code}` |
| `get_valuation` | `fund_code`, `prefer_holdings` | `GET /api/valuation/{code}` |
| `get_batch_valuation` | `fund_codes`, `prefer_holdings` | `POST /api/valuation/batch` |
| `get_stock_price` | `stock_code` | `GET /api/market/stock/{code}` |
| `get_etf_price` | `etf_code` | `GET /api/market/etf/{code}` |
| `get_index_price` | `index_code` | `GET /api/market/index/{code}` |
| `get_global_index_price` | `index_code` | `GET /api/market/global-index/{code}` |
| `get_valuation_types` | - | `GET /api/valuation/info/types` |
| `get_supported_indices` | - | `GET /api/market/indices` |

#### 黄金预测工具（14个）

| 工具 | 参数 | 调用 API |
|------|------|----------|
| `predict_gold_price` | `symbol`, `horizon_days`, `model_type` | `POST /api/gold/predict` |
| `predict_gold_tb` | `symbol`, `model_type` | `POST /api/gold/predict-tb` |
| `retrain_gold_model` | `model_type`, `horizon_days`, `symbol` | `POST /api/gold/retrain` |
| `get_gold_history` | `symbol`, `days` | `GET /api/gold/history` |
| `sync_gold_data` | `years` | `POST /api/gold/sync` |
| `get_gold_current` | `symbol` | `GET /api/gold/current` |
| `get_gold_factors` | `symbol` | `GET /api/gold/factors` |
| `get_gold_drift_status` | `model_type?`, `horizon_days?` | `GET /api/gold/drift-status` |
| `record_gold_actual` | `date`, `actual_direction`, `model_type`, `horizon_days` | `POST /api/gold/record-actual` |
| `get_gold_factor_importance` | `model_type`, `horizon_days`, `symbol` | `GET /api/gold/factor-importance` |
| `get_gold_coverage` | - | `GET /api/gold/coverage` |
| `run_gold_backtest` | `years`, `model_types`, `horizon_days`, `method` | `POST /api/gold/backtest` |
| `run_gold_backtest_trend` | `years`, `fast_ma`, `slow_ma`, `sl_multiplier`, `symbol` | `POST /api/gold/backtest-trend` |
| `get_gold_trend_signal` | `symbol` | `GET /api/gold/trend-signal` |

### MCP Resources（9个）

| 资源 URI | 描述 |
|----------|------|
| `fund://{fund_code}` | 基金详情 |
| `valuation://{fund_code}` | 实时估值 |
| `market://stock/{stock_code}` | 股票行情 |
| `market://etf/{etf_code}` | ETF 行情 |
| `market://index/{index_code}` | 国内指数 |
| `market://global-index/{index_code}` | 海外指数 |
| `gold://current` | 黄金当前价格与宏观指标 |
| `gold://signal` | 黄金趋势信号 |
| `gold://factors` | 黄金因子数据 |

### MCP Prompts（3个）

| Prompt | 参数 | 描述 |
|--------|------|------|
| `analyze_fund` | `fund_code` | 分析基金投资价值 |
| `portfolio_summary` | - | 持仓组合总结报告 |
| `market_daily` | - | 市场日报 |

### MCP 配置

```bash
# 添加 MCP 服务器
claude mcp add --transport http fund-valuation http://127.0.0.1:8000/mcp
```

或 `.mcp.json`：
```json
{
  "mcpServers": {
    "fund-valuation": {
      "type": "http",
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

## 配置说明

### 后端配置 (`backend/config.py`)

```python
APP_NAME = "智能理财Agent"
APP_VERSION = "1.0.0"
DEBUG = True

API_PREFIX = "/api"
DATA_DIR = "data"  # funds.json 存储目录

CORS_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]

TUSHARE_TOKEN = None  # 可选，Tushare API token
```

### 环境变量 (`.env`)

```bash
# 可选配置
TUSHARE_TOKEN=your_token_here
LOG_LEVEL=INFO
```

## 部署指南

### 本地开发部署

```bash
# 1. 创建虚拟环境
conda create -n fund_valuation python=3.11
conda activate fund_valuation

# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动后端
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# 4. 启动前端
cd frontend
npm install
npm run dev
```

### Production 部署

```bash
pip install gunicorn

gunicorn backend.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 120 \
  --access-logfile logs/access.log \
  --error-logfile logs/error.log
```

## 日志配置

日志输出到：
- 控制台：INFO 级别
- 文件：`backend/logs/api.log`，DEBUG 级别，轮转（10MB/文件，保留 7 天）

## 错误码说明

| 错误码 | 说明 |
|--------|------|
| `SUCCESS` | 成功 |
| `FUND_NOT_FOUND` | 基金不存在 |
| `VALUATION_FAILED` | 估值失败 |
| `DATA_SOURCE_ERROR` | 数据源错误 |
| `INVALID_PARAMETER` | 参数无效 |
| `INTERNAL_ERROR` | 内部错误 |

## 数据源优先级

### A 股股票
1. AkShare (主)
2. 新浪财经 (备用)
3. 腾讯财经 (备用)

### 基金数据
1. 东方财富 (主)
2. 天天基金 (备用)
3. AkShare (备用)

### 黄金数据
1. yFinance (COMEX期货 GC=F)
2. AkShare (现货 Au99.99)

### 海外市场
1. yFinance (主)
2. 新浪财经港股 (备用)

## 估值计算流程

```
1. 获取基金基本信息
   ↓
2. 判断基金类型和市场类型
   ↓
3. 选择估值策略
   ├─ 场内 ETF → real_time_price (取交易价格)
   ├─ 指数基金 → index_based (取指数涨跌幅)
   ├─ 主动股票 → holdings_based (持仓加权)
   └─ 数据缺失 → benchmark_only (业绩基准)
   ↓
4. 计算估算净值和涨跌幅
   ↓
5. 返回 ValuationResult
```

## 黄金预测流程

```
1. 获取黄金历史数据（yFinance + AkShare）
   ↓
2. 特征工程（技术指标 + 宏观因子）
   ├─ 技术指标: MA, RSI, MACD, ATR, 布林带, 波动率
   ├─ 宏观因子: DXY, VIX, US10Y, TIPS, BREAKEVEN
   └─ 交互特征: 品种比率、动量散度
   ↓
3. 因子筛选（互信息 + 相关性去冗余）
   ↓
4. 训练/加载模型
   ├─ LightGBM / XGBoost / Ridge
   └─ Triple-Barrier 分类模型
   ↓
5. 预测 → 返回预测价格/方向概率
```

## 相关资源

- [SKILL.md](./SKILL.md) - 技能使用指南
- [CLAUDE.md](../../CLAUDE.md) - 项目开发指南
- [README.md](../../README.md) - 项目说明
- [API 文档](http://localhost:8000/docs) - Swagger UI
