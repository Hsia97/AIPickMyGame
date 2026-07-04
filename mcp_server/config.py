"""
配置管理模块

负责加载和管理应用配置，支持默认值和用户自定义配置。
"""

from pathlib import Path
from typing import Dict, Any, Optional
import json
from pydantic import BaseModel, Field


class PlatformConfig(BaseModel):
    """平台配置"""
    enabled: bool = True
    auto_sync: bool = True
    sync_interval_hours: int = 24
    api_key: Optional[str] = None
    steam_id: Optional[str] = None



class MetadataConfig(BaseModel):
    """元数据配置"""
    provider: str = "rawg"
    api_key: Optional[str] = None
    cache_ttl_days: int = 30
    igdb_client_id: Optional[str] = None
    igdb_client_secret: Optional[str] = None
    steam_language: str = "schinese"
    steam_country: str = "CN"


class AppConfig(BaseModel):
    """应用主配置"""
    # 平台配置
    platforms: Dict[str, PlatformConfig] = Field(default_factory=lambda: {
        "epic": PlatformConfig(),
        "steam": PlatformConfig(enabled=False),
        "gog": PlatformConfig(enabled=False)
    })
    
    # 元数据配置
    metadata: MetadataConfig = Field(default_factory=MetadataConfig)
    
    # 存储路径
    library_path: str = "~/Games"
    token_storage_type: str = "system_keychain"
    
    class Config:
        extra = "allow"
    
    def __init__(self, **data):
        super().__init__(**data)
        self.config_path = self._get_config_path()
        self._load_or_create_config()
    
    def _get_config_path(self) -> Path:
        """获取配置文件路径"""
        # 优先使用项目本地配置目录
        local_config_dir = Path(__file__).parent.parent / "config"
        local_config_dir.mkdir(exist_ok=True)
        local_config_path = local_config_dir / "config.json"
        
        # 如果本地配置文件存在，使用它
        if local_config_path.exists():
            return local_config_path
        
        # 否则使用用户主目录（向后兼容）
        user_config_dir = Path.home() / ".aipickmygame"
        user_config_dir.mkdir(exist_ok=True)
        return user_config_dir / "config.json"
    
    def _load_or_create_config(self):
        """加载现有配置或创建默认配置"""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                self._update_from_dict(config_data)
            except Exception as e:
                print(f"⚠️ 配置文件读取失败: {e}，使用默认配置")
                self._save_default_config()
        else:
            self._save_default_config()
    
    def _save_default_config(self):
        """保存默认配置"""
        config_data = {
            "platforms": {
                name: platform.model_dump()
                for name, platform in self.platforms.items()
            },
            "metadata": self.metadata.model_dump(),
            "library_path": self.library_path,
            "token_storage_type": self.token_storage_type
        }
        
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)
        print(f"✅ 已创建默认配置文件: {self.config_path}")
    
    def _update_from_dict(self, data: Dict[str, Any]):
        """从字典更新配置"""
        if 'platforms' in data:
            for platform, config in data['platforms'].items():
                if platform in self.platforms:
                    self.platforms[platform] = PlatformConfig(**config)
        
        if 'metadata' in data:
            self.metadata = MetadataConfig(**data['metadata'])
        
        if 'library_path' in data:
            self.library_path = data['library_path']
        
        if 'token_storage_type' in data:
            self.token_storage_type = data['token_storage_type']
    
    def save(self):
        """保存当前配置到文件"""
        self._save_default_config()
    
    def get_library_path(self, platform: str) -> Path:
        """获取指定平台的游戏库文件路径"""
        base_path = Path(self.library_path).expanduser()
        base_path.mkdir(parents=True, exist_ok=True)
        return base_path / f"{platform}_library.json"

    @property
    def data_dir(self) -> str:
        """数据存储目录（用于存放 token 等文件）"""
        d = self.config_path.parent
        d.mkdir(parents=True, exist_ok=True)
        return str(d)
