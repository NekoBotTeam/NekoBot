"""平台适配器系统"""

from .base import BasePlatform
from .metadata import PlatformMetadata
from .register import register_platform_adapter, get_platform_adapter, get_all_platforms
from .manager import PlatformManager

from .sources import aiocqhttp
from .sources import discord
from .sources import telegram

__all__ = [
    "BasePlatform",
    "PlatformMetadata",
    "register_platform_adapter",
    "get_platform_adapter",
    "get_all_platforms",
    "PlatformManager",
]
