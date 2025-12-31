"""平台适配器系统"""

from .base import BasePlatform
from .metadata import PlatformMetadata
from .register import register_platform_adapter, get_platform_adapter, get_all_platforms
from .manager import PlatformManager

# 导入平台适配器以触发注册（使用 try-except 处理可选依赖）
try:
    from .sources import aiocqhttp
except ImportError:
    pass

try:
    from .sources import discord
except ImportError:
    pass

try:
    from .sources import telegram
except ImportError:
    pass

__all__ = [
    "BasePlatform",
    "PlatformMetadata",
    "register_platform_adapter",
    "get_platform_adapter",
    "get_all_platforms",
    "PlatformManager",
]
