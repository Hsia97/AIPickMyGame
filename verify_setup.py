"""
项目结构验证脚本

检查所有必需的模块和文件是否存在。
"""

import sys
from pathlib import Path


def check_project_structure():
    """验证项目结构完整性"""
    
    root = Path(__file__).parent
    
    required_files = [
        "mcp_server/__init__.py",
        "mcp_server/main.py",
        "mcp_server/config.py",
        "mcp_server/auth/__init__.py",
        "mcp_server/auth/epic_auth.py",
        "mcp_server/auth/token_manager.py",
        "mcp_server/sync/__init__.py",
        "mcp_server/sync/library_syncer.py",
        "mcp_server/recommend/__init__.py",
        "mcp_server/recommend/engine.py",
        "mcp_server/storage/__init__.py",
        "mcp_server/storage/token_storage.py",
        "mcp_server/storage/library_cache.py",
        "browser-extension/manifest.json",
        "browser-extension/background.js",
        "browser-extension/epic-content.js",
        "requirements.txt",
        "README.md",
    ]
    
    print("🔍 检查项目结构...\n")
    
    missing = []
    for file_path in required_files:
        full_path = root / file_path
        if full_path.exists():
            print(f"✅ {file_path}")
        else:
            print(f"❌ {file_path} - 缺失!")
            missing.append(file_path)
    
    print("\n" + "="*60)
    
    if missing:
        print(f"❌ 发现 {len(missing)} 个缺失文件:")
        for f in missing:
            print(f"   - {f}")
        return False
    else:
        print("✅ 项目结构完整！所有必需文件都存在。")
        
        # 检查依赖
        print("\n📦 检查 Python 依赖...")
        try:
            import fastmcp
            print("✅ fastmcp")
        except ImportError:
            print("❌ fastmcp - 请运行: pip install fastmcp")
        
        try:
            import keyring
            print("✅ keyring")
        except ImportError:
            print("❌ keyring - 请运行: pip install keyring")
        
        try:
            import aiohttp
            print("✅ aiohttp")
        except ImportError:
            print("❌ aiohttp - 请运行: pip install aiohttp")
        
        try:
            import httpx
            print("✅ httpx")
        except ImportError:
            print("❌ httpx - 请运行: pip install httpx")
        
        try:
            import pydantic
            print("✅ pydantic")
        except ImportError:
            print("❌ pydantic - 请运行: pip install pydantic")
        
        print("\n" + "="*60)
        print("🎉 项目初始化完成！")
        print("\n下一步:")
        print("1. 安装依赖: pip install -r requirements.txt")
        print("2. 查看文档: cat docs/QUICKSTART.md")
        print("3. 启动服务: python -m mcp_server.main")
        
        return True


if __name__ == "__main__":
    success = check_project_structure()
    sys.exit(0 if success else 1)
