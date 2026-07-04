"""
IGDB.com 游戏元数据客户端

使用 Twitch OAuth 访问 IGDB API，获取：
- 类型 (genres)
- 标签/主题 (themes)
- 评分 (rating)
- 描述 (summary)
- 截图 (screenshots)
- 封面图 (cover)
- 发行日期 (release_date)

IGDB 提供免费 API，国内部分 ISP 可直连（无需代理）。
需要配置 Twitch Client ID 和 Client Secret。
"""

import time
import httpx
from typing import Dict, Any, Optional, List


class IGDBClient:
    """IGDB API 客户端（基于 Twitch OAuth）"""

    AUTH_URL = "https://id.twitch.tv/oauth2/token"
    API_URL = "https://api.igdb.com/v4/games"

    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self._access_token = None
        self._token_expiry = 0

        # 检测系统代理
        proxy = self._detect_system_proxy()
        self._client = httpx.Client(
            timeout=15.0,
            follow_redirects=True,
            proxy=proxy,
        )
        if proxy:
            print(f"IGDB 客户端检测到代理: {proxy}")
        else:
            print("IGDB 客户端直连模式")

    def _get_access_token(self) -> Optional[str]:
        if self._access_token and time.time() < self._token_expiry:
            return self._access_token

        try:
            resp = self._client.post(
                self.AUTH_URL,
                params={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "client_credentials",
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                self._access_token = data.get("access_token")
                self._token_expiry = time.time() + data.get("expires_in", 3600) - 60
                return self._access_token
        except Exception as e:
            print(f"IGDB 认证失败: {e}")
        return None

    def search_game(self, title: str) -> Optional[Dict[str, Any]]:
        token = self._get_access_token()
        if not token:
            return None

        try:
            resp = self._client.post(
                self.API_URL,
                headers={
                    "Client-ID": self.client_id,
                    "Authorization": f"Bearer {token}",
                },
                data=f'search "{title}"; fields id,name,genres.name,themes.name,rating,aggregated_rating,summary,cover.url,screenshots.url,first_release_date,platforms.name,involved_companies.company.name; limit 5;',
            )
            if resp.status_code != 200:
                return None

            results = resp.json()
            if not results:
                return None

            best = results[0]
            return self._parse_game_data(best)

        except Exception as e:
            print(f"IGDB search error for '{title}': {e}")
            return None

    def _parse_game_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        genres = [g.get("name", "") for g in data.get("genres", [])]

        themes = [t.get("name", "") for t in data.get("themes", [])]

        cover_url = ""
        cover = data.get("cover", {})
        if cover:
            cover_url = cover.get("url", "").replace("t_thumb", "t_cover_big")
            if cover_url.startswith("//"):
                cover_url = "https:" + cover_url

        screenshots = []
        for s in data.get("screenshots", [])[:4]:
            url = s.get("url", "").replace("t_thumb", "t_screenshot_big")
            if url.startswith("//"):
                url = "https:" + url
            screenshots.append(url)

        release_date = ""
        ts = data.get("first_release_date")
        if ts:
            from datetime import datetime
            release_date = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")

        developers = []
        for company in data.get("involved_companies", []):
            if company.get("developer"):
                c = company.get("company", {})
                if c.get("name"):
                    developers.append(c["name"])

        description = data.get("summary", "")

        return {
            "title": data.get("name", ""),
            "genres": genres,
            "tags": themes,
            "rating": round(data.get("rating", 0) or 0, 1),
            "aggregated_rating": round(data.get("aggregated_rating", 0) or 0, 1),
            "release_date": release_date,
            "description": description,
            "developers": developers,
            "screenshots": screenshots,
            "cover_url": cover_url,
            "igdb_id": data.get("id"),
        }

    @staticmethod
    def _detect_system_proxy() -> Optional[str]:
        import os
        for var in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY"):
            val = os.environ.get(var) or os.environ.get(var.lower())
            if val:
                return val
        if os.name == "nt":
            try:
                import winreg
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
                )
                enable, _ = winreg.QueryValueEx(key, "ProxyEnable")
                if enable:
                    server, _ = winreg.QueryValueEx(key, "ProxyServer")
                    winreg.CloseKey(key)
                    if server:
                        if "://" not in server:
                            server = f"http://{server}"
                        return server
                winreg.CloseKey(key)
            except Exception:
                pass
        return None

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()