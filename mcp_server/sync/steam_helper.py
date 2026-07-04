"""
Steam Web API 游戏库同步逻辑

通过 Steam 官方 Web API 拉取用户拥有的全部游戏：
- IPlayerService/GetOwnedGames 返回游戏列表 + 游玩时长
- 需要用户提供 Web API Key 和 SteamID64（Profile 须设为公开）

API Key 申请: https://steamcommunity.com/dev/apikey
SteamID64 查询: https://steamid.io 或个人资料 URL
"""

from typing import List, Dict, Any, Optional
from datetime import datetime

import httpx

from ..config import AppConfig

OWNED_GAMES_URL = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
# 游戏封面 CDN（按 appid 拼接，无需额外请求）
HEADER_IMG = "https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/header.jpg"


class SteamHelper:
    """Steam Web API 游戏库同步器"""

    def __init__(self, config: AppConfig):
        self.config = config
        steam_cfg = config.platforms.get("steam")
        self.api_key = steam_cfg.api_key if steam_cfg else None
        self.steam_id = steam_cfg.steam_id if steam_cfg else None
        # trust_env=False 禁用系统代理，Steam Web API 国内可直连
        self._client = httpx.Client(timeout=20.0, follow_redirects=True, trust_env=False)

    def is_configured(self) -> bool:
        """检查是否已配置 API Key 和 SteamID"""
        return bool(self.api_key and self.steam_id)

    def get_game_list(self) -> List[Dict[str, Any]]:
        """
        通过 Web API 获取用户拥有的全部 Steam 游戏

        Returns:
            标准格式游戏列表（含游玩时长）
        """
        if not self.is_configured():
            raise Exception(
                "未配置 Steam API Key 或 SteamID，请在 config.json 的 platforms.steam 中填写 "
                "api_key（https://steamcommunity.com/dev/apikey 申请）和 steam_id（SteamID64）"
            )

        # 重试机制：api.steampowered.com 国内首次握手常超时，重试即可
        import time
        resp = None
        last_err = None
        for attempt in range(4):
            try:
                resp = self._client.get(
                    OWNED_GAMES_URL,
                    params={
                        "key": self.api_key,
                        "steamid": self.steam_id,
                        "include_appinfo": 1,        # 返回游戏名、图标等
                        "include_played_free_games": 1,
                        "format": "json",
                    },
                )
                if resp.status_code == 200:
                    break
            except Exception as e:
                last_err = e
                if attempt < 3:
                    time.sleep(2 * (attempt + 1))
                    continue
        if resp is None:
            raise Exception(f"拉取 Steam 游戏库失败（多次超时）: {last_err}")
        if resp.status_code == 401 or resp.status_code == 403:
            raise Exception("Steam API 认证失败：请检查 api_key 是否正确")
        if resp.status_code != 200:
            raise Exception(f"拉取 Steam 游戏库失败 (HTTP {resp.status_code})")

        data = resp.json().get("response", {})
        games_raw = data.get("games", [])
        if not games_raw and data.get("game_count", 0) == 0:
            raise Exception(
                "未获取到游戏，可能原因：SteamID 错误，或个人资料『游戏详情』未设为公开"
            )

        result: List[Dict[str, Any]] = []
        for g in games_raw:
            appid = g.get("appid")
            if not appid:
                continue
            result.append({
                "app_name": f"steam_{appid}",
                "title": g.get("name", f"Steam-{appid}"),
                "namespace": "steam",
                "steam_app_id": appid,
                "cover_url": HEADER_IMG.format(appid=appid),
                "genres": [],
                "developer": "",
                "platform": "steam",
                "playtime_minutes": g.get("playtime_forever", 0),
                "installed": False,
                "added_at": datetime.now().isoformat(),
            })
        return result

    def close(self):
        self._client.close()
