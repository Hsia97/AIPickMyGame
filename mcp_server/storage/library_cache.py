"""
游戏库缓存管理

管理本地游戏库 JSON 文件的读写和缓存。
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta


class LibraryCache:
    """游戏库缓存管理器"""
    
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def save(self, platform: str, games: List[Dict[str, Any]]):
        """
        保存游戏库到缓存
        
        Args:
            platform: 平台名称
            games: 游戏列表
        """
        cache_file = self._get_cache_file(platform)
        
        data = {
            'platform': platform,
            'cached_at': datetime.now().isoformat(),
            'game_count': len(games),
            'games': games
        }
        
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def load(self, platform: str) -> Optional[List[Dict[str, Any]]]:
        """
        从缓存加载游戏库
        
        Args:
            platform: 平台名称
            
        Returns:
            游戏列表，如果缓存不存在则返回 None
        """
        cache_file = self._get_cache_file(platform)
        
        if not cache_file.exists():
            return None
        
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            return data.get('games', [])
        
        except Exception as e:
            print(f"⚠️ 加载缓存失败: {e}")
            return None
    
    def is_fresh(self, platform: str, max_age_hours: int = 24) -> bool:
        """
        检查缓存是否新鲜
        
        Args:
            platform: 平台名称
            max_age_hours: 最大缓存时长（小时）
            
        Returns:
            True 如果缓存未过期
        """
        cache_file = self._get_cache_file(platform)
        
        if not cache_file.exists():
            return False
        
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            cached_at = datetime.fromisoformat(data.get('cached_at', ''))
            age = datetime.now() - cached_at
            
            return age < timedelta(hours=max_age_hours)
        
        except Exception:
            return False
    
    def clear(self, platform: Optional[str] = None):
        """
        清除缓存
        
        Args:
            platform: 指定平台，如果为 None 则清除所有
        """
        if platform:
            cache_file = self._get_cache_file(platform)
            if cache_file.exists():
                cache_file.unlink()
        else:
            for cache_file in self.cache_dir.glob('*_library.json'):
                cache_file.unlink()
    
    def _get_cache_file(self, platform: str) -> Path:
        """获取缓存文件路径"""
        return self.cache_dir / f"{platform}_library.json"
