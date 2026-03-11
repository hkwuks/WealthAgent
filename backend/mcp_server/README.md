# MCP 服务器开发文档

## 概述

本基金估值系统 MCP 服务器提供了完整的 Model Context Protocol (MCP) 接口，允许 AI 助手通过与后端 API 交互来获取基金信息、估值数据和市场行情。

## 架构设计

```
backend/mcp_server/
├── __init__.py          # 包初始化，导出公共接口
├── server.py            # MCP 服务器主模块，注册 Tools/Resources/Prompts
├── tools.py             # MCP Tools 实现，调用后端 API
├── resources.py         # MCP Resources 实现，提供 URI 资源访问
├── prompts.py           # MCP Prompts 实现，预定义提示词模板
├── run_server.py        # MCP 服务器启动脚本
└── test_mcp.py          # MCP 服务器测试脚本
```

## 依赖安装

```bash
# 安装 MCP 相关依赖
pip install mcp httpx

# 或者更新 requirements.txt
pip install -r requirements.txt
```

## 启动方式

### 方式 1: 独立启动 MCP 服务器

```bash
# 在项目根目录执行
python -m backend.mcp_server.run_server
```

### 方式 2: 通过 Claude Code 配置启动

在 `mcp_config.json` 中配置：

```json
{
  "mcpServers": {
    "fund-valuation-system": {
      "command": "python",
      "args": ["-m", "backend.mcp_server.run_server"],
      "cwd": "<PROJECT_ROOT>",
      "env": {
        "PYTHONPATH": "<PROJECT_ROOT>"
      }
    }
  }
}
```

### 方式 3: 在 Claude Desktop 中使用

将配置添加到 Claude Desktop 配置文件中：
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

## MCP Tools

| Tool 名称 | 功能描述 | 参数 |
|----------|---------|------|
| `get_fund_list` | 获取持仓基金列表 | 无 |
| `add_fund` | 添加基金到持仓 | `fund_code`, `fund_name`, `fund_type`, `total_shares` |
| `delete_fund` | 从持仓删除基金 | `fund_code` |
| `get_fund_info` | 获取基金详细信息 | `fund_code` |
| `get_valuation` | 获取基金实时估值 | `fund_code`, `prefer_holdings` (可选) |
| `get_batch_valuation` | 批量获取基金估值 | `fund_codes`, `prefer_holdings` (可选) |
| `get_stock_price` | 获取 A 股股票行情 | `stock_code` |
| `get_etf_price` | 获取场内 ETF 行情 | `etf_code` |
| `get_index_price` | 获取国内指数行情 | `index_code` |
| `get_global_index_price` | 获取海外指数行情 | `index_code` |
| `get_valuation_types` | 获取估值类型说明 | 无 |
| `get_supported_indices` | 获取支持的指数列表 | 无 |

### 使用示例

```python
# 获取基金估值
result = await tools.get_valuation("110022")
print(result)

# 批量估值
result = await tools.get_batch_valuation(["110022", "510300", "159915"])
print(result)

# 获取股票价格
result = await tools.get_stock_price("600519")
print(result)
```

## MCP Resources

| Resource URI | 功能描述 |
|-------------|---------|
| `fund://{fund_code}` | 获取基金详细信息 |
| `valuation://{fund_code}` | 获取基金实时估值 |
| `market://stock/{stock_code}` | 获取股票行情 |
| `market://etf/{etf_code}` | 获取 ETF 行情 |
| `market://index/{index_code}` | 获取国内指数行情 |
| `market://global-index/{index_code}` | 获取海外指数行情 |

### 使用示例

```python
# 读取基金资源
resource = await resources.get_fund_resource("110022")
print(resource)

# 读取估值资源
resource = await resources.get_valuation_resource("110022")
print(resource)
```

## MCP Prompts

| Prompt 名称 | 功能描述 | 参数 |
|------------|---------|------|
| `analyze_fund` | 分析单只基金投资价值 | `fund_code` |
| `portfolio_summary` | 生成持仓组合总结报告 | 无 |
| `market_daily` | 生成市场日报 | 无 |

### 使用示例

```python
prompts = FundValuationPrompts()

# 基金分析提示词
prompt = prompts.analyze_fund("110022")
print(prompt)

# 持仓总结提示词
prompt = prompts.portfolio_summary()
print(prompt)

# 市场日报提示词
prompt = prompts.market_daily()
print(prompt)
```

## 测试

### 运行测试脚本

```bash
# 在项目根目录执行
python backend/mcp_server/test_mcp.py
```

### 测试内容

测试脚本会依次测试：
1. `get_fund_list` - 获取基金列表
2. `get_valuation_types` - 获取估值类型
3. `get_supported_indices` - 获取指数列表
4. `get_fund_info` - 获取基金信息
5. `get_valuation` - 获取基金估值
6. `get_batch_valuation` - 批量估值
7. `get_stock_price` - 获取股票价格
8. `get_etf_price` - 获取 ETF 价格
9. `get_index_price` - 获取指数价格
10. `get_global_index_price` - 获取海外指数价格

## API 依赖

MCP 服务器依赖于后端 FastAPI 服务运行。请确保先启动后端服务：

```bash
# 启动后端服务
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

后端服务启动后，MCP 服务器会自动通过 HTTP 调用后端 API。

## 配置说明

### 环境变量

| 变量名 | 说明 | 默认值 |
|-------|------|-------|
| `API_BASE_URL` | 后端 API 地址 | `http://127.0.0.1:8000/api` |

### 修改 API 地址

如果需要修改后端 API 地址，可以在 `tools.py` 和 `resources.py` 中修改 `API_BASE_URL` 常量：

```python
API_BASE_URL = "http://your-server:port/api"
```

## 扩展开发

### 添加新的 Tool

1. 在 `tools.py` 中添加方法：

```python
async def get_fund_nav_history(self, fund_code: str, days: int = 30) -> dict:
    """获取基金历史净值"""
    try:
        result = await self._request("GET", f"/funds/{fund_code}/nav/history?days={days}")
        return result
    except Exception as e:
        logger.error(f"获取基金历史净值失败：{e}")
        return {"success": False, "message": f"获取基金历史净值失败：{str(e)}"}
```

2. 在 `server.py` 中注册：

```python
@mcp.tool()
async def get_fund_nav_history(fund_code: str, days: int = 30) -> dict:
    """获取基金历史净值"""
    return await FundValuationTools().get_fund_nav_history(fund_code, days)
```

### 添加新的 Resource

1. 在 `resources.py` 中添加方法：

```python
async def get_fund_holdings_resource(self, fund_code: str) -> str:
    """获取基金持仓资源"""
    # 实现代码
```

2. 在 `server.py` 中注册：

```python
@mcp.resource("fund://{fund_code}/holdings")
async def get_fund_holdings_resource(fund_code: str) -> str:
    """获取基金持仓资源"""
    return await FundValuationResources().get_fund_holdings_resource(fund_code)
```

### 添加新的 Prompt

1. 在 `prompts.py` 中添加方法：

```python
def compare_funds(self, fund_code1: str, fund_code2: str) -> str:
    """对比两只基金"""
    return f"""请对比基金 {fund_code1} 和 {fund_code2} ..."""
```

2. 在 `server.py` 中注册：

```python
@mcp.prompt()
def compare_funds(fund_code1: str, fund_code2: str) -> str:
    """对比两只基金"""
    return FundValuationPrompts().compare_funds(fund_code1, fund_code2)
```

## 故障排除

### 问题：MCP 服务器无法启动

检查：
1. Python 环境是否安装了 `mcp` 和 `httpx`
2. 后端服务是否正在运行
3. 日志文件中是否有错误信息

### 问题：Tool 调用返回空数据

检查：
1. 后端 API 地址是否正确
2. 网络连接是否正常
3. 基金代码是否有效

### 问题：Resource 无法读取

检查：
1. URI 格式是否正确
2. 后端 API 是否返回有效数据
3. 日志中是否有错误信息

## 版本历史

- v1.0.0 (2026-03-11): 初始版本
  - 实现 12 个 MCP Tools
  - 实现 6 个 MCP Resources
  - 实现 3 个 MCP Prompts
