"""
MCP Server for 智能理财Agent

智能理财Agent MCP 服务器
提供基金查询、估值、市场数据、黄金预测、回测等功能的 MCP 接口
"""

from backend.mcp_server.server import create_mcp_server
from backend.mcp_server.tools import FundValuationTools
from backend.mcp_server.resources import FundValuationResources, GoldPredictionResources
from backend.mcp_server.prompts import FundValuationPrompts

__all__ = [
    "create_mcp_server",
    "FundValuationTools",
    "FundValuationResources",
    "GoldPredictionResources",
    "FundValuationPrompts",
]
