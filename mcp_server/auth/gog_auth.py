"""
GOG Games 认证管理器

复刻 Heroic Games Launcher 的 gogdl OAuth2 流程，纯 HTTP 实现：
- 打开 GOG 登录页引导用户在浏览器登录
- 登录成功后页面跳转到 embed.gog.com/on_login_success?code=XXX
- 用户复制地址栏 URL（或其中的 code）
- 通过 complete_gog_auth() 用 code 换取 access_token / refresh_token
- access_token 过期时用 refresh_token 自动刷新
"""

import time
import webbrowser
from typing import Dict, Any, Optional
from urllib.parse import urlparse, parse_qs

import httpx

from ..config import AppConfig
from .token_manager import TokenManager

# GOG Galaxy 客户端公开凭证（与 Heroic/gogdl 一致）
CLIENT_ID = "46899977096215655"
CLIENT_SECRET = "9d85c43b1482497dbbce61f6e4aa173a433796eeae2ca8c5f6129f2dc4de46d9"
REDIRECT_URI = "https://embed.gog.com/on_login_success?origin=client"

OAUTH_URL = (
    "https://auth.gog.com/auth?client_id=" + CLIENT_ID
    + "&redirect_uri=https%3A%2F%2Fembed.gog.com%2Fon_login_success%3Forigin%3Dclient"
    + "&response_type=code&layout=galaxy"
)
TOKEN_URL = "https://auth.gog.com/token"


class GOGAuthManager:
    """GOG Games 认证管理器（OAuth2）"""

    def __init__(self, config: AppConfig):
        self.config = config
        self.token_manager = TokenManager(config)
        # trust_env=False 禁用系统代理，避免国内代理干扰导致超时
        self._client = httpx.Client(timeout=20.0, follow_redirects=True, trust_env=False)

    async def interactive_login(self) -> Dict[str, Any]:
        """
        检查 GOG 认证状态。
        - 已认证：返回账号信息
        - 未认证：打开浏览器到 GOG 登录页，提示用户提供 code
        """
        token = await self.token_manager.load_token("gog")
        if token and token.get("refresh_token"):
            # 尝试刷新确认 token 有效
            try:
                await self.get_valid_access_token()
                return {
                    "authenticated": True,
                    "account_id": token.get("user_id", ""),
                    "display_name": token.get("display_name", ""),
                }
            except Exception:
                pass

        print(f"Opening GOG login page: {OAUTH_URL}")
        webbrowser.open(OAUTH_URL)
        return {
            "authenticated": False,
            "login_url": OAUTH_URL,
            "message": (
                "浏览器已打开 GOG 登录页面。请完成登录，登录成功后页面会跳转到 "
                "embed.gog.com/on_login_success?code=... 。请复制浏览器地址栏的完整 URL"
                "（或其中 code= 后面的值），然后调用 complete_gog_auth(authorization_code) 完成认证。"
            ),
        }

    @staticmethod
    def _extract_code(code_or_url: str) -> str:
        """从完整 URL 或纯 code 中提取 authorization code"""
        s = (code_or_url or "").strip().strip('"').strip("'")
        if s.startswith("http"):
            parsed = urlparse(s)
            qs = parse_qs(parsed.query)
            code = qs.get("code", [""])[0]
            return code or s
        return s

    async def complete_auth(self, code_or_url: str) -> Dict[str, Any]:
        """用 authorization code 换取 token 并保存"""
        code = self._extract_code(code_or_url)
        if not code:
            return {"success": False, "message": "未能解析出 authorization code"}

        try:
            resp = self._client.get(
                TOKEN_URL,
                params={
                    "client_id": CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": REDIRECT_URI,
                },
            )
            if resp.status_code != 200:
                return {"success": False, "message": f"Token 交换失败 (HTTP {resp.status_code}): {resp.text[:200]}"}

            data = resp.json()
            token_data = {
                "access_token": data.get("access_token", ""),
                "refresh_token": data.get("refresh_token", ""),
                "user_id": data.get("user_id", ""),
                "expires_at": time.time() + data.get("expires_in", 3600),
                "token_type": data.get("token_type", "bearer"),
                "auth_method": "oauth2",
            }
            await self.token_manager.save_token("gog", token_data)
            print("GOG account authenticated via OAuth2")
            return {
                "success": True,
                "account_id": token_data["user_id"],
                "display_name": "",
                "message": "GOG authentication successful",
            }
        except Exception as e:
            return {"success": False, "message": f"认证失败: {e}"}

    async def get_valid_access_token(self) -> str:
        """返回有效的 access_token，过期则用 refresh_token 刷新"""
        token = await self.token_manager.load_token("gog")
        if not token:
            raise Exception("未认证，请先运行 setup_gog_account()")

        # 未过期直接返回（留 60 秒余量）
        if token.get("access_token") and token.get("expires_at", 0) > time.time() + 60:
            return token["access_token"]

        # 刷新
        refresh_token = token.get("refresh_token")
        if not refresh_token:
            raise Exception("缺少 refresh_token，请重新认证")

        resp = self._client.get(
            TOKEN_URL,
            params={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )
        if resp.status_code != 200:
            raise Exception(f"Token 刷新失败 (HTTP {resp.status_code})")

        data = resp.json()
        token["access_token"] = data.get("access_token", "")
        token["refresh_token"] = data.get("refresh_token", refresh_token)
        token["expires_at"] = time.time() + data.get("expires_in", 3600)
        if data.get("user_id"):
            token["user_id"] = data["user_id"]
        await self.token_manager.save_token("gog", token)
        return token["access_token"]

    def get_login_url(self) -> str:
        return OAUTH_URL
