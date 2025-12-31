"""平台适配器源码模块"""

# 导入所有平台适配器以自动注册
# 使用 try-except 处理可选依赖缺失的情况
try:
    from . import aiocqhttp
except ImportError:
    pass

try:
    from . import discord
except ImportError:
    pass

try:
    from . import telegram
except ImportError:
    pass

try:
    from . import lark
except ImportError:
    pass

try:
    from . import kook
except ImportError:
    pass

try:
    from . import qqchannel
except ImportError:
    pass

try:
    from . import slack
except ImportError:
    pass

try:
    from . import wecom
except ImportError:
    pass

__all__ = []
