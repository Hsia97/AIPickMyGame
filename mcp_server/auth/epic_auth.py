"""
Epic Games 认证管理器

使用 Legendary 作为认证方案：
- 打开 legendary.gl/epiclogin 引导用户在浏览器中登录
- 用户复制页面上的 authorizationCode
- 通过 complete_epic_auth() 完成认证
- 使用 Legendary Python API 管理认证会话和 Token 刷新
"""

import webbrowser
from typing import Dict, Any

from ..config import AppConfig
from .token_manager import TokenManager

# Legendary 登录页面（会显示 authorizationCode 供用户复制）
_LOGIN_URL = "https://legendary.gl/epiclogin"


class EpicAuthManager:
    """Epic Games 认证管理器（基于 Legendary）"""

    def __init__(self, config: AppConfig):
        self.config = config
        self.token_manager = TokenManager(config)
        self._legendary_helper = None

    def _get_legendary(self):
        """延迟导入并获取 LegendaryHelper"""
        if self._legendary_helper is None:
            from ..sync.legendary_helper import LegendaryHelper
            self._legendary_helper = LegendaryHelper()
        return self._legendary_helper

    async def interactive_login(self) -> Dict[str, Any]:
        """
        检查 Legendary 认证状态。

        - 已认证：直接返回账号信息
        - 未认证：打开浏览器到 legendary.gl/epiclogin，提示用户提供 authorizationCode

        Returns:
            认证状态或登录指引
        """
        print("Checking Legendary authentication status...")
        legendary = self._get_legendary()

        # 检查是否已认证
        if legendary.is_authenticated():
            info = legendary.get_account_info() or {}
            print("Legendary already authenticated")
            token_data = {
                "account_id": info.get("account_id", ""),
                "display_name": info.get("display_name", ""),
                "auth_method": "legendary",
            }
            await self.token_manager.save_token("epic", token_data)
            return {
                "authenticated": True,
                "account_id": info.get("account_id", ""),
                "display_name": info.get("display_name", ""),
            }

        # 未认证 → 打开浏览器
        print(f"Opening Legendary login page: {_LOGIN_URL}")
        webbrowser.open(_LOGIN_URL)

        return {
            "authenticated": False,
            "login_url": _LOGIN_URL,
            "message": (
                "浏览器已打开登录页面。请在页面中完成 Epic Games 登录，"
                "登录后页面会显示一段 JSON，复制其中 authorizationCode 的值，"
                "然后调用 complete_epic_auth(authorization_code) 完成认证。"
            ),
        }

    async def complete_auth(self, auth_code: str) -> Dict[str, Any]:
        """
        使用 authorizationCode 完成 Legendary 认证

        Args:
            auth_code: 从 legendary.gl/epiclogin 页面获取的 authorizationCode

        Returns:
            认证结果
        """
        legendary = self._get_legendary()
        result = legendary.authenticate_with_code(auth_code)

        if result.get("success"):
            token_data = {
                "account_id": result.get("account_id", ""),
                "display_name": result.get("display_name", ""),
                "auth_method": "legendary",
            }
            await self.token_manager.save_token("epic", token_data)
            print("Epic account authenticated via Legendary")

        return result

    async def auto_refresh_token(self) -> Dict[str, Any]:
        """
        自动刷新 Token（Legendary 内部自动处理）

        Returns:
            Token 数据
        """
        legendary = self._get_legendary()

        if legendary.is_authenticated():
            info = legendary.get_account_info() or {}
            return {
                "authenticated": True,
                "account_id": info.get("account_id", ""),
                "display_name": info.get("display_name", ""),
                "auth_method": "legendary",
            }

        token_data = await self.token_manager.load_token("epic")
        if token_data:
            return token_data

        raise Exception("未认证，请先运行 setup_epic_account()")

    def get_login_url(self) -> str:
        """获取登录 URL"""
        return _LOGIN_URL
