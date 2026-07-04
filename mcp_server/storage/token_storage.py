"""
加密 Token 存储

使用系统密钥链安全存储认证令牌。
注意：此模块已迁移到 auth/token_manager.py，保留此处仅为兼容性。
"""

from ..auth.token_manager import TokenManager as EncryptedTokenStorage

# 向后兼容别名
__all__ = ['EncryptedTokenStorage']
