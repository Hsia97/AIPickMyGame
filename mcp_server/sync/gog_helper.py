"""
GOG 游戏库同步逻辑

对标 LegendaryHelper，通过 GOG Galaxy API 拉取用户游戏库：
- galaxy-library.gog.com 拉取拥有的 release 列表（分页）
- gamesdb.gog.com 补充每款游戏的标题、封面、类型
- 解析为项目标准游戏格式（与 Epic 一致）
"""

from typing import List, Dict, Any, Optional
from datetime import datetime

import httpx

from ..config import AppConfig
from ..auth.gog_auth import GOGAuthManager

USERDATA_URL = "https://embed.gog.com/userData.json"
LIBRARY_URL = "https://galaxy-library.gog.com/users/{user_id}/releases"
GAMESDB_URL = "https://gamesdb.gog.com/platforms/{platform}/external_releases/{game_id}"


class GOGHelper:
    """GOG 游戏库同步器（基于 GOG Galaxy API）"""

    def __init__(self, config: AppConfig):
        self.config = config
        self.auth = GOGAuthManager(config)
        self._client = httpx.Client(timeout=20.0, follow_redirects=True, trust_env=False)

    async def is_authenticated(self) -> bool:
        """检查是否已认证（能拿到有效 access_token）"""
        try:
            await self.auth.get_valid_access_token()
            return True
        except Exception:
            return False

    async def get_account_info(self) -> Optional[Dict[str, Any]]:
        """获取账号信息（用户名、ID）"""
        try:
            access_token = await self.auth.get_valid_access_token()
            resp = self._client.get(
                USERDATA_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            return {
                "account_id": str(data.get("userId", "")),
                "display_name": data.get("username", ""),
            }
        except Exception:
            return None

    async def _fetch_all_releases(self) -> List[Dict[str, Any]]:
        """
        分页拉取 GOG Galaxy 聚合库的全部 release（含所有已绑定平台）

        Returns:
            原始 release 列表
        """
        access_token = await self.auth.get_valid_access_token()
        token = await self.auth.token_manager.load_token("gog")
        user_id = token.get("user_id", "") if token else ""
        if not user_id:
            info = await self.get_account_info()
            user_id = info.get("account_id", "") if info else ""
        if not user_id:
            raise Exception("无法获取 GOG user_id，请重新认证")

        headers = {"Authorization": f"Bearer {access_token}"}
        releases: List[Dict[str, Any]] = []
        url = LIBRARY_URL.format(user_id=user_id)
        params: Dict[str, Any] = {}
        while True:
            resp = self._client.get(url, headers=headers, params=params)
            if resp.status_code != 200:
                raise Exception(f"拉取 GOG 游戏库失败 (HTTP {resp.status_code})")
            data = resp.json()
            releases.extend(data.get("items", []))
            next_token = data.get("next_page_token")
            if not next_token:
                break
            params = {"page_token": next_token}
        return releases

    async def get_game_list(self) -> List[Dict[str, Any]]:
        """
        获取用户拥有的所有 GOG 游戏（仅 GOG 平台自家游戏）

        Returns:
            标准格式游戏列表
        """
        releases = await self._fetch_all_releases()
        gog_releases = [r for r in releases if r.get("platform_id") == "gog"]
        print(f"GOG 拥有 {len(gog_releases)} 款游戏，开始解析元数据...")

        result: List[Dict[str, Any]] = []
        for rel in gog_releases:
            external_id = rel.get("external_id")
            if not external_id:
                continue
            game = self._fetch_game_meta(external_id, rel.get("certificate", ""), platform="gog")
            if game:
                result.append(game)
        return result

    async def get_aggregated_game_list(self) -> List[Dict[str, Any]]:
        """
        获取 GOG Galaxy 聚合库的全平台游戏（含 Epic/Steam/Uplay/Xbox/Origin 等）

        GOG Galaxy 会聚合用户在其中绑定的所有平台游戏。本方法遍历全部 release，
        用各自的 platform_id 查询 gamesdb 拿到标题/类型/封面。

        Returns:
            标准格式游戏列表，platform 字段标记真实来源平台
        """
        import time

        releases = await self._fetch_all_releases()

        from collections import Counter
        dist = Counter(r.get("platform_id", "?") for r in releases)
        print(f"Galaxy 聚合库共 {len(releases)} 个 release，平台分布: {dict(dist)}")

        result: List[Dict[str, Any]] = []
        for rel in releases:
            platform = rel.get("platform_id") or "gog"
            external_id = rel.get("external_id")
            if not external_id:
                continue
            game = self._fetch_game_meta(external_id, rel.get("certificate", ""), platform=platform)
            if game:
                result.append(game)
            time.sleep(0.05)  # 轻微间隔，避免 gamesdb 限流
        return result


    def _fetch_game_meta(self, game_id: str, certificate: str = "", platform: str = "gog") -> Optional[Dict[str, Any]]:
        """
        从 gamesdb 获取单款游戏的元数据并解析为标准格式

        Args:
            game_id: 平台的 external_id
            certificate: galaxy-library 返回的 cert（用于 X-GOG-Library-Cert header）
            platform: 平台标识（gog/steam/epic/uplay/xboxone/origin）

        Returns:
            标准格式游戏字典，失败返回 None
        """
        try:
            headers = {}
            if certificate:
                headers["X-GOG-Library-Cert"] = certificate
            resp = self._client.get(
                GAMESDB_URL.format(platform=platform, game_id=game_id),
                headers=headers,
            )
            if resp.status_code != 200:
                return None
            data = resp.json()

            # 标题
            title_obj = data.get("title", {})
            title = title_obj.get("*", "") if isinstance(title_obj, dict) else str(title_obj)
            if not title:
                game_obj = data.get("game", {})
                t = game_obj.get("title", {}) if isinstance(game_obj, dict) else {}
                title = t.get("*", "") if isinstance(t, dict) else ""
            if not title:
                title = f"GOG-{game_id}"

            # 封面（取 game.vertical_cover 或 square_icon）
            cover_url = ""
            game_obj = data.get("game", {}) or {}
            for key in ("vertical_cover", "cover", "square_icon", "logo"):
                img = game_obj.get(key)
                if isinstance(img, dict) and img.get("url_format"):
                    cover_url = img["url_format"].split("{")[0]
                    break
                if isinstance(img, str) and img:
                    cover_url = img
                    break

            # 类型
            genres = []
            for g in game_obj.get("genres", []) or []:
                name = g.get("name", {})
                gname = name.get("*", "") if isinstance(name, dict) else str(name)
                if gname:
                    genres.append(gname)

            # 开发商
            developer = ""
            devs = game_obj.get("developers", []) or []
            if devs:
                d0 = devs[0]
                developer = d0.get("name", "") if isinstance(d0, dict) else str(d0)

            return {
                "app_name": f"{platform}_{game_id}",
                "title": title,
                "namespace": platform,
                "cover_url": cover_url,
                "genres": genres[:5],
                "developer": developer,
                "platform": platform,
                "installed": False,
                "added_at": datetime.now().isoformat(),
            }
        except Exception as e:
            print(f"{platform} 游戏 {game_id} 元数据解析失败: {e}")
            return None
