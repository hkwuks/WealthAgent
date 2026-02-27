# 基金估值系统

一个基于 FastAPI 和 TypeScript 的基金估值可视化系统，通过实时获取股票、基金、指数价格来计算基金的估算净值。

## 功能特性

- 基金管理：添加、查看、删除基金
- 持仓管理：管理基金的持仓明细
- 实时行情：集成多个数据源获取实时价格
- 估值计算：基于持仓实时价格计算基金估算净值
- 可视化展示：直观展示基金信息和估值结果

## 技术栈

### 后端
- **FastAPI**: 高性能异步 Web 框架
- **Pydantic**: 数据验证和序列化
- **AkShare**: 中国金融数据接口（股票、基金、指数）
- **yFinance**: Yahoo Finance 数据接口（国际市场）
- **Loguru**: 日志记录
- **aiohttp**: 异步 HTTP 客户端

### 前端
- TypeScript：类型安全的JavaScript
- Vite：现代前端构建工具
- 原生JavaScript：无复杂框架依赖

## 安装和运行

### 环境要求
- Python 3.8+
- Node.js 16+

### 后端

1. 创建并激活 conda 环境：
```bash
conda create -n your_env_name
conda activate your_env_name  # 或使用其他环境
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

3. 构建生产版本：
```bash
npm run build
```

前端开发服务器默认在 http://localhost:3000 启动

## 使用说明

1. 访问 http://localhost:3000 打开前端界面
2. **基金管理**标签页：
   - 输入基金代码，点击"查询"自动获取基金信息
   - 设置持有份额，点击"添加基金"
   - 选择自动刷新间隔（30秒-10分钟）
   - 点击"刷新数据"手动更新估值
3. **基金估值**标签页：查看所有基金的实时估值情况
4. **基金信息**标签页：查看基金详细持仓和历史净值
5. **市场数据**标签页：监控股票、指数实时行情

## 数据源

系统支持以下数据源：
- AkShare：中国股票、基金、指数数据
- yFinance：国际市场数据
- 东方财富网
- 腾讯财经
- 新浪财经
- 汇丰

## API文档

启动后端后访问 http://localhost:8000/docs 查看完整的 Swagger API 文档。

### 主要 API 端点

- `GET /api/v1/funds` - 获取基金列表
- `POST /api/v1/funds/add` - 添加基金
- `DELETE /api/v1/funds/{fund_code}` - 删除基金
- `GET /api/v1/funds/{fund_code}` - 获取基金详情
- `POST /api/v1/valuation/batch` - 批量估值计算
- `GET /api/v1/market/stock/{code}` - 获取股票行情
- `GET /api/v1/market/index/{code}` - 获取指数数据

## 项目结构

```
基金估值/
├── backend/                    # 后端代码
│   ├── api/                   # API 路由
│   │   ├── funds.py          # 基金相关接口
│   │   ├── valuation.py      # 估值相关接口
│   │   ├── market.py         # 市场数据接口
│   │   └── schemas.py        # Pydantic 模型
│   ├── fund_service.py       # 基金业务逻辑
│   ├── fund_valuation.py     # 估值计算引擎
│   ├── market_data.py        # 市场数据获取
│   ├── models.py             # 数据模型
│   ├── config.py             # 配置文件
│   └── main.py               # 应用入口
├── frontend/                   # 前端代码
│   ├── src/
│   │   ├── main.ts           # 应用入口
│   │   ├── api.ts            # API 客户端
│   │   ├── fundManagerUI.ts  # 基金管理界面
│   │   ├── valuationUI.ts    # 估值界面
│   │   ├── fundInfoUI.ts     # 基金信息界面
│   │   ├── marketDataUI.ts   # 市场数据界面
│   │   ├── fundManager.ts    # 基金管理逻辑
│   │   ├── storage.ts        # 本地存储
│   │   ├── types.ts          # TypeScript 类型
│   │   ├── utils.ts          # 工具函数
│   │   ├── toast.ts          # 消息提示
│   │   └── style.css         # 样式文件
│   ├── index.html            # HTML 入口
│   ├── package.json          # 依赖配置
│   └── vite.config.ts        # Vite 配置
├── data/                       # 数据存储目录
│   └── funds.json            # 基金数据文件
├── logs/                       # 日志目录
├── requirements.txt            # Python 依赖
└── README.md                   # 项目说明
```

## 估值算法说明

系统根据数据可用性采用以下估值策略（按优先级排序）：

| 估值类型 | 置信度 | 说明 |
|----------|--------|------|
| real_time_price | 100% | 场内ETF实时交易价格 |
| index_based | 85% | 基于跟踪指数的实时涨跌幅估算 |
| holdings_based | 60-80% | 基于持仓股票的实时价格计算 |
| benchmark_only | 30% | 仅基于业绩基准指数估算 |

### 计算公式

**基于持仓的估值**：
```
估算净值 = 昨日净值 × (1 + Σ(持仓占比 × 股票涨跌幅))
```

**基于指数的估值**：
```
估算净值 = 昨日净值 × (1 + 指数涨跌幅 × 跟踪误差系数)
```

## 配置说明

### 后端配置 (backend/config.py)

```python
APP_NAME = "基金估值系统"      # 应用名称
APP_VERSION = "0.0.1"         # 版本号
DEBUG = False                 # 调试模式
API_PREFIX = "/api/v1"        # API 前缀
CORS_ORIGINS = ["*"]          # 跨域配置
```

### 前端配置

前端配置位于 `frontend/src/api.ts`：
```typescript
const API_BASE_URL = 'http://127.0.0.1:8000/api/v1'
```

## 开发计划

- [x] 基金增删改查
- [x] 实时估值计算
- [x] 市场数据监控
- [x] 自动刷新机制
- [x] 数据持久化
- [ ] 历史净值图表
- [ ] 收益率统计
- [ ] 多账户支持
- [ ] 数据导出功能

## 注意事项

1. **数据准确性**：估值数据仅供参考，实际净值以基金公司公布为准
2. **网络依赖**：系统需要联网获取实时行情数据
3. **频率限制**：频繁获取数据可能被数据源限制，请合理设置刷新间隔
4. **本地存储**：基金数据保存在浏览器本地存储中，清除浏览器数据会丢失

## 贡献指南

欢迎提交 Issue 和 Pull Request！

## 许可证

本项目基于 MIT 许可证开源，您可以在遵守许可证条款的前提下自由使用、修改和分发本项目的代码。

MIT License

## 说明

本项目是一个个人科研项目，目的是为大模型提供基金数据服务，并不承诺数据的可靠性和准确性，用户在使用时请自行承担风险。后续有MCP以及大模型接入等开发计划。
