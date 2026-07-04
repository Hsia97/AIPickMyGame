# Steam Store 元数据客户端（国内直连，无需代理）
# 通过 Steam Store API 获取完整游戏数据
# 国内可直连，不需要代理，是大陆用户的首选元数据源

import os
import re
import time
import winreg
import httpx
from typing import Dict, Any, Optional, List


class SteamClient:
    """
    Steam Store API 客户端（国内直连）
    """

    SEARCH_URL = "https://store.steampowered.com/api/storesearch"
    DETAIL_URL = "https://store.steampowered.com/api/appdetails"

    def __init__(self, language="schinese", country="CN"):
        """
        初始化 Steam 客户端

        Args:
            language: 语言代码，默认 schinese（简体中文）
            country: 国家/地区代码，默认 CN（中国）
        """
        self.language = language
        self.country = country
        self._last_request_time: float = 0.0
        self._rate_limit_delay: float = 1.0

        # 熔断：store.steampowered.com 在大陆常被整域封锁（GFW），
        # 此时每次请求会连接超时。连续多次连接失败即熔断，
        # 后续请求直接返回 None，避免每款游戏干等数十秒。
        self._conn_fail_streak: int = 0
        self._store_blocked: bool = False
        self._BLOCK_THRESHOLD: int = 3

        # Steam Store 国内可直连，明确禁用代理（trust_env=False 阻止 httpx 读取系统代理）
        # 连接超时单独设短（5s）：域名被墙时快速失败，不再 30s 干等
        self._client = httpx.Client(
            timeout=httpx.Timeout(15.0, connect=5.0),
            follow_redirects=True,
            trust_env=False,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0"
            },
        )

    def _note_conn_error(self) -> None:
        """记录一次连接层失败；连续达到阈值则熔断 store 域名。"""
        self._conn_fail_streak += 1
        if self._conn_fail_streak >= self._BLOCK_THRESHOLD and not self._store_blocked:
            self._store_blocked = True
            print(
                f"[SteamClient] 连续 {self._conn_fail_streak} 次连接失败，"
                "判定 store.steampowered.com 当前不可达（可能被墙），"
                "本次同步后续 Steam 请求将直接跳过，转由其它元数据源补全。"
            )

    def _note_success(self) -> None:
        """记录一次成功响应，清零连续失败计数。"""
        self._conn_fail_streak = 0

    @property
    def store_blocked(self) -> bool:
        """store 域名是否已被判定为不可达（熔断生效）。"""
        return self._store_blocked

    def _enforce_rate_limit(self) -> None:
        """
        强制执行速率限制，确保请求间隔不低于 200ms
        """
        elapsed = time.time() - self._last_request_time
        if elapsed < self._rate_limit_delay:
            time.sleep(self._rate_limit_delay - elapsed)
        self._last_request_time = time.time()

    def search_game(self, title: str) -> Optional[Dict[str, Any]]:
        """
        搜索游戏并返回最佳匹配的元数据

        Args:
            title: 游戏名称

        Returns:
            游戏元数据字典，未找到则返回 None
        """
        # 熔断生效：store 已判定不可达，直接跳过
        if self._store_blocked:
            return None
        try:
            # 清洗标题：去掉商标符号、书名号、版本后缀等，提升 Steam 匹配率
            clean_title = self._clean_title(title)

            # 重试机制：最多重试 2 次
            resp = None
            for attempt in range(3):
                self._enforce_rate_limit()
                try:
                    resp = self._client.get(
                        self.SEARCH_URL,
                        params={"term": clean_title, "l": self.language, "cc": self.country},
                    )
                    if resp.status_code == 200:
                        break
                except httpx.TransportError as e:
                    # 连接/超时层错误：计入熔断统计
                    self._note_conn_error()
                    if self._store_blocked:
                        return None
                    if attempt < 2:
                        time.sleep(2 * (attempt + 1))  # 递增等待
                        continue
                    raise
                except Exception:
                    if attempt < 2:
                        time.sleep(2 * (attempt + 1))  # 递增等待
                        continue
                    raise
            if not resp or resp.status_code != 200:
                return None

            # 成功拿到响应，清零连接失败计数
            self._note_success()

            items = resp.json().get("items", [])
            if not items:
                return None

            # 找到最佳匹配
            best = self._find_best_match(clean_title, items)
            if not best:
                return None

            app_id = best.get("id")
            if not app_id:
                return None

            # 获取完整详情（appdetails 提供 genres/description/screenshots 等核心数据）
            detail = self.get_app_details(app_id)
            if detail:
                return detail

            # 详情获取失败（多为限流）：返回 None 而非残缺搜索结果，
            # 使该游戏标记为"未补全"，可在下一批次重试拿到完整数据
            return None

        except Exception as e:
            print(f"[SteamClient] 搜索失败 '{title}': {e}")
            return None

    def get_app_details(self, app_id: int) -> Optional[Dict[str, Any]]:
        """
        获取单个游戏的完整详情

        Args:
            app_id: Steam App ID

        Returns:
            游戏元数据字典，获取失败则返回 None
        """
        # 熔断生效：store 已判定不可达，直接跳过，避免干等
        if self._store_blocked:
            return None
        try:
            # 重试机制：最多重试 2 次
            resp = None
            for attempt in range(3):
                self._enforce_rate_limit()
                try:
                    resp = self._client.get(
                        self.DETAIL_URL,
                        params={"appids": str(app_id), "l": self.language, "cc": self.country},
                    )
                    if resp.status_code == 200:
                        break
                except httpx.TransportError as e:
                    # 连接/超时层错误：计入熔断统计
                    self._note_conn_error()
                    if self._store_blocked:
                        return None
                    if attempt < 2:
                        time.sleep(2 * (attempt + 1))  # 递增等待
                        continue
                    raise
                except Exception:
                    if attempt < 2:
                        time.sleep(2 * (attempt + 1))  # 递增等待
                        continue
                    raise
            if not resp or resp.status_code != 200:
                return None

            # 成功拿到响应，清零连接失败计数
            self._note_success()

            result = resp.json()
            app_data = result.get(str(app_id))
            if not app_data or not app_data.get("success"):
                return None

            data = app_data.get("data")
            return self._parse_app_details(data, app_id)

        except Exception as e:
            print(f"[SteamClient] 获取详情失败 app_id={app_id}: {e}")
            return None

    def _find_best_match(self, title: str, results: List[Dict]) -> Optional[Dict]:
        """
        从搜索结果中找到最佳匹配项

        Args:
            title: 搜索的标题
            results: 搜索结果列表

        Returns:
            最佳匹配的结果项
        """
        # 归一化标题做比较（忽略符号、空格、大小写差异）
        norm_title = self._normalize(title)

        # 第一轮：归一化精确匹配
        for item in results:
            if self._normalize(item.get("name", "")) == norm_title:
                return item

        # 第二轮：归一化包含匹配（双向）
        for item in results:
            norm_name = self._normalize(item.get("name", ""))
            if norm_name and (norm_title in norm_name or norm_name in norm_title):
                return item

        # 都没匹配上，返回第一个结果
        return results[0] if results else None

    @staticmethod
    def _clean_title(title: str) -> str:
        """
        清洗游戏标题用于搜索：去掉商标符号、书名号、常见版本后缀。

        例如：
        - "HOT WHEELS UNLEASHED™" -> "HOT WHEELS UNLEASHED"
        - "《art of rally》 Standard Edition" -> "art of rally"
        - "Dying Light Enhanced Edition" -> "Dying Light"
        - "Barony (Beta)" -> "Barony"
        """
        t = title
        # 去掉商标/版权符号
        t = re.sub(r'[™®©]', '', t)
        # 去掉书名号、方括号
        t = re.sub(r'[《》【】]', '', t)
        # 去掉括号及其内容（如 (Beta)、(逃出百慕大)）
        t = re.sub(r'[\(（][^\)）]*[\)）]', '', t)
        # 去掉常见版本/edition 后缀
        version_suffixes = [
            r'\bStandard Edition\b', r'\bEnhanced Edition\b', r'\bDefinitive Edition\b',
            r'\bComplete Edition\b', r'\bComplete Journey\b', r'\bGold Edition\b',
            r'\bDeluxe Edition\b', r'\bGOTY Edition\b', r'\bGame of the Year Edition\b',
            r'\bRe-Elected\b', r'\bRedux\b', r'\bRemastered\b', r'\bPre-game editor\b',
            r'\bThe Final Cut\b', r'\bBeta\b',
        ]
        for suffix in version_suffixes:
            t = re.sub(suffix, '', t, flags=re.IGNORECASE)
        # 折叠多余空格
        t = re.sub(r'\s+', ' ', t).strip()
        # 去掉首尾残留的标点
        t = t.strip(' -:：')
        return t or title.strip()

    @staticmethod
    def _normalize(name: str) -> str:
        """归一化名称用于匹配：转小写，只保留字母数字和中文，去掉所有符号空格。"""
        name = name.lower()
        # 只保留字母、数字、中文字符
        name = re.sub(r'[^\w一-鿿]', '', name)
        return name

    def _parse_search_result(self, item: Dict) -> Dict[str, Any]:
        """
        从搜索结果中解析基础元数据（作为 appdetails 失败的后备方案）

        Args:
            item: 搜索结果中的一项

        Returns:
            解析后的元数据字典
        """
        # 提取类型
        genres = [
            g.get("description", "")
            for g in item.get("genres", [])
            if g.get("description")
        ]

        # 提取标签（最多 10 个）
        tags = [
            c.get("description", "")
            for c in item.get("categories", [])[:10]
            if c.get("description")
        ]

        # 提取开发商
        developers = item.get("developers", [])
        developer = developers[0] if developers else ""

        # 提取发行商
        publishers = item.get("publishers", [])
        publisher = publishers[0] if publishers else ""

        # Metacritic 评分转 5 分制
        metascore = item.get("metascore", "")
        try:
            rating = float(metascore) / 20.0 if metascore else 0.0
        except (ValueError, TypeError):
            rating = 0.0

        return {
            "app_id": item.get("id"),
            "title": item.get("name"),
            "developer": developer,
            "publisher": publisher,
            "genres": genres,
            "tags": tags,
            "cover_url": item.get("header_image", ""),
            "short_description": "",
            "release_date": item.get("release_date", {}).get("date", ""),
            "rating": rating,
            "source": "steam_search",
        }

    def _parse_app_details(self, data: Dict, app_id: int) -> Dict[str, Any]:
        """
        解析 Steam appdetails API 返回的完整游戏数据

        Args:
            data: appdetails 返回的 data 字段
            app_id: 游戏的 App ID

        Returns:
            解析后的完整元数据字典
        """
        # 提取类型
        genres = [
            g.get("description", "")
            for g in data.get("genres", [])
            if g.get("description")
        ]

        # 提取标签（最多 10 个）
        tags = [
            c.get("description", "")
            for c in data.get("categories", [])[:10]
            if c.get("description")
        ]

        # 简介
        short_description = data.get("short_description", "")

        # 开发商和发行商
        developers = data.get("developers", [])
        publishers = data.get("publishers", [])
        developer = ", ".join(developers) if developers else ""
        publisher = ", ".join(publishers) if publishers else ""

        # 截图（最多 4 张）
        screenshots = [
            s.get("path_full", "")
            for s in data.get("screenshots", [])[:4]
            if s.get("path_full")
        ]

        # 封面图
        header_image = data.get("header_image", "")

        # 发售日期
        release_date = data.get("release_date", {}).get("date", "")

        # 基于用户评测推荐数计算评分
        recommendations_total = data.get("recommendations", {}).get("total", 0)
        try:
            rating = min(float(recommendations_total) / 20.0, 5.0)
            rating = round(rating, 1)
        except (ValueError, TypeError):
            rating = 0.0

        return {
            "app_id": str(app_id),
            "title": data.get("name", ""),
            "type": data.get("type", ""),
            "developer": developer,
            "publisher": publisher,
            "genres": genres,
            "tags": tags,
            "short_description": short_description,
            "cover_url": header_image,
            "screenshots": screenshots,
            "release_date": release_date,
            "rating": rating,
            "source": "steam",
        }

    def close(self) -> None:
        """
        关闭 HTTP 客户端连接
        """
        if self._client:
            self._client.close()

    @staticmethod
    def _detect_system_proxy() -> Optional[str]:
        """
        检测系统代理设置

        优先检查环境变量，然后检查 Windows 注册表中的代理配置

        Returns:
            代理地址字符串，未找到则返回 None
        """
        # 优先检查环境变量
        for var in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]:
            proxy = os.environ.get(var)
            if proxy:
                return proxy

        # 检查 Windows 注册表
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
            ) as key:
                proxy_enable, _ = winreg.QueryValueEx(key, "ProxyEnable")
                if proxy_enable:
                    proxy_server, _ = winreg.QueryValueEx(key, "ProxyServer")
                    if proxy_server:
                        return "http://" + proxy_server
        except (OSError, FileNotFoundError):
            pass

        return None
