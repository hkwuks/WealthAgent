# 智能理财 Agent

一个基于 FastAPI 和 TypeScript 的智能理财助手系统，集成基金估值、黄金量化交易、市场数据监控等功能，通过 MCP 与 AI 助手深度集成，提供全方位的理财决策支持。

## 功能特性

- **基金估值**：盘中实时计算基金估算净值和涨跌幅，支持多策略估值引擎
- **黄金量化**：基于策略引擎的趋势跟踪/均值回归/ML策略回测与交易信号
- **市场数据**：获取 A 股、港股、美股、指数实时行情
- **持仓管理**：添加、查看、删除基金持仓
- **批量估值**：支持 SSE 流式批量估值，实时返回每个基金的结果
- **趋势跟踪**：MA 交叉 + ATR 止损策略回测与实时信号
- **自动刷新**：可配置自动刷新间隔（30秒-10分钟）
- **数据持久化**：基金数据本地存储，刷新不丢失
- **MCP 集成**：支持 Model Context Protocol，AI 助手可直接调用系统功能
- **Skill**：AI 助手可通过 Skill 调用系统功能

## 技术栈

### 后端
- **FastAPI**：高性能异步 Web 框架
- **Pydantic**：数据验证和序列化
- **AkShare**：中国金融数据接口
- **yFinance**：Yahoo Finance 数据接口（国际市场）
- **LightGBM / XGBoost / Ridge**：机器学习预测模型
- **aiohttp**：异步 HTTP 客户端
- **Loguru**：日志记录
- **httpx**：异步 HTTP 客户端
- **MCP**：Model Context Protocol 服务器

### 前端
- **TypeScript**：类型安全的 JavaScript
- **Vite**：现代前端构建工具
- **原生 JavaScript**：无框架依赖，轻量高效

## 安装和运行

### 环境要求
- Python 3.11+
- Node.js 16+

### 后端

1. 创建并激活 conda 环境：
```bash
conda create -n wealth_agent python=3.11
conda activate wealth_agent
```

2. 安装依赖：
```bash
pip install -r requirements.txt
```

3. 启动后端服务：
```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

服务将在 http://localhost:8000 启动，API 文档访问 http://localhost:8000/docs

**注意**: 启动后端服务时，MCP 服务器会自动同时启动，无需额外操作。

### 前端

1. 进入前端目录并安装依赖：
```bash
cd frontend
npm install
```

2. 启动开发服务器：
```bash
npm run dev
```

前端开发服务器默认在 http://localhost:3000 启动

## 使用说明

1. 访问 http://localhost:3000 打开前端界面
2. **基金管理**标签页：
   - 输入基金代码，点击"查询"自动获取基金信息
   - 设置持有份额，点击"添加基金"
   - 点击"刷新估值"更新所有基金估值
   - 选择自动刷新间隔
3. **基金估值**标签页：
   - 单个基金估值：输入基金代码进行估值
   - 批量基金估值：输入多个基金代码批量估值
4. **基金信息**标签页：查看基金详细持仓和历史净值
5. **市场数据**标签页：监控股票、ETF、指数实时行情
6. **黄金量化**标签页：策略回测、多策略对比、机器学习策略交易信号

## 估值策略

系统根据基金类型和数据可用性自动选择最优估值策略：

| 估值类型 | 估值方法 | 置信度 | 适用基金 |
|----------|----------|--------|----------|
| `real_time_price` | 实时价格估值 | 100% | 场内 ETF、LOF |
| `index_based` | 指数估值 | 85% | 指数基金、ETF 联接基金 |
| `holdings_based` | 持仓估值 | 60-80% | 主动股票型、混合型基金 |
| `hybrid_bond` | 混合估值（债券+股票） | 70% | 偏债混合基金、二级债基 |
| `hybrid_qdii` | 混合估值（持仓+指数） | 70% | 主动管理型 QDII 基金 |
| `benchmark_only` | 业绩基准参考 | 30% | 无法获取持仓或指数的基金 |

### 计算公式

**持仓估值**：
```
估算净值 = 昨日净值 × (1 + Σ(持仓占比 × 股票涨跌幅))
```

**指数估值**：
```
估算净值 = 昨日净值 × (1 + 指数涨跌幅)
```

**混合估值（QDII）**：
```
估算净值 = 昨日净值 × (1 + 已知持仓贡献 + 剩余仓位×参考指数涨跌幅)
```

## 黄金量化策略

系统使用三种机器学习模型预测黄金价格：

| 模型 | 描述 |
|------|------|
| `lightgbm` | LightGBM 梯度提升树（默认） |
| `xgboost` | XGBoost 梯度提升树 |
| `ridge` | Ridge 线性回归基准 |

| 预测周期 | 参数值 | 说明 |
|----------|--------|------|
| 1天 | `horizon_days=1` | 短期预测 |
| 1周 | `horizon_days=5` | 周度预测 |
| 1月 | `horizon_days=20` | 月度预测 |

### 回测方法

| 方法 | 参数值 | 描述 |
|------|--------|------|
| Walk-Forward | `method=walk_forward` | 滚动窗口回测，带 Purging + Embargo |
| CPCV | `method=cpcv` | 组合清洗交叉验证，计算 PBO 过拟合指标 |

## API 文档

启动后端后访问 http://localhost:8000/docs 查看完整的 Swagger API 文档。

### 主要 API 端点

#### 基金管理
| 方法 | 端点 | 描述 |
|------|------|------|
| GET | `/api/funds` | 获取基金列表 |
| POST | `/api/funds/add` | 添加基金 |
| DELETE | `/api/funds/{fund_code}` | 删除基金 |
| GET | `/api/funds/query/{fund_code}` | 查询基金信息（从外部数据源） |
| GET | `/api/funds/{fund_code}/holdings` | 获取基金持仓 |
| GET | `/api/funds/{fund_code}/nav-history` | 获取净值历史 |

#### 估值计算
| 方法 | 端点 | 描述 |
|------|------|------|
| GET | `/api/valuation/{fund_code}` | 获取单个基金估值 |
| POST | `/api/valuation/batch` | 批量获取基金估值 |
| POST | `/api/valuation/batch/stream` | 流式批量估值（SSE） |
| GET | `/api/valuation/{fund_code}/detail` | 获取估值详情 |
| GET | `/api/valuation/{fund_code}/accuracy` | 验证估值准确性 |
| GET | `/api/valuation/info/types` | 获取估值类型说明 |

#### 黄金量化
| 方法 | 端点 | 描述 |
|------|------|------|
| POST | `/api/gold/predict` | 预测黄金价格 |
| POST | `/api/gold/predict-tb` | Triple-Barrier 方向预测 |
| POST | `/api/gold/backtest` | 模型回测 |
| POST | `/api/gold/backtest-trend` | 趋势跟踪策略回测 |
| GET | `/api/gold/trend-signal` | 当前趋势信号 |
| GET | `/api/gold/current` | 当前黄金价格与宏观指标 |
| GET | `/api/gold/factors` | 技术与宏观因子 |
| GET | `/api/gold/factor-importance` | 模型特征重要性 |
| GET | `/api/gold/drift-status` | 模型漂移检测 |
| POST | `/api/gold/sync` | 同步历史数据 |
| POST | `/api/gold/retrain` | 强制重新训练模型 |

#### 市场数据
| 方法 | 端点 | 描述 |
|------|------|------|
| GET | `/api/market/stock/{code}` | 获取股票行情 |
| GET | `/api/market/etf/{code}` | 获取 ETF 行情 |
| GET | `/api/market/index/{code}` | 获取国内指数行情 |
| GET | `/api/market/global-index/{code}` | 获取全球指数行情 |

## 项目结构

```
智能理财Agent/
├── backend/                    # 后端代码
│   ├── api/                   # API 路由
│   │   ├── funds.py          # 基金管理接口
│   │   ├── gold_trading.py   # 黄金量化交易接口
│   │   ├── valuation.py      # 估值计算接口
│   │   ├── market.py         # 市场数据接口
│   │   └── schemas.py        # API 响应模型
│   ├── mcp_server/           # MCP 服务器
│   │   ├── server.py        # MCP 服务器定义
│   │   ├── tools.py         # MCP Tools 实现
│   │   ├── resources.py     # MCP Resources 实现
│   │   └── prompts.py       # MCP Prompts 实现
│   ├── fund_service.py       # 基金业务逻辑
│   ├── fund_valuation.py     # 估值计算引擎
│   ├── gold/                # 黄金量化交易子系统
│   ├── backtest_engine.py    # 回测引擎
│   ├── data_sync.py          # 数据同步服务
│   ├── market_data.py        # 市场数据获取服务
│   ├── models.py             # Pydantic 数据模型
│   ├── config.py             # 应用配置
│   └── main.py               # FastAPI 应用入口
├── frontend/                   # 前端代码
│   ├── src/
│   │   ├── main.ts           # 应用入口
│   │   ├── api.ts            # API 客户端封装
│   │   ├── fundManager.ts    # 基金状态管理
│   │   ├── fundManagerUI.ts  # 基金管理界面
│   │   ├── valuationUI.ts    # 估值计算界面
│   │   ├── fundInfoUI.ts     # 基金信息界面

│   │   ├── marketDataUI.ts   # 市场数据界面
│   │   ├── types.ts          # TypeScript 类型定义
│   │   ├── style.css         # 样式文件
│   │   └── toast.ts          # 消息提示组件
│   ├── index.html            # HTML 入口
│   ├── package.json          # npm 依赖配置
│   └── vite.config.ts        # Vite 配置
├── data/                       # 数据存储
│   └── funds.json            # 基金持仓数据
├── logs/                       # 日志目录
├── skills/                     # AI Skill
│   ├── wealth-agent/         # 智能理财Agent技能
│   │   └── SKILL.md
│   └── fund-valuation/       # 基金估值技能（已合并至 wealth-agent）
│       ├── SKILL.md
│       └── REFERENCE.md
├── requirements.txt            # Python 依赖
├── CLAUDE.md                   # Claude Code 开发指南
└── README.md                   # 项目说明
```

## Skill

本项目包含智能理财 Agent Skill，让 AI 助手可以直接调用系统全部功能。

### Skill 位置

```
skills/wealth-agent/
└── SKILL.md        # 智能理财Agent技能使用指南
```

### Skill 功能

| 功能 | 描述 |
|------|------|
| 基金查询 | 获取基金信息、持仓、净值 |
| 实时估值 | 盘中实时估算基金净值和涨跌幅 |
| 持仓管理 | 添加/删除/查看持仓基金 |
| 市场数据 | 获取 A 股股票、ETF、指数行情 |
| 批量估值 | 同时估值多只基金 |
| 黄金量化 | 策略回测与交易信号 |
| 趋势信号 | MA 交叉趋势跟踪信号 |
| 模型回测 | Walk-Forward / CPCV 回测 |

### 使用方式

Skill 通过 HTTP API 调用系统功能，后端服务启动后，AI 助手可以自动执行：
- 查询基金信息和持仓
- 获取实时估值数据
- 监控市场行情
- 批量估值操作
- 预测黄金价格走势
- 运行模型回测
- 获取趋势跟踪信号

## MCP 服务

系统支持 MCP (Model Context Protocol) Streamable HTTP 模式，可与 AI 助手集成实现自动化操作。

### MCP 配置（Streamable HTTP 模式）

**配置方法**（以 Claude Code 为例）：

```bash
# 通过命令行添加 MCP 服务器
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

**前提条件**：后端 API 必须运行在 `http://127.0.0.1:8000`

```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

启动后端服务后，MCP 服务器会自动挂载到 `/mcp` 端点，支持 SSE 连接和 HTTP 消息传输。

### MCP Tools

#### 基金/市场工具（12个）

| Tool | 功能描述 |
|------|---------|
| `get_fund_list` | 获取持仓基金列表 |
| `add_fund` | 添加基金到持仓 |
| `delete_fund` | 删除持仓基金 |
| `get_fund_info` | 获取基金详细信息 |
| `get_valuation` | 获取基金实时估值 |
| `get_batch_valuation` | 批量获取基金估值 |
| `get_stock_price` | 获取 A 股股票行情 |
| `get_etf_price` | 获取场内 ETF 行情 |
| `get_index_price` | 获取国内指数行情 |
| `get_global_index_price` | 获取海外指数行情 |
| `get_valuation_types` | 获取估值类型说明 |
| `get_supported_indices` | 获取支持的指数列表 |

#### 黄金量化工具（14个）

| Tool | 功能描述 |
|------|---------|
| `predict_gold_price` | 预测黄金价格 |
| `predict_gold_tb` | Triple-Barrier 方向概率预测 |
| `retrain_gold_model` | 强制重新训练模型 |
| `get_gold_history` | 获取历史数据概况 |
| `sync_gold_data` | 同步历史数据 |
| `get_gold_current` | 当前价格与宏观指标 |
| `get_gold_factors` | 技术与宏观因子 |
| `get_gold_drift_status` | 模型漂移检测状态 |
| `record_gold_actual` | 记录实际涨跌方向 |
| `get_gold_factor_importance` | 特征重要性排名 |
| `get_gold_coverage` | 数据覆盖率统计 |
| `run_gold_backtest` | 模型回测 |
| `run_gold_backtest_trend` | 趋势跟踪策略回测 |
| `get_gold_trend_signal` | 当前趋势信号 |

### MCP Resources

- `fund://{fund_code}` - 基金详细信息
- `valuation://{fund_code}` - 基金实时估值
- `market://stock/{stock_code}` - 股票行情
- `market://etf/{etf_code}` - ETF 行情
- `market://index/{index_code}` - 国内指数行情
- `market://global-index/{index_code}` - 海外指数行情
- `gold://current` - 黄金当前价格与宏观指标
- `gold://signal` - 黄金趋势信号
- `gold://factors` - 黄金因子数据

### MCP Prompts

- `analyze_fund` - 分析单只基金投资价值
- `portfolio_summary` - 生成持仓组合总结报告
- `market_daily` - 生成市场日报

## 数据源

系统整合多个数据源，自动选择最优数据：

| 数据源 | 数据类型 | 说明 |
|--------|----------|------|
| 东方财富 | 基金信息、持仓、净值 | 主要数据源 |
| 天天基金 | 基金持仓 | 备用数据源 |
| AkShare | A股行情、ETF、指数、黄金现货 | 国内市场数据 |
| 新浪财经 | 股票行情 | 备用数据源 |
| 腾讯财经 | 股票行情 | 备用数据源 |
| yFinance | 全球指数、港股、COMEX黄金 | 国际市场数据 |

## 配置说明

### 后端配置 (backend/config.py)

```python
APP_NAME = "智能理财Agent"
APP_VERSION = "1.0.0"
DEBUG = True
API_PREFIX = "/api"
DATA_DIR = "data"
CORS_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]
```

### 前端配置

Vite 代理配置 (`frontend/vite.config.ts`)：
```typescript
server: {
  port: 3000,
  proxy: {
    '/api': {
      target: 'http://localhost:8000',
      changeOrigin: true
    }
  }
}
```

## 注意事项

1. **估值准确性**：估值数据仅供参考，实际净值以基金公司公布为准
2. **持仓时效性**：持仓数据来自季报，存在滞后性，会影响估值准确性
3. **QDII 估值**：QDII 基金投资海外市场，估值时间与 A 股不同步
4. **黄金量化**：策略回测基于历史数据，仅供参考，不构成投资建议
5. **网络依赖**：系统需要联网获取实时行情数据
6. **频率限制**：请合理设置刷新间隔，避免被数据源限制

## 开发计划

- [x] 基金增删改查
- [x] 实时估值计算
- [x] 多策略估值引擎
- [x] 批量估值（SSE 流式）
- [x] 市场数据监控
- [x] 自动刷新机制
- [x] 数据缓存
- [x] 估值方法显示
- [x] MCP 服务
- [x] Skill
- [x] 趋势跟踪策略
- [x] Walk-Forward / CPCV 回测
- [ ] 更多资产类别支持
- [ ] 投资组合优化

## 免责声明

本项目是一个个人科研项目，目的是为投资者提供理财决策参考服务。并不承诺数据的可靠性和准确性，用户在使用时请自行承担风险。估值数据和预测结果仅供参考，不构成任何投资建议。

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=hkwuks/Fund-Valuation-Framework&type=date&legend=top-left)](https://www.star-history.com/?repos=hkwuks%2FFund-Valuation-Framework&type=date&legend=top-left)
