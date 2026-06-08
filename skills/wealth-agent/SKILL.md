---
name: wealth-agent
description: 智能理财Agent技能。提供基金查询、实时估值、市场数据、黄金价格预测与回测、趋势跟踪等功能，支持 HTTP API 调用方式。
---

# 智能理财Agent技能

## 触发场景

当用户请求以下内容时，应使用此技能：
- 查询基金信息、净值、持仓
- 获取基金实时估值和涨跌幅
- 查询股票、ETF、指数行情
- 分析基金投资价值
- 批量估值多只基金
- 预测黄金价格走势
- 回测黄金预测模型或趋势跟踪策略
- 获取黄金宏观因子、趋势信号
- 检查模型漂移状态

## 能力说明

### 基金估值功能

| 能力 | 描述 | HTTP API |
|------|------|----------|
| 基金查询 | 获取基金信息、持仓、净值 | `GET /api/funds/{code}` |
| 实时估值 | 盘中实时估算基金净值 | `GET /api/valuation/{code}` |
| 持仓管理 | 添加/删除/查看持仓 | `GET/POST /api/funds` |
| 股票行情 | A 股实时价格 | `GET /api/market/stock/{code}` |
| ETF 行情 | 场内 ETF 实时价格 | `GET /api/market/etf/{code}` |
| 指数行情 | 国内外指数点位 | `GET /api/market/index/{code}` |
| 批量估值 | 同时估值多只基金 | `POST /api/valuation/batch` |

### 黄金预测功能

| 能力 | 描述 | HTTP API |
|------|------|----------|
| 价格预测 | 预测黄金价格变动 | `POST /api/gold/predict` |
| TB预测 | Triple-Barrier方向概率预测 | `POST /api/gold/predict-tb` |
| 模型回测 | Walk-Forward / CPCV 回测 | `POST /api/gold/backtest` |
| 趋势回测 | MA交叉+ATR止损策略回测 | `POST /api/gold/backtest-trend` |
| 趋势信号 | 当前MA交叉状态和持仓建议 | `GET /api/gold/trend-signal` |
| 当前价格 | 黄金价格与宏观指标 | `GET /api/gold/current` |
| 因子数据 | 技术与宏观因子 | `GET /api/gold/factors` |
| 因子重要性 | 模型特征重要性排名 | `GET /api/gold/factor-importance` |
| 漂移检测 | 模型数据漂移状态 | `GET /api/gold/drift-status` |
| 数据同步 | 同步黄金历史数据 | `POST /api/gold/sync` |
| 强制重训 | 重新训练模型 | `POST /api/gold/retrain` |

## 服务启动

### 检查服务状态

```bash
curl -s http://localhost:8000/health
```

返回 `{"status": "healthy"}` 表示服务正常。

### 启动后端服务

```bash
cd <PROJECT_ROOT>
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

### 启动前端

```bash
cd frontend
npm run dev
```

**注意：** 后端 API 文档在 http://localhost:8000/docs

## 使用示例

### 基金估值示例

**查询基金信息:**
```bash
curl http://localhost:8000/api/funds/110022
```

**获取实时估值:**
```bash
curl http://localhost:8000/api/valuation/110022
```

**批量估值:**
```bash
curl -X POST http://localhost:8000/api/valuation/batch \
  -H "Content-Type: application/json" \
  -d '{"fund_codes": ["110022", "510300", "159915"]}'
```

**获取市场行情:**
```bash
curl http://localhost:8000/api/market/stock/600519
curl http://localhost:8000/api/market/etf/510300
curl http://localhost:8000/api/market/index/000300
curl http://localhost:8000/api/market/global-index/nasdaq
```

### 黄金预测示例

**预测黄金价格:**
```bash
# 1天预测，LightGBM模型
curl -X POST "http://localhost:8000/api/gold/predict?symbol=GC&horizon_days=1&model_type=lightgbm"

# 1周预测，XGBoost模型
curl -X POST "http://localhost:8000/api/gold/predict?symbol=GC&horizon_days=5&model_type=xgboost"
```

**Triple-Barrier 方向预测:**
```bash
curl -X POST "http://localhost:8000/api/gold/predict-tb?symbol=GC&model_type=lightgbm"
```

**模型回测:**
```bash
# Walk-Forward 回测
curl -X POST "http://localhost:8000/api/gold/backtest?years=1&model_types=lightgbm,xgboost,ridge&horizon_days=1&method=walk_forward"

# CPCV 回测
curl -X POST "http://localhost:8000/api/gold/backtest?years=1&model_types=lightgbm,xgboost,ridge&horizon_days=1&method=cpcv"
```

**趋势跟踪回测:**
```bash
curl -X POST "http://localhost:8000/api/gold/backtest-trend?years=2&fast_ma=50&slow_ma=200&sl_multiplier=2.0"
```

**获取趋势信号:**
```bash
curl "http://localhost:8000/api/gold/trend-signal?symbol=GC"
```

**获取黄金当前价格与宏观指标:**
```bash
curl "http://localhost:8000/api/gold/current?symbol=GC"
```

**获取因子数据:**
```bash
curl "http://localhost:8000/api/gold/factors?symbol=GC"
```

**获取因子重要性:**
```bash
curl "http://localhost:8000/api/gold/factor-importance?model_type=lightgbm&horizon_days=1"
```

**检查模型漂移:**
```bash
curl "http://localhost:8000/api/gold/drift-status"
```

**强制重新训练:**
```bash
curl -X POST "http://localhost:8000/api/gold/retrain?model_type=lightgbm&horizon_days=1&symbol=GC"
```

**同步数据:**
```bash
curl -X POST "http://localhost:8000/api/gold/sync?years=5"
```

## 估值类型说明

系统根据基金类型自动选择最优估值方法：

| 估值类型 | 置信度 | 适用场景 |
|----------|--------|----------|
| `real_time_price` | 100% | 场内 ETF、LOF（直接取交易价格） |
| `index_based` | 85% | 指数基金、ETF 联接（基于跟踪指数） |
| `holdings_based` | 60-80% | 主动股票/混合型（基于持仓股票） |
| `benchmark_only` | 30% | 数据缺失（仅参考业绩基准） |

## 黄金预测模型说明

| 模型 | 描述 |
|------|------|
| `lightgbm` | LightGBM 梯度提升树（默认） |
| `xgboost` | XGBoost 梯度提升树 |
| `ridge` | Ridge 线性回归基准 |

| 预测周期 | 参数值 | 说明 |
|----------|--------|------|
| 1天 | `horizon_days=1` | SHORT |
| 1周 | `horizon_days=5` | MEDIUM |
| 1月 | `horizon_days=20` | LONG |

## 回测方法说明

| 方法 | 参数值 | 描述 |
|------|--------|------|
| Walk-Forward | `method=walk_forward` | 滚动窗口回测，带 Purging + Embargo |
| CPCV | `method=cpcv` | 组合清洗交叉验证，计算 PBO 过拟合指标 |

**CPCV 参数：** 默认 6 组、2 组测试、C(6,2)=15 条路径，自适应调整分组数以适应数据量。

**回测指标：** 总收益率、年化收益、最大回撤、夏普比率、Sortino、Calmar、胜率、方向准确率(DA)、信息比率、盈亏比、最大连亏、均持仓收益。

## MCP 工具

MCP 服务器挂载在 `/mcp`，提供以下工具和资源。

### 基金/市场 MCP 工具（12个）

| 工具 | 描述 |
|------|------|
| `get_fund_list` | 获取持仓基金列表 |
| `add_fund` | 添加基金到持仓 |
| `delete_fund` | 删除持仓基金 |
| `get_fund_info` | 获取基金详情 |
| `get_valuation` | 获取实时估值 |
| `get_batch_valuation` | 批量估值 |
| `get_stock_price` | 获取 A 股股票价格 |
| `get_etf_price` | 获取 ETF 价格 |
| `get_index_price` | 获取国内指数 |
| `get_global_index_price` | 获取海外指数 |
| `get_valuation_types` | 获取估值类型说明 |
| `get_supported_indices` | 获取支持的指数列表 |

### 黄金预测 MCP 工具（14个）

| 工具 | 描述 | 关键参数 |
|------|------|----------|
| `predict_gold_price` | 预测黄金价格 | `symbol`, `horizon_days`, `model_type` |
| `predict_gold_tb` | TB方向概率预测 | `symbol`, `model_type` |
| `retrain_gold_model` | 强制重新训练模型 | `model_type`, `horizon_days`, `symbol` |
| `get_gold_history` | 获取历史数据概况 | `symbol`, `days` |
| `sync_gold_data` | 同步历史数据 | `years` |
| `get_gold_current` | 当前价格与宏观指标 | `symbol` |
| `get_gold_factors` | 技术与宏观因子 | `symbol` |
| `get_gold_drift_status` | 模型漂移检测状态 | `model_type?`, `horizon_days?` |
| `record_gold_actual` | 记录实际方向 | `date`, `actual_direction` |
| `get_gold_factor_importance` | 特征重要性排名 | `model_type`, `horizon_days` |
| `get_gold_coverage` | 数据覆盖率统计 | - |
| `run_gold_backtest` | 模型回测 | `years`, `model_types`, `method` |
| `run_gold_backtest_trend` | 趋势跟踪回测 | `years`, `fast_ma`, `slow_ma` |
| `get_gold_trend_signal` | 当前趋势信号 | `symbol` |

### MCP 资源

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

### MCP Prompts

| Prompt | 描述 |
|--------|------|
| `analyze_fund` | 分析基金投资价值 |
| `portfolio_summary` | 持仓组合总结报告 |
| `market_daily` | 市场日报 |

## 常用基金代码参考

| 类型 | 代码 | 名称 |
|------|------|------|
| 沪深 300ETF | 510300 | 华泰柏瑞沪深 300ETF |
| 创业板 ETF | 159915 | 易方达创业板 ETF |
| 中证 500ETF | 510500 | 南方中证 500ETF |
| 科创 50ETF | 588000 | 华夏科创 50ETF |
| 黄金 ETF | 518880 | 华安黄金 ETF |
| 纳斯达克 ETF | 513100 | 国泰纳斯达克 100ETF |
| 标普 500ETF | 513500 | 博时标普 500ETF |

## 常用指数代码参考

| 市场 | 代码 | 名称 |
|------|------|------|
| A 股 | 000300 | 沪深 300 |
| A 股 | 000905 | 中证 500 |
| A 股 | 399006 | 创业板指 |
| A 股 | 000688 | 科创 50 |
| 港股 | hsi | 恒生指数 |
| 美股 | nasdaq | 纳斯达克指数 |
| 美股 | sp500 | 标普 500 |
| 美股 | dji | 道琼斯指数 |
| 日本 | n225 | 日经 225 |

## 注意事项

1. **服务依赖**: 所有功能依赖后端服务运行在 `http://localhost:8000`
2. **交易时间**: 估值数据仅在 A 股交易时段（9:30-15:00）有效
3. **QDII 时差**: 投资海外的 QDII 基金估值时间与 A 股不同步
4. **数据刷新**: 建议设置合理的刷新间隔（>=30 秒），避免被数据源限制
5. **免责声明**: 估值数据和预测结果仅供参考，不构成投资建议
6. **回测耗时**: CPCV 回测需训练多条路径（默认15条），耗时较长（约1-3分钟）

## 故障排除

**问题：API 调用返回空数据或错误**

```bash
# 1. 检查后端服务是否运行
curl http://localhost:8000/health

# 2. 检查基金代码是否正确
curl http://localhost:8000/api/funds/query/110022
```

**问题：估值数据为 null**
- 可能是非交易时间
- 基金可能是 QDII，需要等待海外市场开盘
- 数据源可能暂时不可用

**问题：CPCV 回测所有模型收益为 0**
- 数据量太少导致分组后训练样本不足（最低需50个有效特征样本）
- 尝试增加回测周期（2-3年）或使用 Walk-Forward 方法

**问题：后端启动失败**
```bash
# 检查依赖是否安装
pip install -r requirements.txt

# 检查端口是否被占用
lsof -i :8000
```
