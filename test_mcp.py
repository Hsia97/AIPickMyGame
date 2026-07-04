"""
MCP Server 手动测试脚本

用于验证 MCP Server 是否正常工作，无需依赖外部 AI Agent。
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from mcp_server.main import mcp


async def test_mcp_server():
    """测试 MCP Server 的基本功能"""
    
    print("🧪 开始测试 MCP Server...\n")
    
    # 列出所有可用的工具
    tools = await mcp.list_tools()
    print(f"✅ 发现 {len(tools)} 个可用工具:")
    for tool in tools:
        print(f"   - {tool.name}: {tool.description}")
    
    print("\n" + "="*60)
    print("💡 提示: MCP Server 运行正常！")
    print("\n下一步:")
    print("1. 在 Claude Desktop 或其他 MCP 客户端中配置此服务器")
    print("2. 或编写自定义客户端调用这些工具")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(test_mcp_server())
