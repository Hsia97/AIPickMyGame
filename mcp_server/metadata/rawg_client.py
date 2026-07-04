"""
RAWG.io 游戏元数据客户端

通过 RAWG.io API 按游戏标题搜索，获取：
- 评分 (rating)
- 类型 (genres)
- 标签 (tags)
- 发行日期 (released)
- 描述 (description)
- 截图 (screenshots)
- 开发者/发行商 (developers/publishers)
"""

import re
import httpx
from typing import Dict, Any, Optional, List


def format_display_name(title: str) -> str:
    """
    格式化游戏显示名称：中文名优先，英文名放括号里。

    处理规则：
    - "土豆兄弟(Brotato)" → "土豆兄弟（Brotato）"  （已是理想格式，规范化括号）
    - "Enter the Gungeon" → "Enter the Gungeon"      （纯英文保持不变）
    - "毛线先生 (CHUCHEL)" → "毛线先生（CHUCHEL）"    （规范化括号）
    - "《孤星猎人》" → "孤星猎人"                     （去掉书名号）
    - "Down in Bermuda (逃出百慕大)" → "逃出百慕大（Down in Bermuda）" （中文移到前面）
    """
    if not title:
        return ""

    # 去掉书名号
    title = re.sub(r'^《(.+)》$', r'\1', title.strip())

    # 检查是否包含中文字符
    has_chinese = bool(re.search(r'[\u4e00-\u9fff]', title))
    if not has_chinese:
        return title

    # 模式1: "中文(English)" 或 "中文 (English)" — 第一部分必须包含中文
    m = re.match(r'^(.+?)[\s]*[(\uff08](.+?)[)\uff09]$', title)
    if m and re.search(r'[\u4e00-\u9fff]', m.group(1)):
        cn_part = m.group(1).strip()
        en_part = m.group(2).strip()
        return f"{cn_part}（{en_part}）"

    # 模式2: "English (中文)" — 中文移到前面
    m = re.match(r'^(.+?)[\s]*[(\uff08]([\u4e00-\u9fff][\u4e00-\u9fff\w\s]*)[)\uff09]$', title)
    if m and not re.search(r'[\u4e00-\u9fff]', m.group(1)):
        en_part = m.group(1).strip()
        cn_part = m.group(2).strip()
        return f"{cn_part}（{en_part}）"

    # 模式3: "《English》中文后缀" → "中文后缀（English）"
    m = re.match(r'^《(.+?)》\s*(.+)$', title)
    if m and re.search(r'[\u4e00-\u9fff]', m.group(2)):
        en_part = m.group(1).strip()
        cn_part = m.group(2).strip()
        return f"{cn_part}（{en_part}）"

    # 模式4: "English 中文"（无括号，空格分隔）→ "中文（English）"
    m = re.match(r'^([A-Za-z0-9\s:\-\'!?.]+?)\s+([\u4e00-\u9fff][\u4e00-\u9fff\w\s]*)$', title)
    if m:
        en_part = m.group(1).strip()
        cn_part = m.group(2).strip()
        return f"{cn_part}（{en_part}）"

    # 模式5: 纯中文或已经是理想格式
    return title


class RAWGClient:
    """RAWG.io API 客户端"""

    BASE_URL = "https://api.rawg.io/api"

    def __init__(self, api_key: str):
        self.api_key = api_key
        proxy_url = self._detect_system_proxy()
        transport = None
        proxy = None
        if proxy_url:
            proxy = proxy_url
            print(f"Using system proxy: {proxy_url}")
        self._client = httpx.Client(
            timeout=20.0,
            follow_redirects=True,
            proxy=proxy,
        )

    def search_game(self, title: str) -> Optional[Dict[str, Any]]:
        """
        按标题搜索游戏，返回最佳匹配结果。

        Args:
            title: 游戏标题

        Returns:
            游戏元数据字典，未找到则返回 None
        """
        # 清理标题：去掉中文书名号、特殊符号
        clean_title = re.sub(r'[《》【】]', '', title).strip()

        try:
            resp = self._client.get(
                f"{self.BASE_URL}/games",
                params={"key": self.api_key, "search": clean_title, "page_size": 5},
            )
            if resp.status_code != 200:
                print(f"RAWG search failed ({resp.status_code}) for: {clean_title}")
                return None

            results = resp.json().get("results", [])
            if not results:
                return None

            # 找到最佳匹配：标题最接近的
            best = self._find_best_match(clean_title, results)
            if not best:
                return None

            # 获取详细信息
            return self._get_game_detail(best["id"])

        except Exception as e:
            print(f"RAWG search error for '{clean_title}': {e}")
            return None

    def _find_best_match(self, title: str, results: List[Dict]) -> Optional[Dict]:
        """从搜索结果中找到最佳匹配"""
        title_lower = title.lower()

        # 精确匹配
        for r in results:
            if r.get("name", "").lower() == title_lower:
                return r

        # 包含匹配
        for r in results:
            name = r.get("name", "").lower()
            if title_lower in name or name in title_lower:
                return r

        # 返回第一个结果（如果相似度足够）
        if results:
            return results[0]

        return None

    def _get_game_detail(self, game_id: int) -> Optional[Dict[str, Any]]:
        """获取游戏详细信息"""
        try:
            resp = self._client.get(
                f"{self.BASE_URL}/games/{game_id}",
                params={"key": self.api_key},
            )
            if resp.status_code != 200:
                return None

            data = resp.json()
            return self._parse_game_data(data)

        except Exception as e:
            print(f"RAWG detail error for game {game_id}: {e}")
            return None

    def _parse_game_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """解析 RAWG 游戏数据为标准格式"""
        # 提取类型
        genres = [g.get("name", "") for g in data.get("genres", [])]

        # 提取标签（取前 10 个）
        tags = [t.get("name", "") for t in data.get("tags", [])[:10]]

        # 提取开发者
        developers = [d.get("name", "") for d in data.get("developers", [])]

        # 提取发行商
        publishers = [p.get("name", "") for p in data.get("publishers", [])]

        # 提取截图 URL
        screenshots = []
        for s in data.get("short_screenshots", [])[:4]:
            img = s.get("image", "")
            if img:
                screenshots.append(img)

        # 清理 HTML 描述
        description = data.get("description", "") or ""
        description = re.sub(r'<[^>]+>', '', description).strip()
        if len(description) > 500:
            description = description[:500] + "..."

        # 提取平台
        platforms = []
        for p in data.get("platforms", []):
            plat = p.get("platform", {})
            platforms.append(plat.get("name", ""))

        return {
            "title": data.get("name", ""),
            "slug": data.get("slug", ""),
            "genres": genres,
            "tags": tags,
            "rating": round(data.get("rating", 0), 1),
            "ratings_count": data.get("ratings_count", 0),
            "release_date": data.get("released", ""),
            "description": description,
            "developers": developers,
            "publishers": publishers,
            "screenshots": screenshots,
            "metacritic_score": data.get("metacritic", 0) or 0,
            "platforms": platforms,
            "cover_url": data.get("background_image", ""),
            "rawg_url": data.get("website", ""),
        }

    def close(self):
        """关闭 HTTP 客户端"""
        self._client.close()

    @staticmethod
    def _detect_system_proxy() -> Optional[str]:
        """检测 Windows 系统代理设置"""
        import os
        # 优先检查环境变量
        for var in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY"):
            val = os.environ.get(var) or os.environ.get(var.lower())
            if val:
                return val

        # 从 Windows 注册表读取
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

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def _extract_steam_appid(game: Dict[str, Any]) -> Optional[int]:
    """从游戏记录中提取 Steam appid，用于 appdetails 直查（跳过搜索）。

    两类带 appid 的来源：
    - Steam Web API 同步：游戏带 steam_app_id 字段
    - Galaxy 聚合的 steam 平台游戏：app_name 形如 "steam_{appid}"，external_id 即 appid

    优先级：steam_app_id 字段 > app_name 的 steam_ 前缀。
    其它平台（epic/gog/uplay/xbox/origin）返回 None，走标题搜索。
    """
    raw = game.get("steam_app_id")
    if raw:
        try:
            return int(raw)
        except (ValueError, TypeError):
            pass
    app_name = game.get("app_name", "")
    if isinstance(app_name, str) and app_name.startswith("steam_"):
        suffix = app_name[len("steam_"):]
        if suffix.isdigit():
            return int(suffix)
    return None


def enrich_games(games: List[Dict[str, Any]], api_key: str) -> List[Dict[str, Any]]:
    """
    批量为游戏列表补全元数据，使用 geo 感知的多级降级链：

    地理检测 → 智能路由 →
    - 大陆用户：Steam（首选，完整数据）→ RAWG（需代理）→ IGDB
    - 海外用户：RAWG（首选，完整数据）→ Steam → IGDB

    优先级说明：
    1. Steam Store — 完整数据（类型、标签、描述、截图、开发商、评分等），大陆可直连
    2. RAWG.io — 完整数据，海外可直连 / 大陆需代理
    3. IGDB.com — 全球通用降级（类型、描述、评分、截图）
    4. 保留 Legendary 原有数据

    Args:
        games: 游戏列表（来自 Legendary）
        api_key: RAWG.io API Key（可选，无则跳过 RAWG 层）

    Returns:
        补全后的游戏列表
    """
    rawg_client = None
    steam_client = None
    igdb_client = None
    rawg_count = 0
    steam_count = 0
    igdb_count = 0
    skipped = 0

    # 检测代理和地理环境
    proxy = RAWGClient._detect_system_proxy()

    is_mainland = False
    try:
        from ..utils.geo_utils import is_mainland_china_sync
        is_mainland = is_mainland_china_sync(timeout=2.0)
        if is_mainland:
            print("检测到中国大陆网络环境")
        else:
            print("检测到海外网络环境")
    except Exception:
        pass

    # 初始化 Steam 客户端（大陆可直连，海外也可用）
    try:
        from .steam_client import SteamClient
        from ..config import AppConfig
        _cfg = AppConfig()
        steam_client = SteamClient(
            language=_cfg.metadata.steam_language,
            country=_cfg.metadata.steam_country,
        )
        print("启用 Steam 元数据源")
    except Exception as e:
        print(f"Steam 客户端初始化失败: {e}")

    # 大陆：RAWG 需代理才启用；海外：有 key 就启用
    use_rawg = bool(api_key) and (not is_mainland or proxy)

    if use_rawg:
        try:
            rawg_client = RAWGClient(api_key)
            print("启用 RAWG 元数据源")
        except Exception as e:
            print(f"RAWG 客户端初始化失败: {e}")

    # IGDB 作为降级源（大陆首选降级 / 海外无 key 时降级）
    use_igdb = is_mainland or (not api_key and not proxy)
    if use_igdb:
        try:
            from .igdb_client import IGDBClient
            from ..config import AppConfig
            cfg = AppConfig()
            igdb_id = cfg.metadata.igdb_client_id
            igdb_secret = cfg.metadata.igdb_client_secret
            if igdb_id and igdb_secret:
                igdb_client = IGDBClient(igdb_id, igdb_secret)
                print("启用 IGDB 元数据源")
            else:
                print("IGDB 未配置 Client ID/Secret，跳过。需在 config.json 的 metadata 中填写 igdb_client_id 和 igdb_client_secret")
        except Exception as e:
            print(f"IGDB 客户端初始化失败: {e}")

    try:
        for game in games:
            # 已有可靠来源的完整数据才跳过（有类型+描述，且来源是 steam/rawg/igdb）
            reliable = game.get("_meta_source") in ("steam", "rawg", "igdb")
            if reliable and game.get("genres") and game.get("description"):
                skipped += 1
                continue

            title = game.get("title", "")
            if not title:
                continue

            enriched = False

            # 根据地理环境确定数据源优先级：大陆 Steam → RAWG → IGDB  |  海外 RAWG → Steam → IGDB
            source_order = ["steam", "rawg", "igdb"] if is_mainland else ["rawg", "steam", "igdb"]

            for source in source_order:
                if enriched:
                    break

                # --- Steam（完整数据 via appdetails API，大陆可直连） ---
                if source == "steam" and steam_client:
                    try:
                        # 优化：带 appid 的游戏（Steam 同步 / Galaxy 的 steam 平台）直查
                        # appdetails，跳过 storesearch 搜索——少一半请求、更准、缓解限流
                        appid = _extract_steam_appid(game)
                        if appid:
                            print(f"  [Steam] {title} (appid={appid} 直查)...")
                            steam_data = steam_client.get_app_details(appid)
                        else:
                            print(f"  [Steam] {title} (标题搜索)...")
                            steam_data = steam_client.search_game(title)
                        # Steam 有可靠的 type 字段：game / dlc / music / demo / series / mod 等。
                        # 仅当 type 为 game 时才采用其元数据；OST/DLC 等非游戏条目不污染，
                        # 让该条降级到其它源（下一轮可能由 RAWG/IGDB 处理或标记为非游戏）。
                        if steam_data and steam_data.get("type") and steam_data.get("type") != "game":
                            t = steam_data.get("type")
                            print(f"  [Steam] {title} 命中非游戏类型 (type={t})，跳过采用，降级其它源")
                            # 保留 type 信号供推荐层标记疑似非游戏（即便元数据不采用）
                            game["steam_type"] = t
                            steam_data = None
                        if steam_data:
                            game["genres"] = steam_data.get("genres") or game.get("genres", [])
                            game["tags"] = steam_data.get("tags") or game.get("tags", [])
                            game["rating"] = steam_data.get("rating") or game.get("rating", 0)
                            game["ratings_count"] = steam_data.get("ratings_count", 0)
                            game["release_date"] = steam_data.get("release_date") or game.get("release_date", "")
                            game["description"] = steam_data.get("short_description") or game.get("description", "")
                            game["developers"] = steam_data.get("developers") or game.get("developers", [])
                            game["publishers"] = steam_data.get("publishers") or game.get("publishers", [])
                            game["screenshots"] = steam_data.get("screenshots") or game.get("screenshots", [])
                            game["metacritic_score"] = steam_data.get("metacritic_score", 0)
                            game["cover_url"] = steam_data.get("cover_url") or game.get("cover_url", "")
                            game["rawg_url"] = steam_data.get("rawg_url", "")
                            game["_meta_source"] = "steam"
                            steam_count += 1
                            enriched = True
                    except Exception as e:
                        print(f"  [Steam] 查询失败: {e}")

                # --- RAWG（完整数据，海外首选 / 大陆需代理） ---
                if source == "rawg" and rawg_client:
                    try:
                        print(f"  [RAWG] {title}...")
                        rawg_data = rawg_client.search_game(title)
                        if rawg_data:
                            game["genres"] = rawg_data.get("genres") or game.get("genres", [])
                            game["tags"] = rawg_data.get("tags") or game.get("tags", [])
                            game["rating"] = rawg_data.get("rating") or game.get("rating", 0)
                            game["ratings_count"] = rawg_data.get("ratings_count", 0)
                            game["release_date"] = rawg_data.get("release_date") or game.get("release_date", "")
                            game["description"] = rawg_data.get("description") or game.get("description", "")
                            game["developers"] = rawg_data.get("developers") or game.get("developers", [])
                            game["publishers"] = rawg_data.get("publishers") or game.get("publishers", [])
                            game["screenshots"] = rawg_data.get("screenshots") or game.get("screenshots", [])
                            game["metacritic_score"] = rawg_data.get("metacritic_score", 0)
                            game["cover_url"] = rawg_data.get("cover_url") or game.get("cover_url", "")
                            game["rawg_url"] = rawg_data.get("rawg_url", "")
                            game["_meta_source"] = "rawg"
                            rawg_count += 1
                            enriched = True
                    except Exception as e:
                        print(f"  [RAWG] 查询失败: {e}")

                # --- IGDB（全球通用降级） ---
                if source == "igdb" and igdb_client:
                    try:
                        print(f"  [IGDB] {title}...")
                        igdb_data = igdb_client.search_game(title)
                        if igdb_data:
                            if not game.get("genres") and igdb_data.get("genres"):
                                game["genres"] = igdb_data["genres"]
                            if not game.get("tags") and igdb_data.get("tags"):
                                game["tags"] = igdb_data["tags"]
                            if not game.get("rating") and igdb_data.get("rating"):
                                game["rating"] = igdb_data["rating"]
                            if not game.get("description") and igdb_data.get("description"):
                                game["description"] = igdb_data["description"]
                            if not game.get("cover_url") and igdb_data.get("cover_url"):
                                game["cover_url"] = igdb_data["cover_url"]
                            if not game.get("screenshots") and igdb_data.get("screenshots"):
                                game["screenshots"] = igdb_data["screenshots"]
                            if igdb_data.get("developers"):
                                game["developers"] = igdb_data["developers"]
                            game["igdb_id"] = igdb_data.get("igdb_id")
                            game["_meta_source"] = game.get("_meta_source", "") or "igdb"
                            igdb_count += 1
                            enriched = True
                    except Exception as e:
                        print(f"  [IGDB] 查询失败: {e}")

            if not enriched:
                game["_meta_source"] = "none"
                print(f"  未找到: {title}")

            # 短暂间隔，尊重 API 限流
            import time
            time.sleep(0.15)

    finally:
        if rawg_client:
            rawg_client.close()
        if steam_client:
            steam_client.close()
        if igdb_client:
            igdb_client.close()

    total_enriched = rawg_count + steam_count + igdb_count
    sources = []
    if rawg_count:
        sources.append(f"RAWG {rawg_count}款")
    if steam_count:
        sources.append(f"Steam {steam_count}款")
    if igdb_count:
        sources.append(f"IGDB {igdb_count}款")
    source_str = ", ".join(sources) if sources else "无"
    print(f"元数据补全完成: {total_enriched}款成功 ({source_str}), {skipped}款跳过")
    return games
