"""Pipeline 上下文

提供 Pipeline 执行所需的上下文信息（类型安全版本）
"""

from typing import Any, Dict, Optional
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
import asyncio
from loguru import logger


# ============== 类型定义 ==============

class IConfigManager(ABC):
    """配置管理器接口"""

    @abstractmethod
    def get(self, key: str, default: Any = None) -> Any:
        pass

    @abstractmethod
    async def set(self, key: str, value: Any) -> None:
        pass


class IPlatformManager(ABC):
    """平台管理器接口"""

    @abstractmethod
    async def send_message(
        self,
        platform_id: str,
        message_type: str,
        target_id: str,
        message: str
    ) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_platform(self, platform_id: str) -> Optional[Any]:
        pass


class IPluginManager(ABC):
    """插件管理器接口"""

    @abstractmethod
    async def enable_plugin(self, name: str) -> bool:
        pass

    @abstractmethod
    async def disable_plugin(self, name: str) -> bool:
        pass

    @abstractmethod
    def get_plugin(self, name: str) -> Optional[Any]:
        pass

    @abstractmethod
    async def handle_message(self, message: Any) -> None:
        pass


class IConversationManager(ABC):
    """会话管理器接口"""

    @abstractmethod
    async def get_or_create_conversation(
        self,
        session_id: str,
        user_id: str
    ) -> Any:
        pass

    @abstractmethod
    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str
    ) -> None:
        pass


class ILLMManager(ABC):
    """LLM 管理器接口"""

    @abstractmethod
    async def text_chat(
        self,
        provider_id: str,
        prompt: str,
        **kwargs
    ) -> str:
        pass


class IEventQueue(ABC):
    """事件队列接口"""

    @abstractmethod
    async def put(self, event: Dict[str, Any]) -> None:
        pass

    @abstractmethod
    async def get(self) -> Dict[str, Any]:
        pass


# ============== 类型安全的 Pipeline Context ==============

@dataclass
class TypedPipelineContext:
    """类型安全的 Pipeline 上下文

    提供明确的类型定义，避免运行时类型错误
    """

    # 必需依赖
    config: IConfigManager
    """配置管理器"""

    platform_manager: IPlatformManager
    """平台管理器"""

    plugin_manager: IPluginManager
    """插件管理器"""

    # 可选依赖
    llm_manager: Optional[ILLMManager] = None
    """LLM 管理器"""

    conversation_manager: Optional[IConversationManager] = None
    """会话管理器"""

    event_queue: Optional[IEventQueue] = None
    """事件队列"""

    # 额外的上下文数据
    extra: Dict[str, Any] = field(default_factory=dict)

    # 请求/会话特定数据
    session_id: Optional[str] = None
    """当前会话 ID"""

    user_id: Optional[str] = None
    """当前用户 ID"""

    group_id: Optional[str] = None
    """当前群组 ID"""

    message_id: Optional[str] = None
    """当前消息 ID"""

    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)
    """元数据"""

    def get(self, key: str, default: Any = None) -> Any:
        """获取额外上下文数据"""
        return self.extra.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """设置额外上下文数据"""
        self.extra[key] = value

    def has_conversation(self) -> bool:
        """检查是否有会话管理器"""
        return self.conversation_manager is not None

    def has_llm(self) -> bool:
        """检查是否有 LLM 管理器"""
        return self.llm_manager is not None

    def get_session_identifier(self) -> str:
        """获取会话标识符"""
        if self.session_id:
            return self.session_id
        if self.user_id and self.group_id:
            return f"{self.group_id}_{self.user_id}"
        if self.user_id:
            return f"private_{self.user_id}"
        return "default"


# ============== 依赖注入容器 ==============

class DependencyContainer:
    """依赖注入容器

    管理应用中的所有依赖关系
    """

    def __init__(self):
        """初始化依赖容器"""
        self._services: Dict[str, Any] = {}
        self._singletons: Dict[str, Any] = {}
        self._factories: Dict[str, callable] = {}
        self._lock = asyncio.Lock()

    def register_singleton(self, name: str, instance: Any) -> None:
        """注册单例服务

        Args:
            name: 服务名称
            instance: 服务实例
        """
        self._singletons[name] = instance
        logger.debug(f"注册单例服务: {name}")

    def register_transient(self, name: str, factory: callable) -> None:
        """注册瞬态服务（每次获取时创建新实例）

        Args:
            name: 服务名称
            factory: 工厂函数
        """
        self._factories[name] = factory
        logger.debug(f"注册瞬态服务: {name}")

    def register_factory(self, name: str, factory: callable) -> None:
        """注册工厂服务

        Args:
            name: 服务名称
            factory: 工厂函数
        """
        self._factories[name] = factory
        logger.debug(f"注册工厂服务: {name}")

    async def get(self, name: str) -> Any:
        """获取服务

        Args:
            name: 服务名称

        Returns:
            服务实例
        """
        async with self._lock:
            # 优先返回单例
            if name in self._singletons:
                return self._singletons[name]

            # 其次尝试工厂
            if name in self._factories:
                factory = self._factories[name]
                if asyncio.iscoroutinefunction(factory):
                    return await factory()
                else:
                    return factory()

            # 最后查找已注册的服务
            if name in self._services:
                return self._services[name]

            raise ValueError(f"服务不存在: {name}")

    def has(self, name: str) -> bool:
        """检查服务是否存在

        Args:
            name: 服务名称

        Returns:
            是否存在
        """
        return (
            name in self._singletons or
            name in self._factories or
            name in self._services
        )

    def get_sync(self, name: str) -> Any:
        """同步获取服务（仅限已注册的服务）

        Args:
            name: 服务名称

        Returns:
            服务实例
        """
        if name in self._singletons:
            return self._singletons[name]

        if name in self._services:
            return self._services[name]

        raise ValueError(f"服务不存在（同步）: {name}")


# 全局依赖容器
_global_container: Optional[DependencyContainer] = None


def get_container() -> DependencyContainer:
    """获取全局依赖容器"""
    global _global_container
    if _global_container is None:
        _global_container = DependencyContainer()
    return _global_container


# ============== 便捷函数 ==============

async def create_pipeline_context(
    config: IConfigManager,
    platform_manager: IPlatformManager,
    plugin_manager: IPluginManager,
    llm_manager: Optional[ILLMManager] = None,
    conversation_manager: Optional[IConversationManager] = None,
    event_queue: Optional[IEventQueue] = None,
    **extra
) -> TypedPipelineContext:
    """创建 Pipeline 上下文（便捷函数）

    Args:
        config: 配置管理器
        platform_manager: 平台管理器
        plugin_manager: 插件管理器
        llm_manager: LLM 管理器（可选）
        conversation_manager: 会话管理器（可选）
        event_queue: 事件队列（可选）
        **extra: 额外参数

    Returns:
        Pipeline 上下文
    """
    return TypedPipelineContext(
        config=config,
        platform_manager=platform_manager,
        plugin_manager=plugin_manager,
        llm_manager=llm_manager,
        conversation_manager=conversation_manager,
        event_queue=event_queue,
        extra=extra,
    )


# ============== 向后兼容 ==============

# 为了向后兼容，保留原有的 PipelineContext 别名
PipelineContext = TypedPipelineContext
