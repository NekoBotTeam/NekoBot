"""事件处理器注册表和权限系统

提供统一的事件处理器管理和权限控制，参考 AstrBot 框架实现
"""

import asyncio
import inspect
from typing import (
    Callable, Dict, List, Optional, Any, Set
)
from enum import Enum
from dataclasses import dataclass, field
from loguru import logger


# ============== 权限系统 ==============

class PermissionType(str, Enum):
    """权限类型"""
    EVERYONE = "everyone"      # 所有人
    MEMBER = "member"          # 普通成员
    ADMIN = "admin"            # 管理员
    SUPER_ADMIN = "super_admin" # 超级管理员


@dataclass
class PermissionContext:
    """权限上下文"""
    user_id: str
    group_id: Optional[str] = None
    roles: Set[str] = field(default_factory=set)
    permissions: Set[str] = field(default_factory=set)

    def has_role(self, role: str) -> bool:
        """检查是否有角色"""
        return role in self.roles

    def has_permission(self, permission: str) -> bool:
        """检查是否有权限"""
        return permission in self.permissions


class PermissionChecker:
    """权限检查器"""

    def __init__(self):
        # 默认权限配置
        self._admin_users: Set[str] = set()
        self._admin_groups: Set[str] = set()

    def add_admin_user(self, user_id: str) -> None:
        """添加管理员用户"""
        self._admin_users.add(user_id)
        logger.info(f"添加管理员用户: {user_id}")

    def remove_admin_user(self, user_id: str) -> None:
        """移除管理员用户"""
        self._admin_users.discard(user_id)
        logger.info(f"移除管理员用户: {user_id}")

    def add_admin_group(self, group_id: str) -> None:
        """添加管理员群组"""
        self._admin_groups.add(group_id)
        logger.info(f"添加管理员群组: {group_id}")

    def remove_admin_group(self, group_id: str) -> None:
        """移除管理员群组"""
        self._admin_groups.discard(group_id)
        logger.info(f"移除管理员群组: {group_id}")

    def check_permission(
        self,
        required_permission: PermissionType,
        context: PermissionContext
    ) -> bool:
        """检查权限

        Args:
            required_permission: 所需权限
            context: 权限上下文

        Returns:
            是否有权限
        """
        # SUPER_ADMIN 无所不能
        if "super_admin" in context.roles:
            return True

        # ADMIN 权限检查
        if required_permission in (PermissionType.ADMIN, PermissionType.SUPER_ADMIN):
            return (
                context.user_id in self._admin_users or
                (context.group_id and context.group_id in self._admin_groups)
            )

        # EVERYONE 权限，所有请求都通过
        if required_permission == PermissionType.EVERYONE:
            return True

        # 其他权限类型（如 MEMBER），默认拒绝
        return False


# 全局权限检查器
_global_permission_checker: Optional[PermissionChecker] = None


def get_permission_checker() -> PermissionChecker:
    """获取全局权限检查器"""
    global _global_permission_checker
    if _global_permission_checker is None:
        _global_permission_checker = PermissionChecker()
    return _global_permission_checker


# ============== 事件处理器 ==============

class EventType(str, Enum):
    """事件类型"""
    # 系统事件
    ON_STARTUP = "on_startup"
    ON_SHUTDOWN = "on_shutdown"
    ON_PLATFORM_READY = "on_platform_ready"

    # 消息事件
    ON_MESSAGE = "on_message"
    ON_PRIVATE_MESSAGE = "on_private_message"
    ON_GROUP_MESSAGE = "on_group_message"

    # 命令事件
    ON_COMMAND = "on_command"

    # 插件事件
    ON_PLUGIN_LOAD = "on_plugin_load"
    ON_PLUGIN_UNLOAD = "on_plugin_unLOAD"
    ON_PLUGIN_ENABLE = "on_plugin_enable"
    ON_PLUGIN_DISABLE = "on_plugin_disable"


@dataclass
class EventHandler:
    """事件处理器"""
    handler: Callable
    handler_name: str
    handler_full_name: str  # 唯一标识符
    module_path: str        # 所属模块
    priority: int = 0       # 优先级（数字越大越优先）
    permission: PermissionType = PermissionType.EVERYONE
    once: bool = False       # 是否只触发一次
    event_filters: List[Any] = field(default_factory=list)  # 事件过滤器
    enabled: bool = True    # 是否启用

    # 统计信息
    call_count: int = 0
    last_called: Optional[float] = None
    total_duration_ms: float = 0


# ============== 事件处理器注册表 ==============

class EventHandlerRegistry:
    """事件处理器注册表

    管理所有事件处理器的注册、注销和分发
    """

    def __init__(self):
        # 按事件类型分组的处理器
        self._handlers_by_event: Dict[str, List[EventHandler]] = {}

        # 按模块路径分组的处理器
        self._handlers_by_module: Dict[str, List[EventHandler]] = {}

        # 所有处理器
        self._all_handlers: List[EventHandler] = []

        # 命令处理器映射 (command_name -> handler)
        self._command_handlers: Dict[str, EventHandler] = {}

    def register(self, handler: EventHandler) -> None:
        """注册事件处理器

        Args:
            handler: 事件处理器
        """
        # 添加到全局列表
        self._all_handlers.append(handler)

        # 按事件类型分组
        event_type = self._get_event_type_from_handler(handler)
        if event_type not in self._handlers_by_event:
            self._handlers_by_event[event_type] = []

        self._handlers_by_event[event_type].append(handler)
        # 按优先级排序
        self._handlers_by_event[event_type].sort(key=lambda h: h.priority, reverse=True)

        # 按模块分组
        if handler.module_path not in self._handlers_by_module:
            self._handlers_by_module[handler.module_path] = []

        self._handlers_by_module[handler.module_path].append(handler)

        # 如果是命令处理器，添加到命令映射
        if handler.handler_name.startswith("command_"):
            command_name = handler.handler_name.replace("command_", "")
            self._command_handlers[command_name] = handler

        logger.debug(f"注册事件处理器: {handler.handler_full_name} ({event_type})")

    def unregister(self, handler_full_name: str) -> bool:
        """注销事件处理器

        Args:
            handler_full_name: 处理器全名

        Returns:
            是否成功注销
        """
        # 从全局列表中移除
        self._all_handlers = [
            h for h in self._all_handlers
            if h.handler_full_name != handler_full_name
        ]

        # 从事件类型分组中移除
        for event_type, handlers in self._handlers_by_event.items():
            self._handlers_by_event[event_type] = [
                h for h in handlers
                if h.handler_full_name != handler_full_name
            ]

        # 从模块分组中移除
        for module_path, handlers in self._handlers_by_module.items():
            self._handlers_by_module[module_path] = [
                h for h in handlers
                if h.handler_full_name != handler_full_name
            ]

        # 从命令映射中移除
        for command_name, handler in list(self._command_handlers.items()):
            if handler.handler_full_name == handler_full_name:
                del self._command_handlers[command_name]

        logger.debug(f"注销事件处理器: {handler_full_name}")
        return True

    def get_handlers_by_event(self, event_type: str) -> List[EventHandler]:
        """获取指定事件类型的所有处理器

        Args:
            event_type: 事件类型

        Returns:
            处理器列表（已按优先级排序）
        """
        return self._handlers_by_event.get(event_type, []).copy()

    def get_handlers_by_module(self, module_path: str) -> List[EventHandler]:
        """获取指定模块的所有处理器

        Args:
            module_path: 模块路径

        Returns:
            处理器列表
        """
        return self._handlers_by_module.get(module_path, []).copy()

    def get_command_handler(self, command_name: str) -> Optional[EventHandler]:
        """获取命令处理器

        Args:
            command_name: 命令名称

        Returns:
            命令处理器，如果不存在则返回 None
        """
        return self._command_handlers.get(command_name)

    def get_all_handlers(self) -> List[EventHandler]:
        """获取所有处理器

        Returns:
            所有处理器列表
        """
        return self._all_handlers.copy()

    def clear(self) -> None:
        """清空所有处理器"""
        self._handlers_by_event.clear()
        self._handlers_by_module.clear()
        self._all_handlers.clear()
        self._command_handlers.clear()
        logger.debug("已清空所有事件处理器")

    def _get_event_type_from_handler(self, handler: EventHandler) -> str:
        """从处理器名称推断事件类型

        Args:
            handler: 事件处理器

        Returns:
            事件类型
        """
        name = handler.handler_name

        if name.startswith("on_"):
            event_type = name
        elif name.startswith("command_"):
            event_type = EventType.ON_COMMAND.value
        else:
            event_type = EventType.ON_MESSAGE.value

        return event_type


# 全局注册表
_global_registry: Optional[EventHandlerRegistry] = None


def get_event_registry() -> EventHandlerRegistry:
    """获取全局事件处理器注册表"""
    global _global_registry
    if _global_registry is None:
        _global_registry = EventHandlerRegistry()
    return _global_registry


# ============== 事件装饰器 ==============

class EventDecorator:
    """事件装饰器基类"""

    def __init__(self, registry: EventHandlerRegistry):
        self._registry = registry

    def _create_handler(
        self,
        func: Callable,
        event_type: str,
        priority: int = 0,
        permission: PermissionType = PermissionType.EVERYONE,
        once: bool = False
    ) -> EventHandler:
        """创建事件处理器

        Args:
            func: 处理函数
            event_type: 事件类型
            priority: 优先级
            permission: 权限要求
            once: 是否只触发一次

        Returns:
            事件处理器
        """
        handler_name = func.__name__
        module_path = func.__module__

        return EventHandler(
            handler=func,
            handler_name=handler_name,
            handler_full_name=f"{module_path}.{handler_name}",
            module_path=module_path,
            priority=priority,
            permission=permission,
            once=once,
        )

    def register(self, handler: EventHandler) -> None:
        """注册处理器到注册表"""
        self._registry.register(handler)


def on_event(
    event_type: str = EventType.ON_MESSAGE,
    priority: int = 0,
    permission: PermissionType = PermissionType.EVERYONE,
    once: bool = False
):
    """事件监听装饰器

    Args:
        event_type: 事件类型
        priority: 优先级（数字越大越优先）
        permission: 所需权限
        once: 是否只触发一次

    用法:
        @on_event(EventType.ON_MESSAGE, priority=10)
        async def handle_message(event):
            pass
    """
    registry = get_event_registry()
    decorator = EventDecorator(registry)

    def wrapper(func):
        handler = decorator._create_handler(
            func, event_type, priority, permission, once
        )
        decorator.register(handler)

        # 保留原始函数
        func._event_handler = handler
        return func

    return wrapper


def on_command(
    command: str,
    priority: int = 0,
    permission: PermissionType = PermissionType.MEMBER,
    description: str = ""
):
    """命令监听装饰器

    Args:
        command: 命令名称
        priority: 优先级
        permission: 所需权限
        description: 命令描述

    用法:
        @on_command("help", description="显示帮助")
        async def command_help(context):
            pass
    """
    registry = get_event_registry()
    decorator = EventDecorator(registry)

    def wrapper(func):
        handler_name = f"command_{command}"
        handler = decorator._create_handler(
            func,
            EventType.ON_COMMAND.value,
            priority,
            permission,
            once=False
        )
        handler.handler_name = handler_name
        handler.command_description = description

        decorator.register(handler)

        func._event_handler = handler
        return func

    return wrapper


# ============== 事件分发器 ==============

class EventDispatcher:
    """事件分发器

    使用注册表分发事件到对应的处理器
    """

    def __init__(self, registry: Optional[EventHandlerRegistry] = None):
        """初始化事件分发器

        Args:
            registry: 事件处理器注册表
        """
        self._registry = registry or get_event_registry()
        self._permission_checker = get_permission_checker()

    async def dispatch(
        self,
        event_type: str,
        event_data: Dict[str, Any],
        permission_context: Optional[PermissionContext] = None
    ) -> List[Any]:
        """分发事件

        Args:
            event_type: 事件类型
            event_data: 事件数据
            permission_context: 权限上下文

        Returns:
            处理结果列表
        """
        handlers = self._registry.get_handlers_by_event(event_type)

        if not handlers:
            logger.debug(f"没有找到事件处理器: {event_type}")
            return []

        results = []

        for handler in handlers:
            if not handler.enabled:
                continue

            # 权限检查
            if permission_context:
                if not self._permission_checker.check_permission(
                    handler.permission,
                    permission_context
                ):
                    logger.debug(f"权限不足，跳过处理器: {handler.handler_full_name}")
                    continue

            # 过滤器检查
            skip = False
            for event_filter in handler.event_filters:
                if not event_filter(event_data):
                    skip = True
                    break

            if skip:
                continue

            # 执行处理器
            try:
                start_time = asyncio.get_event_loop().time()

                if inspect.iscoroutinefunction(handler.handler):
                    result = await handler.handler(event_data)
                else:
                    result = handler.handler(event_data)

                duration = (asyncio.get_event_loop().time() - start_time) * 1000

                # 更新统计
                handler.call_count += 1
                handler.last_called = asyncio.get_event_loop().time()
                handler.total_duration_ms += duration

                results.append(result)

                logger.debug(f"事件处理器执行完成: {handler.handler_full_name}, 耗时: {duration:.2f}ms")

            except Exception as e:
                logger.error(f"事件处理器执行出错: {handler.handler_full_name}, 错误: {e}")
                import traceback
                logger.error(traceback.format_exc())

        return results

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息

        Returns:
            统计信息字典
        """
        all_handlers = self._registry.get_all_handlers()

        return {
            "total_handlers": len(all_handlers),
            "handlers_by_event": {
                event_type: len(handlers)
                for event_type, handlers in self._registry._handlers_by_event.items()
            },
            "total_calls": sum(h.call_count for h in all_handlers),
            "enabled_handlers": sum(1 for h in all_handlers if h.enabled),
        }


__all__ = [
    "PermissionType",
    "PermissionContext",
    "PermissionChecker",
    "get_permission_checker",
    "EventType",
    "EventHandler",
    "EventHandlerRegistry",
    "get_event_registry",
    "on_event",
    "on_command",
    "EventDispatcher",
]
