"""
游戏库同步器

使用 Legendary 从 Epic Games 拉取游戏库数据，
并保存到本地 JSON 文件。
"""

import json
from typing import List, Dict, Any
from datetime import datetime

from ..config import AppConfig
from ..auth.epic_auth import EpicAuthManager


class LibrarySyncer:
    """游戏库同步器（基于 Legendary）"""

    def __init__(self, config: AppConfig):
        self.config = config
        self.auth_manager = EpicAuthManager(config)

    async def sync(self, platform: str = "epic", force: bool = False) -> Dict[str, Any]:
        """
        同步指定平台的游戏库（仅拉取游戏列表，不补全元数据）

        元数据补全请使用 enrich_metadata() 工具单独触发。

        Args:
            platform: 平台名称 (epic/gog)
            force: 是否强制重新同步（忽略缓存）

        Returns:
            同步结果摘要
        """
        print(f"开始同步 {platform.upper()} 游戏库...")

        # 按平台分发拉取逻辑
        if platform == "epic":
            if not await self.auth_manager.token_manager.has_token("epic"):
                raise Exception("未配置 Epic 账号，请先运行 setup_epic_account()")
            games = self._fetch_epic_library_via_legendary()
        elif platform == "gog":
            games = await self._fetch_gog_library()
        elif platform == "steam":
            games = self._fetch_steam_library()
        elif platform == "galaxy":
            games = await self._fetch_galaxy_library()
        else:
            raise NotImplementedError(f"暂不支持 {platform} 平台，目前支持 Epic、GOG、Steam 和 galaxy 聚合")

        # 合并已补全的元数据：加载已有库，保留 enriched 字段
        existing = await self.load_library(platform)
        if existing:
            enriched_fields = [
                "rating", "ratings_count", "tags", "description",
                "developers", "publishers", "screenshots",
                "metacritic_score", "steam_app_id", "price_cny",
                "igdb_id", "_meta_source",
            ]
            existing_map = {g.get("app_name"): g for g in existing if g.get("app_name")}
            for game in games:
                app_name = game.get("app_name")
                if app_name and app_name in existing_map:
                    for field in enriched_fields:
                        if field in existing_map[app_name] and existing_map[app_name][field]:
                            game[field] = existing_map[app_name][field]

        # 保存到本地（不含元数据）
        await self._save_library(platform, games)

        result = {
            "platform": platform,
            "game_count": len(games),
            "synced_at": datetime.now().isoformat(),
            "success": True,
        }

        print(f"同步完成：{len(games)} 款游戏（元数据待补全）")
        return result

    async def enrich_library(
        self, platform: str = "epic", batch_size: int = 0
    ) -> Dict[str, Any]:
        """
        为已有游戏库补全元数据（不重新拉取游戏列表）

        自动分批处理，每次处理一批后返回进度，可多次调用直到完成。

        Args:
            platform: 平台名称
            batch_size: 每批数量（默认0=自动5款，建议5-15）

        Returns:
            补全结果摘要
        """
        games = await self.load_library(platform)
        if not games:
            return {"success": False, "error": f"未找到 {platform} 游戏库，请先同步"}

        total = len(games)

        def _count_enriched(games_list):
            return sum(
                1 for g in games_list
                if (
                    (g.get("genres") and g.get("description"))
                    or g.get("steam_app_id")
                    or g.get("igdb_id")
                )
            )

        enriched_before = _count_enriched(games)

        if enriched_before >= total:
            return {
                "success": True,
                "platform": platform,
                "total_games": total,
                "enriched_games": total,
                "remaining": 0,
                "message": "所有游戏元数据已补全",
            }

        from ..metadata.rawg_client import enrich_games
        api_key = self.config.metadata.api_key

        chunk = batch_size if batch_size > 0 else 5
        pending = [
            g for g in games
            if not (
                (g.get("genres") and g.get("description"))
                or g.get("steam_app_id")
                or g.get("igdb_id")
            )
        ]
        batch = pending[:chunk]
        print(f"补全 {len(batch)}/{len(pending)} 款（已完成 {enriched_before}/{total}）...")
        enrich_games(batch, api_key)
        await self._save_library(platform, games)

        enriched_count = _count_enriched(games)
        remaining = total - enriched_count

        return {
            "success": True,
            "platform": platform,
            "total_games": total,
            "enriched_games": enriched_count,
            "remaining": remaining,
            "batch_processed": len(batch),
            "message": (
                f"已补全 {enriched_count}/{total} 款"
                + (f"，还剩 {remaining} 款待处理" if remaining else "，全部完成")
            ),
        }

    def _fetch_epic_library_via_legendary(self) -> List[Dict[str, Any]]:
        """
        使用 Legendary Python API 获取 Epic 游戏库

        Returns:
            游戏列表
        """
        from .legendary_helper import LegendaryHelper

        helper = LegendaryHelper()

        if not helper.is_authenticated():
            raise Exception("Legendary 未认证，请先运行 setup_epic_account()")

        games = helper.get_game_list()
        print(f"从 Legendary 获取到 {len(games)} 款游戏")
        return games

    async def _fetch_gog_library(self) -> List[Dict[str, Any]]:
        """
        使用 GOG Galaxy API 获取 GOG 游戏库

        Returns:
            游戏列表
        """
        from .gog_helper import GOGHelper

        helper = GOGHelper(self.config)

        if not await helper.is_authenticated():
            raise Exception("GOG 未认证，请先运行 setup_gog_account()")

        games = await helper.get_game_list()
        print(f"从 GOG 获取到 {len(games)} 款游戏")
        return games

    def _fetch_steam_library(self) -> List[Dict[str, Any]]:
        """
        使用 Steam Web API 获取 Steam 游戏库

        需要在 config.json 的 platforms.steam 中配置 api_key 和 steam_id。

        Returns:
            游戏列表（含游玩时长）
        """
        from .steam_helper import SteamHelper

        helper = SteamHelper(self.config)
        games = helper.get_game_list()
        helper.close()
        print(f"从 Steam 获取到 {len(games)} 款游戏")
        return games

    async def _fetch_galaxy_library(self) -> List[Dict[str, Any]]:
        """
        通过 GOG Galaxy 聚合库获取全平台游戏（Epic/Steam/Uplay/Xbox/Origin 等）

        需要先用 setup_gog_account() 认证 GOG，且用户在 GOG Galaxy 中已绑定相应平台。

        Returns:
            游戏列表（platform 字段标记真实来源）
        """
        from .gog_helper import GOGHelper

        helper = GOGHelper(self.config)

        if not await helper.is_authenticated():
            raise Exception("GOG 未认证，请先运行 setup_gog_account()（聚合库依赖 GOG Galaxy 登录）")

        games = await helper.get_aggregated_game_list()
        print(f"从 Galaxy 聚合库获取到 {len(games)} 款游戏")
        return games

    async def load_library(self, platform: str = "epic") -> List[Dict[str, Any]]:
        """
        从本地文件加载游戏库

        Args:
            platform: 平台名称

        Returns:
            游戏列表
        """
        library_path = self.config.get_library_path(platform)

        if not library_path.exists():
            print(f"未找到 {platform.upper()} 游戏库文件，请先同步")
            return []

        try:
            with open(library_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            games = data.get("games", [])
            print(f"已加载 {len(games)} 款 {platform.upper()} 游戏")
            return games

        except Exception as e:
            print(f"加载游戏库失败: {e}")
            return []

    async def _save_library(self, platform: str, games: List[Dict[str, Any]]):
        """
        保存游戏库到本地 JSON 文件

        Args:
            platform: 平台名称
            games: 游戏列表
        """
        library_path = self.config.get_library_path(platform)

        data = {
            "source": platform,
            "exported_at": datetime.now().isoformat(),
            "game_count": len(games),
            "games": games,
        }

        library_path.parent.mkdir(parents=True, exist_ok=True)

        with open(library_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"游戏库已保存到: {library_path}")
