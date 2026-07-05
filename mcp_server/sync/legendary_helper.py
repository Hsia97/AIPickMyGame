"""
Legendary Helper

封装 Legendary CLI 的 Python API，用于：
- 认证 Epic Games 账号
- 获取游戏库列表
- 获取游戏元数据
"""

import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

# 抑制 Legendary 的日志输出
logging.getLogger("LegendaryCore").setLevel(logging.WARNING)
logging.getLogger("EPCAPI").setLevel(logging.WARNING)


class LegendaryHelper:
    """Legendary CLI 封装"""

    LOGIN_URL = "https://legendary.gl/epiclogin"

    def __init__(self):
        self._core = None

    def _get_core(self):
        """获取或创建 LegendaryCore 实例"""
        if self._core is None:
            from legendary.core import LegendaryCore
            self._core = LegendaryCore()
        return self._core

    def is_authenticated(self) -> bool:
        """检查 Legendary 是否已认证"""
        try:
            core = self._get_core()
            return core.login()
        except (ValueError, Exception):
            return False

    def get_account_info(self) -> Optional[Dict[str, Any]]:
        """获取已认证的账号信息"""
        try:
            core = self._get_core()
            userdata = core.lgd.userdata
            if userdata:
                return {
                    "account_id": userdata.get("account_id", ""),
                    "display_name": userdata.get("displayName", ""),
                    "expires_at": userdata.get("expires_at", ""),
                }
        except Exception:
            pass
        return None

    def authenticate_with_code(self, auth_code: str) -> Dict[str, Any]:
        """
        使用 authorization code 认证

        Args:
            auth_code: 从 legendary.gl/epiclogin 页面获取的 authorizationCode

        Returns:
            认证结果
        """
        core = self._get_core()

        # 处理可能的 JSON 格式输入
        auth_code = auth_code.strip()
        if auth_code.startswith("{"):
            try:
                data = json.loads(auth_code)
                auth_code = data.get("authorizationCode", auth_code)
            except json.JSONDecodeError:
                pass
        auth_code = auth_code.strip('"').strip("'")

        if core.auth_code(auth_code):
            userdata = core.lgd.userdata
            return {
                "success": True,
                "account_id": userdata.get("account_id", ""),
                "display_name": userdata.get("displayName", ""),
                "message": "Legendary authentication successful",
            }
        else:
            return {
                "success": False,
                "message": "Legendary authentication failed",
            }

    def authenticate_with_sid(self, sid: str) -> Dict[str, Any]:
        """
        使用 session ID 认证

        Args:
            sid: Epic Games 的 session ID

        Returns:
            认证结果
        """
        core = self._get_core()
        exchange_code = core.auth_sid(sid)
        if exchange_code:
            if core.auth_ex_token(exchange_code):
                userdata = core.lgd.userdata
                return {
                    "success": True,
                    "account_id": userdata.get("account_id", ""),
                    "display_name": userdata.get("displayName", ""),
                    "message": "Legendary SID authentication successful",
                }
        return {
            "success": False,
            "message": "Legendary SID authentication failed",
        }

    def get_game_list(self, platform: str = "Windows") -> List[Dict[str, Any]]:
        """
        获取用户拥有的所有游戏

        Args:
            platform: 平台过滤 (Windows/Mac/Win32)

        Returns:
            游戏列表
        """
        core = self._get_core()

        # 确保已登录
        if not core.login():
            raise Exception("Legendary not authenticated. Please run setup_epic_account first.")

        games, dlc_map = core.get_game_and_dlc_list(
            update_assets=False,  # 加速同步，元数据由 enrich 单独补全
            platform=platform,
            skip_ue=True,
        )

        result = []
        for game in games:
            try:
                meta = core.lgd.get_game_meta(game.app_name)
                if not meta:
                    continue

                # 获取封面图
                cover_url = None
                if meta.metadata:
                    key_images = meta.metadata.get("keyImages", [])
                    for img in key_images:
                        if img.get("type") in [
                            "Thumbnail",
                            "DieselStoreFrontWide",
                            "OfferImageWide",
                        ]:
                            cover_url = img.get("url")
                            break

                # 获取类型标签（从所有 category path 提取，不限于 /public/）
                genres = []
                if meta.metadata:
                    categories = meta.metadata.get("categories", [])
                    for cat in categories:
                        path = cat.get("path", "")
                        if not path:
                            continue
                        # 去掉各类前缀，取最后一段作为类型名
                        for prefix in ("/public/", "/games/", "/bundles/", "/store/", "/"):
                            if path.startswith(prefix):
                                path = path[len(prefix):]
                                break
                        genre = path.replace("/", " ").strip()
                        if genre:
                            genres.append(genre.title())

                # 获取开发者
                developer = None
                if meta.metadata:
                    developer_info = meta.metadata.get("developer", "")
                    if developer_info:
                        developer = developer_info
                    elif meta.metadata.get("developerName"):
                        developer = meta.metadata["developerName"]

                game_data = {
                    "app_name": game.app_name,
                    "title": meta.metadata.get("title", game.app_name)
                    if meta.metadata
                    else game.app_name,
                    "namespace": game.namespace if hasattr(game, "namespace") else "",
                    "cover_url": cover_url,
                    "genres": genres[:5],
                    "developer": developer,
                    "platform": "epic",
                    "installed": core.is_installed(game.app_name),
                    "added_at": datetime.now().isoformat(),
                }
                result.append(game_data)
            except Exception as e:
                print(f"Warning: Failed to process game {game.app_name}: {e}")
                continue

        return result

    def get_login_url(self) -> str:
        """获取 Legendary 登录页面 URL"""
        return self.LOGIN_URL

    def logout(self):
        """注销 Legendary"""
        try:
            core = self._get_core()
            core.lgd.invalidate_userdata()
        except Exception:
            pass
