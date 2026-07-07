<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://img.shields.io/badge/智能理财Agent-v1.0-1a1a2e?style=for-the-badge&logo=python&logoColor=gold">
    <img src="https://img.shields.io/badge/智能理财Agent-v1.0-1a1a2e?style=for-the-badge&logo=python&logoColor=gold">
  </picture>
</p>

<p align="center">
  <b>WealthWise · 智能理财 Agent</b><br>
  基金估值 · 黄金量化 · 市场数据 · AI 驱动
</p>

<p align="center">
  <a href="#核心功能"><img src="https://img.shields.io/badge/功能-Features-22c55e?style=flat-square"></a>
  <a href="#技术栈"><img src="https://img.shields.io/badge/技术栈-Tech-3b82f6?style=flat-square"></a>
  <a href="#快速开始"><img src="https://img.shields.io/badge/开始-Get%20Started-eab308?style=flat-square"></a>
  <a href="#估值策略"><img src="https://img.shields.io/badge/估值-Valuation-a855f7?style=flat-square"></a>
  <a href="#黄金量化交易"><img src="https://img.shields.io/badge/黄金-Gold-f59e0b?style=flat-square"></a>
  <a href="#api-文档"><img src="https://img.shields.io/badge/API-文档-06b6d4?style=flat-square"></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white">
  <img src="https://img.shields.io/badge/TypeScript-5-3178C6?style=flat-square&logo=typescript&logoColor=white">
  <img src="https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi&logoColor=white">
  <img src="https://img.shields.io/badge/Vite-6-646CFF?style=flat-square&logo=vite&logoColor=white">
  <img src="https://img.shields.io/badge/License-MIT-brightgreen?style=flat-square">
  <img src="https://img.shields.io/badge/MCP-Enabled-7c3aed?style=flat-square">
</p>

<p align="center">
  <i>一个基于 FastAPI + TypeScript 的全方位智能理财助手系统。<br>
  集成基金盘中实时估值、黄金期货量化交易、多源市场数据监控，<br>
  通过 MCP 和 Skill 与 AI 助手深度集成，提供专业的理财决策支持。</i>
</p>

<hr>

## 📋 目录

- [核心功能](#-核心功能)
- [技术栈](#-技术栈)
- [快速开始](#-快速开始)
- [估值策略](#-估值策略)
- [黄金量化交易](#-黄金量化交易)
- [项目结构](#-项目结构)
- [API 文档](#-api-文档)
- [MCP 集成](#-mcp-集成)
- [Skill 系统](#-skill-系统)
- [数据源](#-数据源)
- [配置说明](#-配置说明)
- [注意事项](#-注意事项)
- [开发计划](#-开发计划)
- [免责声明](#-免责声明)

---

## 🚀 核心功能

<table>
<tr>
<td width="50%">

### 📊 基金估值
盘中实时计算基金估算净值和涨跌幅，支持**多策略估值引擎**，根据基金类型自动选择最优算法：
- 场内 ETF / LOF 实时价格
- 指数基金 / ETF 联接
- 主动股票型 / 混合型持仓估值
- 偏债混合 / QDII 混合估值
- 业绩基准参考

</td>
<td width="50%">

### 🥇 黄金量化
SHFE AU 黄金期货全流程量化交易子系统：
- 趋势跟踪（双均线 + ATR 止损）
- 均值回归（RSI + 布林带）
- ML 预测（LightGBM / XGBoost / Ridge）
- Walk-Forward / CPCV 回测验证
- Triple-Barrier 序列标注

</td>
</tr>
<tr>
<td>

### 📈 市场数据
多源数据聚合，实时行情一网打尽：
- A 股、港股、美股实时行情
- 国内外指数（沪深300、标普500等）
- 场内 ETF / LOF 行情
- 黄金现货 / COMEX 黄金

</td>
<td>

### 🤖 AI 集成
双通道 AI 助手集成方案：
- **MCP 协议**：33+ 个 Tool，覆盖基金、黄金、市场全功能
- **Skill 系统**：AI 助手可直接调用的智能理财技能
- 支持基金分析、持仓总结、市场日报等 Prompt

</td>
</tr>
</table>

#### 🎯 更多特性

| 特性 | 说明 |
|------|------|
| ⚡ **批量估值** | SSE 流式批量估值，实时返回每个基金结果 |
| 🔄 **自动刷新** | 可配置 30s – 10min 自动刷新间隔 |
| 💾 **数据持久化** | 基金数据本地存储，刷新不丢失 |
| 🛡️ **风控体系** | VaR / 波动率 / 回撤 / 信号频率实时监控 |
| 📦 **无框架前端** | 原生 TypeScript，零依赖，轻量高效 |

---

## 🛠 技术栈

### Backend

| 类别 | 技术 |
|------|------|
| **框架** | [FastAPI](https://fastapi.tiangolo.com/) + Pydantic |
| **数据** | [AkShare](https://akshare.akfamily.xyz/) · [yFinance](https://github.com/ranaroussi/yfinance) · aiohttp · httpx |
| **ML** | LightGBM · XGBoost · scikit-learn (Ridge) |
| **回测** | Walk-Forward · CPCV · Monte Carlo · Triple-Barrier |
| **日志** | Loguru |
| **协议** | MCP (Model Context Protocol) Streamable HTTP |

### Frontend

| 类别 | 技术 |
|------|------|
| **语言** | TypeScript 5 |
| **构建** | Vite 6 |
| **设计** | 原生 DOM 操作 · CSS 自定义属性 |

---

## 🏁 快速开始

### 环境要求

- **Python** ≥ 3.11
- **Node.js** ≥ 16
- **网络** — 需要联网获取实时行情

### 后端启动

```bash
# 创建并激活 conda 环境
conda create -n wealth_agent python=3.11
conda activate wealth_agent

# 安装依赖
pip install -r requirements.txt

# 启动服务（MCP 服务器自动随同启动）
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

✅ 服务启动于 `http://localhost:8000`  
📖 Swagger API 文档：`http://localhost:8000/docs`

### 前端启动

```bash
cd frontend
npm install
npm run dev
```

✅ 开发服务器默认运行于 `http://localhost:3000`

> **提示**：Vite 已配置代理，`/api` 请求自动转发至后端 `localhost:8000`。

### 使用流程

1. 访问 `http://localhost:3000` 打开界面
2. **基金管理** → 输入基金代码查询 → 设置份额 → 添加
3. **基金估值** → 点击"刷新估值"查看实时估算
4. **市场数据** → 监控股票 / ETF / 指数行情
5. **黄金量化** → 策略回测 / 信号生成 / 风控监控

---

## 📐 估值策略

系统根据基金类型和数据可用性，**自动选择最优估值策略**：

| 策略 | 置信度 | 适用基金 |
|------|:------:|----------|
| `real_time_price` — 实时价格 | **100%** | 场内 ETF、LOF |
| `index_based` — 指数跟踪 | **85%** | 指数基金、ETF 联接 |
| `holdings_based` — 持仓加权 | **60–80%** | 主动股票型、混合型 |
| `hybrid_bond` — 债券+股票混合 | **70%** | 偏债混合、二级债基 |
| `hybrid_qdii` — 持仓+指数混合 | **70%** | 主动管理型 QDII |
| `benchmark_only` — 基准参考 | **30%** | 无法获取持仓 / 指数的基金 |

### 计算公式

```
持仓估值： 估算净值 = 昨日净值 × (1 + Σ(持仓占比 × 股票涨跌幅))
指数估值： 估算净值 = 昨日净值 × (1 + 指数涨跌幅)
QDII 混合：估算净值 = 昨日净值 × (1 + 已知持仓贡献 + 剩余仓位 × 参考指数涨跌幅)
```

---

## 🥇 黄金量化交易

基于 FastAPI 的黄金期货量化交易子系统，覆盖从策略研发到实盘信号的全流程。

### 内置策略

| 策略 | 类型 | 核心逻辑 |
|------|------|----------|
| `trend_following` | 趋势跟踪 | 5/20 双均线交叉 + ATR 动态止损 |
| `mean_reversion` | 均值回归 | RSI 超买超卖 + 布林带位置判断 |
| `ml_predictor` | ML 预测 | LightGBM/XGBoost/Ridge 滑动窗口预测 |

### 回测引擎特性

| 特性 | 说明 |
|------|------|
| **成本模型** | 固定滑点 + ATR 动态滑点 + 手续费 |
| **部分成交** | `fill_ratio` 参数模拟流动性不足 |
| **交易延时** | `execution_delay` 参数模拟成交延迟 |
| **Walk-Forward** | 滚动窗口回测，Purging + Embargo 防前视偏差 |
| **CPCV** | 组合清洗交叉验证，计算 PBO 过拟合概率 |
| **Monte Carlo** | Bootstrap 重采样，95% 置信区间风险估计 |
| **Benchmark** | 买入持有基准对比，信息比率 / 跟踪误差 |
| **Triple-Barrier** | López de Prado 三屏障序列标注（ML 策略） |
| **合约展期** | SHFE AU 主力合约前向 / 后向调整 |

### 风控体系

| 检查项 | 🔶 Warning | 🔴 Reject |
|--------|:----------:|:---------:|
| 当日回撤 > 总资产 | 5% | 10% |
| 单日亏损 > 总资产 | 2% | 5% |
| VaR(95%) > 总资产 | 5% | 10% |
| ATR/价格 > | 5% | 10% |
| 信号频率 | 同方向 5 分钟内有信号 → 跳过 |

---

## 📁 项目结构

```
智能理财Agent/
├── backend/                    # FastAPI 后端
│   ├── api/                   # API 路由层
│   │   ├── funds.py          # 基金管理
│   │   ├── gold_trading.py   # 黄金量化
│   │   ├── valuation.py      # 估值计算
│   │   ├── market.py         # 市场数据
│   │   └── schemas.py        # 响应模型
│   ├── mcp_server/           # MCP 协议服务
│   │   ├── server.py         # 服务器定义
│   │   ├── tools.py          # 工具实现
│   │   ├── resources.py      # 资源实现
│   │   └── prompts.py        # 提示词实现
│   ├── gold/                 # 黄金量化子系统
│   │   ├── core/             # 模型 · 配置 · 异常
│   │   ├── strategy/         # 策略基类 + 内置策略
│   │   ├── backtest/         # 回测引擎 · 报告 · MC
│   │   ├── data/             # 数据网关 · 存储 · 标签 · 展期
│   │   ├── risk/             # 风控 · 订单管理
│   │   ├── signal/           # 信号输出
│   │   └── ml/               # 特征工程 · 训练 · 预测
│   ├── fund_service.py       # 基金业务逻辑
│   ├── fund_valuation.py     # 估值引擎
│   ├── market_data.py        # 市场数据服务
│   ├── data_sync.py          # 数据同步
│   ├── models.py             # 数据模型
│   ├── config.py             # 应用配置
│   └── main.py               # 应用入口
├── frontend/                   # Vite + TypeScript 前端
│   ├── src/
│   │   ├── main.ts           # 入口
│   │   ├── api.ts            # API 客户端
│   │   ├── types.ts          # 类型定义
│   │   ├── fundManager.ts    # 基金状态管理
│   │   ├── fundManagerUI.ts  # 基金管理界面
│   │   ├── valuationUI.ts    # 估值界面
│   │   ├── fundInfoUI.ts     # 基金信息界面
│   │   ├── marketDataUI.ts   # 市场数据界面
│   │   ├── style.css         # 样式
│   │   └── toast.ts          # 消息提示
│   ├── index.html
│   ├── package.json
│   └── vite.config.ts
├── data/                       # 持久化数据
│   └── backend/
│       └── funds.json
├── logs/                       # 运行日志
├── skills/                     # AI 技能
│   └── wealth-agent/
│       └── SKILL.md
├── requirements.txt
├── CLAUDE.md
└── README.md
```

---

## 📖 API 文档

启动后端后访问 [http://localhost:8000/docs](http://localhost:8000/docs) 查看完整的 Swagger 交互式文档。

### 基金管理

| 方法 | 端点 | 描述 |
|:----:|:-----|:-----|
| `GET` | `/api/funds` | 获取基金列表 |
| `POST` | `/api/funds/add` | 添加基金 |
| `DELETE` | `/api/funds/{fund_code}` | 删除基金 |
| `GET` | `/api/funds/query/{fund_code}` | 从外部数据源查询基金信息 |
| `GET` | `/api/funds/{fund_code}/holdings` | 获取基金持仓 |
| `GET` | `/api/funds/{fund_code}/nav-history` | 获取净值历史 |

### 估值计算

| 方法 | 端点 | 描述 |
|:----:|:-----|:-----|
| `GET` | `/api/valuation/{fund_code}` | 单个基金估值 |
| `POST` | `/api/valuation/batch` | 批量估值 |
| `POST` | `/api/valuation/batch/stream` | **SSE 流式**批量估值 |
| `GET` | `/api/valuation/{fund_code}/detail` | 估值详情 |
| `GET` | `/api/valuation/{fund_code}/accuracy` | 估值准确性验证 |
| `GET` | `/api/valuation/info/types` | 估值类型说明 |

### 黄金量化（21 个端点）

| 方法 | 端点 | 描述 |
|:----:|:-----|:-----|
| `GET` | `/api/gold/trading/status` | 系统状态 |
| `GET` | `/api/gold/trading/strategies` | 策略列表 |
| `GET` | `/api/gold/trading/strategies/{name}` | 策略详情 |
| `POST` | `/api/gold/trading/backtest` | 单策略回测 |
| `POST` | `/api/gold/trading/compare` | 多策略对比 |
| `POST` | `/api/gold/trading/backtest/sensitivity` | 参数敏感性分析 |
| `POST` | `/api/gold/trading/backtest/validation` | 策略验证 |
| `POST` | `/api/gold/trading/backtest/walk-forward` | Walk-Forward 回测 |
| `POST` | `/api/gold/trading/backtest/cpcv` | CPCV 回测 |
| `POST` | `/api/gold/trading/backtest/monte-carlo` | Monte Carlo 模拟 |
| `GET` | `/api/gold/trading/signals` | 交易信号 |
| `POST` | `/api/gold/trading/signal/generate` | 生成信号 |
| `GET` | `/api/gold/trading/risk/status` | 风控状态 |
| `GET` | `/api/gold/trading/market-data` | 市场数据仪表盘 |
| `GET` | `/api/gold/trading/analysis` | 技术分析 |
| `GET` | `/api/gold/trading/feature-importance` | 特征重要性 |
| `POST` | `/api/gold/trading/label/triple-barrier` | Triple-Barrier 标注 |
| `POST` | `/api/gold/trading/sync-data` | 数据同步 |
| `GET` | `/api/gold/trading/bars` | K 线数据 |
| `GET` | `/api/gold/trading/config` | 配置信息 |
| `GET` | `/api/gold/trading/strategy-comparison` | 策略适配度对比 |

### 市场数据

| 方法 | 端点 | 描述 |
|:----:|:-----|:-----|
| `GET` | `/api/market/stock/{code}` | A 股股票行情 |
| `GET` | `/api/market/etf/{code}` | 场内 ETF 行情 |
| `GET` | `/api/market/index/{code}` | 国内指数行情 |
| `GET` | `/api/market/global-index/{code}` | 全球指数行情 |

---

## 🔌 MCP 集成

系统支持 **MCP (Model Context Protocol) Streamable HTTP** 模式，AI 助手可直接调用全部功能。

### MCP 配置

```bash
# Claude Code
claude mcp add http wealth-agent http://127.0.0.1:8000/mcp
```

或在 `~/.claude/mcp.json` 中添加：

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

> **前提**：后端必须运行在 `http://127.0.0.1:8000`

### MCP 工具一览

**基金 / 市场（12 个）**

| Tool | 功能 |
|:-----|:-----|
| `get_fund_list` | 持仓基金列表 |
| `add_fund` | 添加基金到持仓 |
| `delete_fund` | 删除持仓基金 |
| `get_fund_info` | 基金详细信息 |
| `get_valuation` | 实时估值 |
| `get_batch_valuation` | 批量估值 |
| `get_stock_price` | A 股行情 |
| `get_etf_price` | ETF 行情 |
| `get_index_price` | 国内指数行情 |
| `get_global_index_price` | 海外指数行情 |
| `get_valuation_types` | 估值类型说明 |
| `get_supported_indices` | 支持的指数列表 |

**黄金量化（18 个）**

| Tool | 功能 |
|:-----|:-----|
| `get_gold_status` | 系统状态 |
| `get_gold_strategies` | 策略列表 |
| `get_gold_strategy_detail` | 策略详情 |
| `get_gold_signals` | 交易信号 |
| `generate_gold_signal` | 触发信号生成 |
| `run_gold_strategy_backtest` | 单策略回测 |
| `compare_gold_strategies` | 多策略对比 |
| `run_gold_sensitivity` | 参数敏感性分析 |
| `run_gold_validation` | 策略验证 |
| `run_gold_walk_forward` | Walk-Forward 回测 |
| `run_gold_cpcv` | CPCV 交叉验证 |
| `run_gold_monte_carlo` | Monte Carlo 模拟 |
| `get_gold_risk_status` | 风控状态 |
| `get_gold_market_data` | 市场数据 |
| `get_gold_analysis` | K 线技术分析 |
| `get_gold_feature_importance` | 特征重要性 |
| `run_gold_triple_barrier_label` | Triple-Barrier 标注 |
| `get_gold_config` | 配置信息 |

### MCP Resources

```
fund://{fund_code}              → 基金详细信息
valuation://{fund_code}          → 基金实时估值
market://stock/{stock_code}      → 股票行情
market://etf/{etf_code}          → ETF 行情
market://index/{index_code}      → 国内指数行情
market://global-index/{code}     → 海外指数行情
```

### MCP Prompts

| Prompt | 用途 |
|:-------|:-----|
| `analyze_fund` | 分析单只基金投资价值 |
| `portfolio_summary` | 持仓组合总结报告 |
| `market_daily` | 市场日报生成 |

---

## 🧠 Skill 系统

AI 助手可通过 **Skill** 直接调用系统全部功能，无需手动构造 HTTP 请求。

```
skills/wealth-agent/
└── SKILL.md         # 智能理财 Agent 技能指南
```

| 功能 | 描述 |
|:-----|:-----|
| 🔍 基金查询 | 基金信息、持仓、净值 |
| 📊 实时估值 | 盘中实时估算净值 / 涨跌幅 |
| 📋 持仓管理 | 添加 / 删除 / 查看持仓 |
| 📈 市场数据 | 股票、ETF、指数行情 |
| 🔄 批量估值 | 多基金同时估值 |
| 🥇 黄金量化 | 回测、对比、交易信号 |
| 🛡️ 风控状态 | VaR / 波动率 / 回撤实时监控 |
| 📉 技术分析 | K 线技术指标解读 |

---

## 🌐 数据源

系统整合多数据源，自动选择最优可用数据：

| 数据源 | 数据类型 | 角色 |
|:-------|:---------|:----:|
| 东方财富 | 基金信息 · 持仓 · 净值 | ⭐ 主要 |
| 天天基金 | 基金持仓 | 🔄 备用 |
| AkShare | A 股行情 · ETF · 指数 · 黄金现货 | ⭐ 主要 |
| 新浪财经 | 股票行情 | 🔄 备用 |
| 腾讯财经 | 股票行情 | 🔄 备用 |
| yFinance | 全球指数 · 港股 · COMEX 黄金 | ⭐ 主要 |

---

## ⚙️ 配置说明

### 后端 (`backend/config.py`)

```python
APP_NAME     = "智能理财Agent"
APP_VERSION  = "1.0.0"
DEBUG        = True
API_PREFIX   = "/api"
DATA_DIR     = "data"
CORS_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]
```

### 前端 (`frontend/vite.config.ts`)

```typescript
server: {
  port: 3000,
  proxy: {
    '/api': { target: 'http://localhost:8000', changeOrigin: true }
  }
}
```

---

## ⚠️ 注意事项

| # | 提醒 |
|:--:|:-----|
| 1 | **估值 ≠ 实际净值** — 估算数据仅供参考，以基金公司公布为准 |
| 2 | **持仓滞后** — 持仓数据来自季报，存在时滞，影响估值准确性 |
| 3 | **QDII 时差** — QDII 投资海外市场，估值时间与 A 股不同步 |
| 4 | **历史不代表未来** — 回测基于历史数据，不构成投资建议 |
| 5 | **ML 置信度** — R² 为负时模型预测置信度降低 |
| 6 | **网络依赖** — 需要联网获取实时行情 |
| 7 | **频率限制** — 请合理设置刷新间隔，避免被数据源限制 |

---

## 📌 开发计划

- [x] 基金增删改查
- [x] 实时估值计算 · 多策略引擎
- [x] 批量估值（SSE 流式）
- [x] 市场数据监控 · 自动刷新 · 数据缓存
- [x] MCP 服务 · Skill 系统
- [x] 趋势跟踪 / 均值回归 / ML 策略
- [x] Walk-Forward / CPCV / Monte Carlo 回测
- [x] Triple-Barrier 标注 · 合约展期处理
- [x] 风控体系（VaR / 波动率 / 回撤 / 频率）
- [ ] 更多资产类别支持
- [ ] 投资组合优化

---

## ⭐ Star History

[![Star History Chart](https://api.star-history.com/svg?repos=hkwuks/Fund-Valuation-Framework&type=date&legend=top-left)](https://www.star-history.com/?repos=hkwuks%2FFund-Valuation-Framework&type=date&legend=top-left)

---

## 📜 免责声明

> 本项目是一个**个人科研项目**，旨在为投资者提供理财决策参考服务。  
> 并不承诺数据的可靠性和准确性，用户在使用时请**自行承担风险**。  
> **估值数据和预测结果仅供参考，不构成任何投资建议。**

---

<p align="center">
  <sub>Built with ⚡ by <a href="https://github.com/hkwuks">hkwuks</a></sub>
  <br>
  <sub>© 2026 智能理财 Agent · WealthWise</sub>
</p>
