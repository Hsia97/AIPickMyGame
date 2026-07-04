"""
认证管理模块

提供 Epic Games、Steam 等平台的 OAuth 认证和 Token 管理功能。
"""

from .epic_auth import EpicAuthManager
from .token_manager import TokenManager

__all__ = ['EpicAuthManager', 'TokenManager']
