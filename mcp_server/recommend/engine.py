"""
推荐引擎（重构版）

提供游戏库数据处理和筛选功能，由 AI Agent 负责 LLM 调用。
"""

import re
from typing import List, Dict, Any, Optional
from datetime import datetime


# 疑似非游戏（OST/DLC/资料片/攻略）的标题特征——用于推荐时给 Agent 标记复判。
# 这是宽松初筛，仅作提示，不删除条目；最终是否算「游戏」由 Agent 判断。
_NONGAME_TITLE_RE = re.compile(
    r'\b(Soundtrack|Original Sound|OST|Season Pass|Artbook|Art Book|Walkthrough|'
    r'Official Guide|Bonus Content|Supporter Pack|Digital Extras|Making Of|'
    r'Art Pack|Map Pack|Weapon Pack|Character Pack|Cosmetic Pack)\b',
    re.IGNORECASE,
)


class GameLibraryProcessor:
    """游戏库处理器 - 纯数据处理，不调用 LLM"""
    
    def __init__(self):
        pass
    
    def filter_games(
        self,
        games: List[Dict[str, Any]],
        genres: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        min_rating: Optional[float] = None,
        max_release_year: Optional[int] = None,
        min_release_year: Optional[int] = None,
        search_keyword: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        根据条件筛选游戏
        
        Args:
            games: 游戏库列表
            genres: 类型过滤（如 ["Roguelike", "Action"]）
            tags: 标签过滤
            min_rating: 最低评分
            max_release_year: 最晚发行年份
            min_release_year: 最早发行年份
            search_keyword: 关键词搜索（标题）
            limit: 返回数量限制
            
        Returns:
            筛选后的游戏列表
        """
        filtered = games
        
        # 按类型过滤
        if genres:
            filtered = [
                g for g in filtered 
                if any(genre.lower() in [gg.lower() for gg in g.get('genres', [])] 
                      for genre in genres)
            ]
        
        # 按标签过滤
        if tags:
            filtered = [
                g for g in filtered 
                if any(tag.lower() in [t.lower() for t in g.get('tags', [])] 
                      for tag in tags)
            ]
        
        # 按评分过滤
        if min_rating is not None:
            filtered = [
                g for g in filtered 
                if g.get('rating', 0) >= min_rating
            ]
        
        # 按发行年份过滤
        if max_release_year is not None:
            filtered = [
                g for g in filtered 
                if self._get_release_year(g) <= max_release_year
            ]
        
        if min_release_year is not None:
            filtered = [
                g for g in filtered 
                if self._get_release_year(g) >= min_release_year
            ]
        
        # 关键词搜索
        if search_keyword:
            keyword_lower = search_keyword.lower()
            filtered = [
                g for g in filtered 
                if keyword_lower in g.get('title', '').lower()
            ]
        
        # 限制返回数量
        return filtered[:limit]
    
    def get_library_summary(self, games: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        生成游戏库摘要统计
        
        Returns:
            包含总数、类型分布、年份分布等统计信息
        """
        if not games:
            return {
                "total_games": 0,
                "genres_distribution": {},
                "year_distribution": {},
                "avg_rating": 0
            }
        
        # 类型分布
        genres_count = {}
        for game in games:
            for genre in game.get('genres', []):
                genres_count[genre] = genres_count.get(genre, 0) + 1
        
        # 年份分布
        year_count = {}
        for game in games:
            year = self._get_release_year(game)
            if year:
                year_count[str(year)] = year_count.get(str(year), 0) + 1
        
        # 平均评分
        ratings = [g.get('rating', 0) for g in games if g.get('rating')]
        avg_rating = sum(ratings) / len(ratings) if ratings else 0
        
        return {
            "total_games": len(games),
            "genres_distribution": dict(sorted(genres_count.items(), key=lambda x: x[1], reverse=True)[:10]),
            "year_distribution": dict(sorted(year_count.items())),
            "avg_rating": round(avg_rating, 2)
        }
    
    def format_for_llm_prompt(self, games: List[Dict[str, Any]], query: str) -> str:
        """
        将游戏数据格式化为适合 LLM Prompt 的文本
        
        Args:
            games: 游戏列表
            query: 用户查询
            
        Returns:
            格式化的文本，可直接用于 LLM Prompt
        """
        if not games:
            return "游戏库为空"
        
        lines = [f"用户查询: {query}\n", f"游戏库中共有 {len(games)} 款游戏:\n"]
        
        for i, game in enumerate(games[:20], 1):  # 最多展示 20 款
            title = game.get('title', 'Unknown')
            genres = ', '.join(game.get('genres', []))
            rating = game.get('rating', 'N/A')
            year = self._get_release_year(game)
            
            lines.append(f"{i}. **{title}**")
            if genres:
                lines.append(f"   - 类型: {genres}")
            if rating:
                lines.append(f"   - 评分: {rating}/10")
            if year:
                lines.append(f"   - 发行年份: {year}")
            lines.append("")
        
        if len(games) > 20:
            lines.append(f"... 还有 {len(games) - 20} 款游戏未显示")
        
        return '\n'.join(lines)
    
    def _get_release_year(self, game: Dict[str, Any]) -> Optional[int]:
        """从游戏数据中提取发行年份"""
        release_date = game.get('release_date')
        if not release_date:
            return None

        try:
            if isinstance(release_date, str):
                # 尝试解析日期字符串
                date_obj = datetime.fromisoformat(release_date.replace('Z', '+00:00'))
                return date_obj.year
            elif isinstance(release_date, (int, float)):
                return int(release_date)
        except:
            pass

        return None

    @staticmethod
    def is_likely_nongame(game: Dict[str, Any]) -> bool:
        """
        疑似非游戏（OST/DLC/资料片/攻略等）宽松初筛。

        信号：
        1. Steam 元数据 type 非 game（music/dlc/demo 等）——最可靠，但仅 enrich 后才有；
        2. 标题含 OST/Soundtrack/Walkthrough/Season Pass 等关键词——兜底，覆盖历史数据。

        仅作提示用，不删除条目；最终判定交给 Agent。
        """
        # 信号1：enrich 后的 Steam type
        meta_type = game.get("steam_type") or game.get("type")
        if meta_type and meta_type != "game":
            return True
        # 信号2：标题关键词
        title = game.get("title", "") or ""
        if _NONGAME_TITLE_RE.search(title):
            return True
        return False

    def group_cross_platform(
        self, libs: Dict[str, List[Dict[str, Any]]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        跨平台"疑似同款"宽松初筛（不做最终判定，判定权交给 AI Agent）

        程序只负责把可能相同的游戏聚成候选组，并标注置信度和各平台原始标题，
        供 Agent 做语义复判。不合并、不删除任何条目。

        Args:
            libs: {平台名: 游戏列表}，如 {"epic": [...], "steam": [...], "gog": [...]}

        Returns:
            {
              "exact": [ {key, platforms, titles:{plat:title}}, ... ],  # 归一化标题完全相同
              "loose": [ {key, platforms, titles:{plat:title}}, ... ],  # 仅去版本后缀后相同（疑似）
            }
            仅包含涉及 >1 个平台的候选组。
        """
        from ..metadata.steam_client import SteamClient
        norm = SteamClient._normalize
        clean = SteamClient._clean_title

        # 严格分组：归一化标题 -> {platform: title}
        strict: Dict[str, Dict[str, str]] = {}
        # 宽松分组：去版本后缀再归一化 -> {platform: title}
        loose: Dict[str, Dict[str, str]] = {}

        for platform, games in libs.items():
            for g in games:
                title = g.get("title", "")
                if not title:
                    continue
                sk = norm(title)
                if sk:
                    strict.setdefault(sk, {}).setdefault(platform, title)
                lk = norm(clean(title))
                if lk:
                    loose.setdefault(lk, {}).setdefault(platform, title)

        # 严格组中跨平台的（>1 平台）= exact 候选
        exact_groups = []
        exact_keys = set()
        for k, plat_titles in strict.items():
            if len(plat_titles) > 1:
                exact_groups.append({
                    "key": k,
                    "platforms": sorted(plat_titles.keys()),
                    "titles": plat_titles,
                })
                exact_keys.add(k)

        # exact 组的 (平台,标题) 签名集合，用于过滤已被 exact 覆盖的 loose 重复
        # 例：'Metro 2033 Redux' 两平台标题相同 → 已是 exact；但其 loose key
        # 'metro2033'（clean 去掉 Redux）不同，若不按成员覆盖过滤会重复进 loose。
        exact_sigs = [
            frozenset((p, t) for p, t in grp["titles"].items())
            for grp in exact_groups
        ]

        # 宽松组中跨平台、且未被 exact 完全覆盖的 = loose 候选（疑似，需 Agent 判断）
        loose_groups = []
        for k, plat_titles in loose.items():
            if len(plat_titles) <= 1:
                continue
            if k in exact_keys:
                continue
            sig = frozenset((p, t) for p, t in plat_titles.items())
            # 该疑似组的全部 (平台,标题) 已被某个 exact 组覆盖 → 跳过，避免重复提示
            if any(sig <= esig for esig in exact_sigs):
                continue
            loose_groups.append({
                "key": k,
                "platforms": sorted(plat_titles.keys()),
                "titles": plat_titles,
            })

        return {"exact": exact_groups, "loose": loose_groups}
