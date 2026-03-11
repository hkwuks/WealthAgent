"""
MCP Server for Fund Valuation System

基金估值系统 MCP 服务器
提供基金查询、估值、市场数据等功能的 MCP 接口
"""

from backend.mcp_server.server import create_mcp_server
from backend.mcp_server.tools import FundValuationTools
from backend.mcp_server.resources import FundValuationResources
from backend.mcp_server.prompts import FundValuationPrompts

__all__ = [
    "create_mcp_server",
    "FundValuationTools",
    "FundValuationResources",
    "FundValuationPrompts",
]
