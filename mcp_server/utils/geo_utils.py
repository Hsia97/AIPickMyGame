"""
地理检测工具

判断当前运行环境是否在中国大陆，用于决定元数据获取策略。
"""

import asyncio
import httpx


async def is_mainland_china(timeout: float = 3.0) -> bool:
    """
    检测当前环境是否在中国大陆。

    策略：尝试直连 Google，不通则判定为大陆。

    Returns:
        True 表示大陆环境
    """
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get("https://www.google.com")
            return False
    except Exception:
        return True


def is_mainland_china_sync(timeout: float = 3.0) -> bool:
    """
    同步版本的地理检测。
    """
    try:
        client = httpx.Client(timeout=timeout)
        resp = client.get("https://www.google.com")
        client.close()
        return False
    except Exception:
        return True