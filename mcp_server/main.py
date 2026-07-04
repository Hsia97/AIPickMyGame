"""
MCP Server 主入口

实现 FastMCP 服务器，提供游戏推荐、库同步等工具。
"""

from fastmcp import FastMCP
from typing import List, Optional, Dict, Any
import asyncio
import json
from pathlib import Path

from .auth.epic_auth import EpicAuthManager
from .auth.gog_auth import GOGAuthManager
from .sync.library_syncer import LibrarySyncer
from .recommend.engine import GameLibraryProcessor
from .metadata.rawg_client import format_display_name
from .storage.token_storage import EncryptedTokenStorage
from .config import AppConfig

# 创建 MCP 服务器实例
mcp = FastMCP("AIPickMyGame")

# 全局配置
config = AppConfig()


@mcp.tool()
async def get_user_library(platform: str = "epic") -> Dict[str, Any]:
    """
    获取用户的游戏库原始数据
    
    返回完整的游戏列表，供 AI Agent 进行进一步分析和推荐。
    
    Args:
        platform: 游戏平台 (epic/steam/gog)
        
    Returns:
        包含游戏库数据的字典
    """
    try:
        syncer = LibrarySyncer(config)
        games = await syncer.load_library(platform)
        
        if not games:
            return {
                "error": f"未找到 {platform} 游戏库",
                "hint": "请先调用 setup_epic_account() 配置账号并同步"
            }
        
        # 返回精简版数据（避免 token 过多）
        simplified_games = [
            {
                "title": format_display_name(g.get('title', '')),
                "genres": g.get('genres', []),
                "tags": g.get('tags', []),
                "rating": g.get('rating', 0),
                "release_date": g.get('release_date', ''),
                "description": g.get('description', '')[:200]  # 限制描述长度
            }
            for g in games
        ]
        
        processor = GameLibraryProcessor()
        summary = processor.get_library_summary(games)
        
        return {
            "platform": platform,
            "summary": summary,
            "games": simplified_games,
            "total_count": len(games)
        }
        
    except Exception as e:
        return {
            "error": f"加载失败: {str(e)}"
        }


@mcp.tool()
async def sync_library(platform: str = "epic", force: bool = False) -> Dict[str, Any]:
    """
    同步指定平台的游戏库（使用 Legendary 获取 Epic 游戏数据）

    需要先通过 setup_epic_account() 完成认证。

    Args:
        platform: 游戏平台 (epic/steam/gog)
        force: 是否强制重新同步（忽略缓存）

    Returns:
        同步结果
    """
    try:
        syncer = LibrarySyncer(config)
        result = await syncer.sync(platform, force=force)
        
        return {
            "success": True,
            "platform": result['platform'],
            "game_count": result['game_count'],
            "synced_at": result['synced_at']
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@mcp.tool()
async def enrich_metadata(platform: str = "epic", batch_size: int = 50) -> Dict[str, Any]:
    """
    为游戏库补全元数据（评分、类型、描述、截图等）

    使用 RAWG.io + Steam Store 多级降级链补全游戏信息。
    支持分批处理，每次调用处理 batch_size 款游戏，可多次调用直到全部完成。
    需要在 config/config.json 中配置 metadata.api_key。

    Args:
        platform: 游戏平台
        batch_size: 每批处理数量（默认50，0=全部一次处理）

    Returns:
        补全结果（含已完成/剩余数量）
    """
    try:
        syncer = LibrarySyncer(config)
        result = await syncer.enrich_library(platform, batch_size=batch_size)
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def setup_epic_account() -> Dict[str, Any]:
    """
    配置 Epic Games 账号（首次使用）

    使用 Legendary 进行认证。如果已认证则直接返回账号信息。
    如果未认证，会打开浏览器引导用户登录，用户需将 authorizationCode
    通过 complete_epic_auth() 工具提交。

    Returns:
        配置结果
    """
    try:
        auth = EpicAuthManager(config)
        result = await auth.interactive_login()

        if result.get("authenticated"):
            return {
                "success": True,
                "message": "Epic 账号配置成功",
                "account_id": result.get("account_id", ""),
                "display_name": result.get("display_name", ""),
                "next_step": "调用 sync_library('epic') 同步游戏库",
            }
        else:
            return {
                "success": False,
                "message": "需要完成认证",
                "login_url": result.get("login_url", ""),
                "next_step": (
                    "在浏览器中登录 Epic Games，复制页面上 JSON 的 authorizationCode 值，"
                    "然后调用 complete_epic_auth(authorization_code) 完成认证"
                ),
            }

    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def complete_epic_auth(authorization_code: str) -> Dict[str, Any]:
    """
    使用 authorizationCode 完成 Epic Games 认证

    在 setup_epic_account() 打开浏览器登录后，将页面上显示的 JSON 中
    authorizationCode 的值传入此工具完成认证。

    Args:
        authorization_code: 从 legendary.gl/epiclogin 页面获取的 authorizationCode

    Returns:
        认证结果
    """
    try:
        auth = EpicAuthManager(config)
        result = await auth.complete_auth(authorization_code)

        if result.get("success"):
            return {
                "success": True,
                "message": "Epic 账号认证成功",
                "account_id": result.get("account_id", ""),
                "display_name": result.get("display_name", ""),
                "next_step": "调用 sync_library('epic') 同步游戏库",
            }
        else:
            return {
                "success": False,
                "error": result.get("message", "认证失败"),
                "hint": "请确认 authorizationCode 正确且未过期，然后重试",
            }

    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def setup_gog_account() -> Dict[str, Any]:
    """
    配置 GOG 账号（首次使用）

    使用 OAuth2 进行认证。如果已认证则直接返回账号信息。
    如果未认证，会打开浏览器引导用户登录 GOG，登录成功后页面会跳转到
    embed.gog.com/on_login_success?code=...，用户需将地址栏 URL（或其中的 code）
    通过 complete_gog_auth() 工具提交。

    Returns:
        配置结果
    """
    try:
        auth = GOGAuthManager(config)
        result = await auth.interactive_login()

        if result.get("authenticated"):
            return {
                "success": True,
                "message": "GOG 账号配置成功",
                "account_id": result.get("account_id", ""),
                "display_name": result.get("display_name", ""),
                "next_step": "调用 sync_library('gog') 同步游戏库",
            }
        else:
            return {
                "success": False,
                "message": "需要完成认证",
                "login_url": result.get("login_url", ""),
                "next_step": (
                    "在浏览器中登录 GOG，登录成功后复制地址栏的完整 URL"
                    "（embed.gog.com/on_login_success?code=...），"
                    "然后调用 complete_gog_auth(authorization_code) 完成认证"
                ),
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def complete_gog_auth(authorization_code: str) -> Dict[str, Any]:
    """
    使用 authorizationCode 完成 GOG 认证

    在 setup_gog_account() 打开浏览器登录后，将地址栏的完整 URL
    （embed.gog.com/on_login_success?code=...）或其中 code 的值传入此工具完成认证。

    Args:
        authorization_code: 登录成功页面的 URL 或其中的 code 值

    Returns:
        认证结果
    """
    try:
        auth = GOGAuthManager(config)
        result = await auth.complete_auth(authorization_code)

        if result.get("success"):
            return {
                "success": True,
                "message": "GOG 账号认证成功",
                "account_id": result.get("account_id", ""),
                "display_name": result.get("display_name", ""),
                "next_step": "调用 sync_library('gog') 同步游戏库",
            }
        else:
            return {
                "success": False,
                "error": result.get("message", "认证失败"),
                "hint": "请确认复制的 URL 或 code 正确且未过期，然后重试",
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def setup_steam_account(api_key: str, steam_id: str) -> Dict[str, Any]:
    """
    配置 Steam Web API 账号

    Steam 同步使用官方 Web API，需要两项凭证：
    - api_key: 在 https://steamcommunity.com/dev/apikey 免费申请
    - steam_id: SteamID64（17 位数字），可在 https://steamid.io 查询

    注意：Steam 个人资料的『游戏详情』需设为公开，否则拉不到游戏库。
    配置会保存到 config.json，之后调用 sync_library('steam') 即可同步。

    Args:
        api_key: Steam Web API Key
        steam_id: SteamID64（17 位数字）

    Returns:
        配置结果
    """
    try:
        steam_cfg = config.platforms.get("steam")
        if steam_cfg is None:
            from .config import PlatformConfig
            steam_cfg = PlatformConfig()
            config.platforms["steam"] = steam_cfg
        steam_cfg.api_key = api_key.strip()
        steam_cfg.steam_id = steam_id.strip()
        steam_cfg.enabled = True
        config.save()
        return {
            "success": True,
            "message": "Steam 账号配置成功",
            "next_step": "调用 sync_library('steam') 同步游戏库",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def list_games(
    platform: str = "epic",
    genre: Optional[str] = None,
    search: Optional[str] = None
) -> str:
    """
    列出已同步的游戏库
    
    Args:
        platform: 游戏平台
        genre: 按类型过滤（可选）
        search: 搜索关键词（可选）
        
    Returns:
        游戏列表
    """
    try:
        syncer = LibrarySyncer(config)
        games = await syncer.load_library(platform)
        
        # 过滤
        if genre:
            games = [g for g in games if genre.lower() in g.get('genres', [])]
        
        if search:
            games = [g for g in games if search.lower() in g.get('title', '').lower()]
        
        # 格式化输出
        output = f"📚 {platform.upper()} 游戏库 ({len(games)} 款游戏)\n\n"
        for i, game in enumerate(games[:20], 1):  # 最多显示 20 个
            display_name = format_display_name(game.get('title', ''))
            output += f"{i}. **{display_name}**\n"
            if game.get('genres'):
                output += f"   类型: {', '.join(game['genres'][:3])}\n"
            if game.get('rating'):
                output += f"   评分: {game['rating']}/5\n"
            output += "\n"
        
        if len(games) > 20:
            output += f"... 还有 {len(games) - 20} 款游戏\n"
        
        return output
        
    except Exception as e:
        return f"❌ 加载失败: {str(e)}"


@mcp.tool()
async def format_games_for_llm(
    platform: str = "epic",
    query: str = "",
    max_games: int = 20
) -> str:
    """
    将游戏数据格式化为适合 LLM Prompt 的文本
    
    此工具专门用于准备数据，让 AI Agent 可以直接将其嵌入 Prompt。
    
    Args:
        platform: 游戏平台
        query: 用户查询（会包含在输出中）
        max_games: 最多包含的游戏数量
        
    Returns:
        格式化后的文本
    """
    try:
        syncer = LibrarySyncer(config)
        games = await syncer.load_library(platform)

        if not games:
            return "游戏库为空"

        # 应用中文优先的显示名称格式
        for g in games:
            g["title"] = format_display_name(g.get("title", ""))

        processor = GameLibraryProcessor()
        return processor.format_for_llm_prompt(games[:max_games], query)
        
    except Exception as e:
        return f"格式化失败: {str(e)}"


def _build_game_line(
    g: Dict[str, Any], platform: str, max_desc_len: int, has_playtime: bool
) -> str:
    """构建单款游戏的紧凑摘要行（跨平台模式用，带 [平台] 前缀）"""
    title = format_display_name(g.get("title", "?"))
    genres = ",".join(g.get("genres", [])[:4]) or "-"
    rating = g.get("rating", 0)
    rating_str = f"{rating:.1f}" if rating else "-"
    year = (g.get("release_date") or "")[:4] or "-"

    # 提取最有意义的标签（排除 Singleplayer、Steam Achievements 等通用标签）
    skip_tags = {
        "singleplayer", "steam achievements", "full controller support",
        "steam cloud", "multiplayer", "co-op", "controller",
        "steam trading cards", "cooperative", "steam workshop",
    }
    meaningful_tags = [t for t in g.get("tags", []) if t.lower() not in skip_tags][:4]
    tags_str = ",".join(meaningful_tags) if meaningful_tags else "-"

    desc = (g.get("description") or "")[:max_desc_len].replace("\n", " ").strip()
    if desc:
        desc = desc + ("..." if len(g.get("description", "")) > max_desc_len else "")
    else:
        desc = "-"

    line = f"[{platform}] {title} | {genres} | {rating_str} | {year} | {tags_str} | {desc}"
    if has_playtime:
        minutes = g.get("playtime_minutes", 0)
        line += f" | {minutes/60:.1f}" if minutes else " | -"
    # 疑似非游戏（OST/DLC/攻略等）标记，供 Agent 复判
    if GameLibraryProcessor.is_likely_nongame(g):
        line += "  ⚠疑似非游戏"
    return line


async def _smart_recommend_all(
    syncer: LibrarySyncer, query: str, max_desc_len: int
) -> str:
    """
    跨平台聚合推荐数据接口

    合并 epic/steam/gog 三个库（不含 galaxy 聚合库，避免双重计数），每款游戏标注
    所属平台；对"疑似同款"做程序初筛并附加提示，最终是否同款、如何呈现由 Agent 复判。
    """
    from .metadata.steam_client import SteamClient
    norm = SteamClient._normalize
    clean = SteamClient._clean_title

    # 加载三个平台库（galaxy 不参与，避免与单平台库双重计数）
    libs: Dict[str, List[Dict[str, Any]]] = {}
    for plat in ("epic", "steam", "gog"):
        try:
            games = await syncer.load_library(plat)
            if games:
                libs[plat] = games
        except Exception:
            continue

    if not libs:
        return "游戏库为空（未找到 epic/steam/gog 任一平台库，请先同步）"

    # 程序初筛：exact（归一化标题完全相同）/ loose（去版本后缀后相同，疑似）
    processor = GameLibraryProcessor()
    groups = processor.group_cross_platform(libs)
    exact_by_key = {grp["key"]: grp for grp in groups["exact"]}
    loose_by_key = {grp["key"]: grp for grp in groups["loose"]}

    # 是否展示游玩时长列（Steam 库有 playtime 即展示）
    has_playtime = any(
        g.get("playtime_minutes", 0) for games in libs.values() for g in games
    )

    plat_counts = {p: len(gs) for p, gs in libs.items()}
    total = sum(plat_counts.values())
    count_str = " / ".join(f"{p} {c}" for p, c in plat_counts.items())

    lines = [
        f"# 跨平台游戏库摘要 | 共 {total} 款（{count_str}）",
        f"# 用户请求: {query}" if query else "",
        "# 格式: [平台] 名称 | 类型 | 评分 | 年份 | 关键标签 | 简介"
        + (" | 游玩时长(h)" if has_playtime else ""),
        "",
        "# —— 跨平台复判指令（给 Agent）——",
        "# ◆ exact 标记：程序判定为同款（归一化标题完全相同）。可直接告知用户"
        "『此游戏在 X/Y 平台都有』，让用户自选版本。",
        "# ◇ loose 标记：仅『疑似』同款（去版本后缀后相同，如本体 vs "
        "Redux/Definitive/Remastered）。",
        "#   是否真同款由你判断；不确定就如实告诉用户两个版本都存在，让用户自己选，"
        "不要擅自合并或遗漏。",
        "# 程序只做初筛，最终如何呈现由你决定。",
        "# 中文名标注：游戏库标题多为英文（数据源限制）。向用户呈现推荐结果时，"
        "若你确知某游戏常用的中文译名，请在英文标题后用括号附上，如 "
        "『Vampire Survivors（吸血鬼幸存者）』；不确定的不要编造，保持原标题即可。",
        "",
    ]

    # 逐平台逐游戏输出，附加跨平台标记
    for plat in ("epic", "steam", "gog"):
        games = libs.get(plat)
        if not games:
            continue
        for g in games:
            title = g.get("title", "")
            line = _build_game_line(g, plat, max_desc_len, has_playtime)
            sk = norm(title)
            if sk and sk in exact_by_key:
                plats = "/".join(exact_by_key[sk]["platforms"])
                line += f"  ◆多平台[{plats}]"
            else:
                lk = norm(clean(title))
                if lk and lk in loose_by_key:
                    grp = loose_by_key[lk]
                    # 列出同组其他平台的原始标题，供 Agent 复判
                    others = {p: t for p, t in grp["titles"].items() if p != plat}
                    if others:
                        parts = ",".join(f"{p}={t}" for p, t in others.items())
                        line += f"  ◇疑似同款({parts})"
            lines.append(line)

    # 末尾汇总 loose 组，便于 Agent 整体把握
    if loose_by_key:
        lines.append("")
        lines.append("# —— 跨平台疑似同款汇总（loose，需你复判）——")
        for grp in loose_by_key.values():
            plats = "/".join(grp["platforms"])
            titles = ",".join(f"{p}={t}" for p, t in grp["titles"].items())
            lines.append(f"# · [{plats}] {titles}")

    return "\n".join(lines)


@mcp.tool()
async def smart_recommend(
    platform: str = "epic",
    query: str = "",
    max_desc_len: int = 80
) -> str:
    """
    智能推荐数据接口

    返回游戏库全量紧凑摘要（每款游戏一行），供 AI Agent 做深度分析。
    包含：标题、类型、评分、年份、关键标签、简短描述。
    AI Agent 应基于玩法机制、设计哲学、情感体验等多维度进行推荐，
    而非简单的标签匹配。

    platform="all" 时进入跨平台模式：合并 epic/steam/gog 三个库，每款游戏标注
    所属平台，并对"疑似同款"给出程序初筛提示（exact=确定同款，loose=疑似需你判断）。
    程序只做初筛，最终是否同款、如何向用户呈现由你（Agent）判断；不确定就如实
    告诉用户"这游戏在某几个平台都有/疑似都有"，让用户自己选玩哪个版本。

    中文名标注：游戏库标题多为英文（数据源限制）。返回的摘要里会带一段给 Agent
    的指令——向用户呈现推荐时，若确知某游戏常用中文译名就用括号附在英文标题后
    （如 Vampire Survivors（吸血鬼幸存者）），不确定的保持原标题，不要编造。

    Args:
        platform: 游戏平台（epic/steam/gog/galaxy），或 "all" 跨平台聚合
        query: 用户的具体需求或参考游戏（如"类似吸血鬼幸存者"）
        max_desc_len: 描述截断长度（默认80字符）

    Returns:
        全量游戏库紧凑文本，供 LLM 深度分析
    """
    try:
        syncer = LibrarySyncer(config)

        if platform == "all":
            return await _smart_recommend_all(syncer, query, max_desc_len)

        games = await syncer.load_library(platform)

        if not games:
            return "游戏库为空"

        # 判断该库是否有游玩时长数据（Steam Web API 提供）
        has_playtime = any(g.get("playtime_minutes", 0) for g in games)
        fmt_hint = "# 格式: 名称 | 类型 | 评分 | 年份 | 关键标签 | 简介"
        if has_playtime:
            fmt_hint += " | 游玩时长(h)"

        # 构建紧凑摘要
        lines = [
            f"# 游戏库摘要 | 平台: {platform} | 共 {len(games)} 款",
            f"# 用户请求: {query}" if query else "",
            fmt_hint,
            "# 中文名标注：游戏库标题多为英文（数据源限制）。向用户呈现推荐结果时，"
            "若你确知某游戏常用的中文译名，请在英文标题后用括号附上，如 "
            "『Vampire Survivors（吸血鬼幸存者）』；不确定的不要编造，保持原标题即可。",
            "",
        ]

        for g in games:
            title = format_display_name(g.get("title", "?"))
            genres = ",".join(g.get("genres", [])[:4]) or "-"
            rating = g.get("rating", 0)
            rating_str = f"{rating:.1f}" if rating else "-"
            year = (g.get("release_date") or "")[:4] or "-"

            # 提取最有意义的标签（排除通用标签如 Singleplayer、Steam Achievements）
            skip_tags = {
                "singleplayer", "steam achievements", "full controller support",
                "steam cloud", "multiplayer", "co-op", "controller",
                "steam trading cards", "cooperative", "steam workshop",
            }
            meaningful_tags = [
                t for t in g.get("tags", [])
                if t.lower() not in skip_tags
            ][:4]
            tags_str = ",".join(meaningful_tags) if meaningful_tags else "-"

            desc = (g.get("description") or "")[:max_desc_len].replace("\n", " ").strip()
            if desc:
                desc = desc + ("..." if len(g.get("description", "")) > max_desc_len else "")
            else:
                desc = "-"

            line = f"{title} | {genres} | {rating_str} | {year} | {tags_str} | {desc}"
            if has_playtime:
                minutes = g.get("playtime_minutes", 0)
                line += f" | {minutes/60:.1f}" if minutes else " | -"
            if GameLibraryProcessor.is_likely_nongame(g):
                line += "  ⚠疑似非游戏"
            lines.append(line)

        return "\n".join(lines)

    except Exception as e:
        return f"数据加载失败: {str(e)}"


def main():
    """启动 MCP 服务器"""
    import sys
    sys.stderr.write(f"🚀 AIPickMyGame MCP Server 启动中...\n")
    sys.stderr.write(f"📂 配置路径: {config.config_path}\n")
    sys.stderr.write(f"🔐 Token 存储: {config.token_storage_type}\n")
    sys.stderr.write("\n等待客户端连接...\n")
    sys.stderr.flush()
    
    mcp.run()


if __name__ == "__main__":
    main()
