---
name: intelligent-wealth-agent
description: 智能理财Agent技能。提供基金查询、实时估值、市场数据、黄金价格预测等功能，支持 HTTP API 调用方式。
---

# 智能理财Agent技能

## 触发场景

当用户请求以下内容时，应使用此技能：
- 查询基金信息、净值、持仓
- 获取基金实时估值和涨跌幅
- 查询股票、ETF、指数行情
- 分析基金投资价值
- 批量估值多只基金
- 黄金价格预测和回测
- 查询黄金价格和宏观指标

## 能力说明

本技能提供以下功能：

| 能力 | 描述 | HTTP API |
|------|------|----------|
| 基金查询 | 获取基金信息、持仓、净值 | `GET /api/funds/{code}` |
| 实时估值 | 盘中实时估算基金净值 | `GET /api/valuation/{code}` |
| 持仓管理 | 添加/删除/查看持仓 | `GET/POST /api/funds` |
| 股票行情 | A 股实时价格 | `GET /api/market/stock/{code}` |
| ETF 行情 | 场内 ETF 实时价格 | `GET /api/market/etf/{code}` |
| 指数行情 | 国内外指数点位 | `GET /api/market/index/{code}` |
| 批量估值 | 同时估值多只基金 | `POST /api/valuation/batch` |
| 黄金预测 | 三模型预测黄金价格 | `POST /api/gold/predict` |
| 黄金行情 | 当前黄金价格和宏观指标 | `GET /api/gold/current` |
| 模型回测 | 黄金预测模型回测 | `POST /api/gold/backtest` |

## 服务启动

### 检查服务状态

```bash
# 检查后端是否运行
curl -s http://localhost:8000/health
```

返回 `{"status": "healthy"}` 表示服务正常。

### 启动后端服务

如果服务未运行，Agent 应自行启动：

```bash
# 1. 进入项目根目录
cd <PROJECT_ROOT>

# 2. 安装依赖（如果需要）
pip install -r requirements.txt

# 3. 启动后端服务
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

**注意：**
- 后端启动后，API 文档在 http://localhost:8000/docs

## 使用示例

### 示例 1：查询基金信息

**HTTP API 调用:**
```bash
curl http://localhost:8000/api/funds/110022
```

**预期返回:**
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

### 示例 2：获取实时估值

**HTTP API 调用:**
```bash
curl http://localhost:8000/api/valuation/110022
```

**预期返回:**
```json
{
  "success": true,
  "data": {
    "fund_code": "110022",
    "estimated_nav": 3.2342,
    "estimated_change_percent": 0.31,
    "valuation_type": "holdings_based",
    "confidence": 0.75
  }
}
```

### 示例 3：批量估值

**HTTP API 调用:**
```bash
curl -X POST http://localhost:8000/api/valuation/batch \
  -H "Content-Type: application/json" \
  -d '{"fund_codes": ["110022", "510300", "159915"]}'
```

### 示例 4：获取持仓列表

**HTTP API 调用:**
```bash
curl http://localhost:8000/api/funds
```

### 示例 5：获取市场行情

**股票行情:**
```bash
curl http://localhost:8000/api/market/stock/600519
```

**ETF 行情:**
```bash
curl http://localhost:8000/api/market/etf/510300
```

**指数行情:**
```bash
curl http://localhost:8000/api/market/index/000300
curl http://localhost:8000/api/market/global-index/nasdaq
```

### 示例 6：获取黄金价格预测

**HTTP API 调用:**
```bash
curl -X POST http://localhost:8000/api/gold/predict \
  -H "Content-Type: application/json" \
  -d '{"symbol": "GC", "horizon_days": 1}'
```

**预期返回:**
```json
{
  "success": true,
  "data": {
    "current_price": 4500.00,
    "predictions": [
      {
        "model_type": "xgboost",
        "predicted_price": 4567.74,
        "predicted_change_percent": 1.51,
        "directional_accuracy": 0.405
      },
      {
        "model_type": "lstm",
        "predicted_price": 4517.98,
        "predicted_change_percent": 0.40,
        "directional_accuracy": 0.391
      },
      {
        "model_type": "transformer",
        "predicted_price": 4556.62,
        "predicted_change_percent": 1.26,
        "directional_accuracy": 0.391
      }
    ],
    "ensemble_prediction": {
      "predicted_price": 4547.45,
      "predicted_change_percent": 1.05,
      "confidence": 0.75
    }
  }
}
```

### 示例 7：获取当前黄金价格和宏观指标

**HTTP API 调用:**
```bash
curl http://localhost:8000/api/gold/current
```

**预期返回:**
```json
{
  "success": true,
  "data": {
    "gold_price": 4500.00,
    "gold_change_percent": 0.50,
    "dxy": 103.50,
    "vix": 18.50,
    "us10y": 4.25,
    "timestamp": "2026-03-23T10:00:00"
  }
}
```

### 示例 8：运行黄金预测模型回测

**HTTP API 调用:**
```bash
curl -X POST http://localhost:8000/api/gold/backtest \
  -H "Content-Type: application/json" \
  -d '{"years": 1, "model_types": "xgboost,lstm,transformer"}'
```

**预期返回:**
```json
{
  "success": true,
  "data": {
    "backtest_id": "bt_20260323_001",
    "period": {
      "start": "2025-03-23",
      "end": "2026-03-23"
    },
    "results": {
      "xgboost": {
        "total_return": 15.2,
        "annualized_return": 15.2,
        "max_drawdown": -8.5,
        "sharpe_ratio": 1.52,
        "win_rate": 58.3,
        "directional_accuracy": 52.1
      },
      "lstm": { ... },
      "transformer": { ... },
      "benchmark": { ... }
    }
  }
}
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

系统使用三种机器学习模型预测黄金价格：

| 模型 | 特点 | 适用场景 |
|------|------|----------|
| XGBoost | 梯度提升树，特征重要性分析 | 短期预测，捕捉非线性关系 |
| LSTM | 长短期记忆网络，序列建模 | 中期趋势，时间序列模式 |
| Transformer | 注意力机制，全局依赖 | 长期预测，复杂模式识别 |

**预测周期：**
- 1天：短期预测
- 5天：周度预测
- 20天：月度预测

**回测指标说明：**
- 总收益率：策略累计收益
- 年化收益率：年化后的平均收益
- 最大回撤：最大亏损幅度
- 夏普比率：风险调整后收益
- 胜率：盈利交易占比
- 方向准确率(DA)：预测方向准确率

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
5. **黄金预测**: 黄金价格预测基于历史数据和宏观因子，仅供参考，不构成投资建议
6. **模型回测**: 回测结果基于历史数据，不代表未来表现
7. **免责声明**: 估值数据和预测结果仅供参考，不构成投资建议

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

**问题：后端启动失败**
```bash
# 检查依赖是否安装
pip install -r requirements.txt

# 检查端口是否被占用
lsof -i :8000
```