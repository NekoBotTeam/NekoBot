"""插件基类和装饰器"""

import inspect
from typing import Dict, Any, Callable, List, Optional
from functools import wraps
from loguru import logger
from abc import ABC, abstractmethod
from dataclasses import dataclass


__all__ = [
    "BasePlugin",
    "register",
    "unregister",
    "reload_plugin",
    "enable_plugin",
    "disable_plugin",
    "export_commands",
    "on_message",
    "on_private_message",
    "on_group_message",
    "PluginDecorator",
    "create_plugin_decorator",
    "CommandInfo",
]


@dataclass
class CommandInfo:
    """命令信息数据类"""
    name: str
    description: str
    aliases: List[str]
    func: Callable


class BasePlugin(ABC):
    """插件基类（支持自动注册）

    插件可以通过类属性定义元数据，使用 __init_subclass__ 自动注册。

    用法:
        class MyPlugin(BasePlugin):
            _plugin_name = "my_plugin"
            _plugin_author = "Your Name"
            _plugin_version = "1.0.0"
            _plugin_description = "My awesome plugin"

            async def on_load(self):
                pass

            async def on_unload(self):
                pass
    """

    # 类属性：插件元数据（子类可覆盖）
    _plugin_name: Optional[str] = None
    _plugin_author: Optional[str] = None
    _plugin_version: Optional[str] = None
    _plugin_description: Optional[str] = None
    _plugin_desc: Optional[str] = None  # _plugin_description 的别名
    _plugin_repo: Optional[str] = None
    _plugin_display_name: Optional[str] = None

    def __init_subclass__(cls, **kwargs):
        """子类化时自动注册插件元数据"""
        super().__init_subclass__(**kwargs)

        # 延迟导入以避免循环依赖
        from .metadata import register_plugin_metadata, PluginMetadata, _plugin_map

        module_path = cls.__module__

        # 只在首次注册时创建元数据
        if module_path not in _plugin_map:
            # 处理 desc 和 description 兼容性
            desc = getattr(cls, "_plugin_desc", None)
            description = getattr(cls, "_plugin_description", None)
            if desc is None and description is not None:
                desc = description
            elif description is None and desc is not None:
                description = desc

            metadata = PluginMetadata(
                name=getattr(cls, "_plugin_name", cls.__name__),
                author=getattr(cls, "_plugin_author", "Unknown"),
                version=getattr(cls, "_plugin_version", "1.0.0"),
                desc=desc,
                description=description,
                repo=getattr(cls, "_plugin_repo", None),
                display_name=getattr(cls, "_plugin_display_name", None),
                module_path=module_path,
                star_cls_type=cls,
            )

            register_plugin_metadata(metadata)
            logger.debug(f"自动注册插件: {metadata.name} ({module_path})")

    def __init__(self):
        self.name = self.__class__.__name__
        self.version = getattr(self.__class__, "_plugin_version", "1.0.0")
        self.description = getattr(self.__class__, "_plugin_description", "")
        self.author = getattr(self.__class__, "_plugin_author", "")
        self.enabled = False
        self.commands: Dict[str, Callable] = {}
        self.message_handlers: List[Callable] = []
        # 平台服务器引用，用于发送消息
        self.platform_server = None
        # 插件配置 schema（从 _conf_schema.json 加载）
        self.conf_schema: Optional[Dict[str, Any]] = None

    @abstractmethod
    async def on_load(self):
        """插件加载时调用"""
        pass

    @abstractmethod
    async def on_unload(self):
        """插件卸载时调用"""
        pass

    async def on_enable(self):
        """插件启用时调用"""
        pass

    async def on_disable(self):
        """插件禁用时调用"""
        pass

    async def on_message(self, message):
        """收到消息时调用"""
        pass

    def set_platform_server(self, platform_server):
        """设置平台服务器引用"""
        self.platform_server = platform_server

    async def send_private_message(self, user_id: int, message: str, platform_id: str = "onebot") -> bool:
        """发送私聊消息"""
        if not self.platform_server:
            logger.warning("平台服务器未设置，无法发送消息")
            return False

        result = await self.platform_server.send_message(
            platform_id=platform_id,
            message_type="private",
            target_id=str(user_id),
            message=message
        )
        return result.get("status") == "success"

    async def send_group_message(
        self, group_id: int, user_id: int, message: str, platform_id: str = "onebot"
    ) -> bool:
        """发送群消息"""
        if not self.platform_server:
            logger.warning("平台服务器未设置，无法发送消息")
            return False

        result = await self.platform_server.send_message(
            platform_id=platform_id,
            message_type="group",
            target_id=str(group_id),
            message=message
        )
        return result.get("status") == "success"


# 装饰器实现
def register(command: str, description: str = "", aliases: List[str] = None):
    """注册命令装饰器

    Args:
        command: 命令名称
        description: 命令描述
        aliases: 命令别名列表
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            return await func(self, *args, **kwargs)

        # 使用数据类存储命令信息
        command_info = CommandInfo(
            name=command,
            description=description,
            aliases=aliases or [],
            func=func
        )
        wrapper._nekobot_command = command_info

        return wrapper

    return decorator


def unregister(func):
    """注销命令装饰器"""

    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        return await func(self, *args, **kwargs)

    wrapper._nekobot_unregister = True
    return wrapper


def reload_plugin(func):
    """重载插件装饰器"""

    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        return await func(self, *args, **kwargs)

    wrapper._nekobot_reload = True
    return wrapper


def enable_plugin(func):
    """启用插件装饰器"""

    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        return await func(self, *args, **kwargs)

    wrapper._nekobot_enable = True
    return wrapper


def disable_plugin(func):
    """禁用插件装饰器"""

    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        return await func(self, *args, **kwargs)

    wrapper._nekobot_disable = True
    return wrapper


def export_commands(func):
    """导出命令装饰器"""

    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        return await func(self, *args, **kwargs)

    wrapper._nekobot_export = True
    return wrapper


def on_message(func):
    """消息处理器装饰器"""

    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        return await func(self, *args, **kwargs)

    wrapper._nekobot_on_message = True
    return wrapper


def on_private_message(func):
    """私聊消息处理器装饰器"""

    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        return await func(self, *args, **kwargs)

    wrapper._nekobot_on_private_message = True
    return wrapper


def on_group_message(func):
    """群消息处理器装饰器"""

    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        return await func(self, *args, **kwargs)

    wrapper._nekobot_on_group_message = True
    return wrapper


class PluginDecorator:
    """插件装饰器管理器"""

    def __init__(self, plugin_instance: BasePlugin):
        self.plugin = plugin_instance
        self._process_decorators()

    def _process_decorators(self):
        """处理插件中的装饰器"""
        # 遍历插件类的所有方法
        for name, method in inspect.getmembers(self.plugin, predicate=inspect.ismethod):
            self._process_method_decorators(method)

    def _process_method_decorators(self, method):
        """处理方法的装饰器"""
        # 处理命令注册
        if hasattr(method, "_nekobot_command"):
            cmd_info = method._nekobot_command
            self.plugin.commands[cmd_info.name] = method
            logger.info(f"注册命令: {cmd_info.name}")

            # 注册到命令管理系统
            try:
                from ..core.command_management import register_command

                register_command(
                    handler_full_name=f"{self.plugin.name}.{method.__name__}",
                    handler_name=cmd_info.name,
                    plugin_name=self.plugin.name,
                    module_path=self.plugin.__class__.__module__,
                    description=cmd_info.description,
                    aliases=cmd_info.aliases,
                    permission="everyone",
                )
                logger.info(f"已将命令 {cmd_info.name} 注册到命令管理系统")
            except ImportError:
                logger.warning("命令管理系统未导入，跳过命令注册")

        # 处理消息处理器
        if hasattr(method, "_nekobot_on_message"):
            self.plugin.message_handlers.append(method)
            logger.info(f"注册消息处理器: {method.__name__}")

        # 处理私聊消息处理器
        if hasattr(method, "_nekobot_on_private_message"):
            self.plugin.message_handlers.append(method)
            logger.info(f"注册私聊消息处理器: {method.__name__}")

        # 处理群消息处理器
        if hasattr(method, "_nekobot_on_group_message"):
            self.plugin.message_handlers.append(method)
            logger.info(f"注册群消息处理器: {method.__name__}")


def create_plugin_decorator(plugin_instance: BasePlugin) -> PluginDecorator:
    """创建插件装饰器管理器"""
    return PluginDecorator(plugin_instance)
