"""
Token 管理器

使用本地文件安全存储和读取认证令牌。
"""

import os
import json
from typing import Dict, Any, Optional

from ..config import AppConfig


class TokenManager:
    """Token 存储管理器（文件存储）"""

    def __init__(self, config: AppConfig):
        self.config = config
        self._token_dir = os.path.join(config.data_dir, "tokens")
        os.makedirs(self._token_dir, exist_ok=True)

    def _token_path(self, platform: str) -> str:
        return os.path.join(self._token_dir, f"{platform}_token.json")

    async def save_token(self, platform: str, token_data: Dict[str, Any]):
        """
        保存 Token 到本地文件

        Args:
            platform: 平台名称 (epic/steam/gog)
            token_data: Token 数据字典
        """
        token_json = json.dumps(token_data, ensure_ascii=False, indent=2)
        path = self._token_path(platform)

        with open(path, "w", encoding="utf-8") as f:
            f.write(token_json)

        print(f"{platform.upper()} Token saved")

    async def load_token(self, platform: str) -> Optional[Dict[str, Any]]:
        """
        从本地文件加载 Token

        Args:
            platform: 平台名称

        Returns:
            Token 数据字典，如果不存在则返回 None
        """
        path = self._token_path(platform)
        try:
            if not os.path.exists(path):
                return None
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Load Token error: {e}")
            return None

    async def delete_token(self, platform: str):
        """
        删除指定平台的 Token

        Args:
            platform: 平台名称
        """
        path = self._token_path(platform)
        try:
            if os.path.exists(path):
                os.remove(path)
                print(f"{platform.upper()} Token deleted")
        except Exception as e:
            print(f"Delete Token error: {e}")

    async def has_token(self, platform: str) -> bool:
        """
        检查是否存在指定平台的 Token

        Args:
            platform: 平台名称

        Returns:
            True 如果存在 Token
        """
        token = await self.load_token(platform)
        return token is not None
