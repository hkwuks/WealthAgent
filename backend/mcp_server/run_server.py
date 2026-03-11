"""
MCP Server 启动脚本

用于启动基金估值系统 MCP 服务器
"""

import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.mcp_server.server import create_mcp_server


def main():
    """主函数"""
    # 创建 MCP 服务器
    mcp = create_mcp_server()

    # 运行 MCP 服务器
    # 默认使用 stdio 传输，可以通过环境变量配置
    mcp.run()


if __name__ == "__main__":
    main()
