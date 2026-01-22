"""Pipeline 上下文单元测试

测试 P2-2: 依赖注入重构（类型安全 + DI 容器）
"""

import pytest
from typing import Optional, Dict, Any
from unittest.mock import Mock, AsyncMock
from dataclasses import dataclass

from packages.core.pipeline.context import (
    # 接口
    IConfigManager,
    IPlatformManager,
    IPluginManager,
    IConversationManager,
    ILLMManager,
    IEventQueue,
    # 类型安全的上下文
    TypedPipelineContext,
    PipelineContext,  # 别名
    # 依赖注入容器
    DependencyContainer,
    get_container,
    # 便捷函数
    create_pipeline_context
)


# ============== Mock 实现用于测试 ==============

class MockConfigManager(IConfigManager):
    """模拟配置管理器"""

    def __init__(self):
        self._data = {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    async def set(self, key: str, value: Any) -> None:
        self._data[key] = value


class MockPlatformManager(IPlatformManager):
    """模拟平台管理器"""

    def __init__(self):
        self._platforms = {}

    async def send_message(
        self,
        platform_id: str,
        message_type: str,
        target_id: str,
        message: str
    ) -> Dict[str, Any]:
        return {"status": "success", "platform_id": platform_id}

    def get_platform(self, platform_id: str) -> Optional[Any]:
        return self._platforms.get(platform_id)


class MockPluginManager(IPluginManager):
    """模拟插件管理器"""

    def __init__(self):
        self._plugins = {}

    async def enable_plugin(self, name: str) -> bool:
        self._plugins[name] = {"enabled": True}
        return True

    async def disable_plugin(self, name: str) -> bool:
        if name in self._plugins:
            self._plugins[name]["enabled"] = False
        return True

    def get_plugin(self, name: str) -> Optional[Any]:
        return self._plugins.get(name)

    async def handle_message(self, message: Any) -> None:
        pass


class MockLLMManager(ILLMManager):
    """模拟 LLM 管理器"""

    async def text_chat(
        self,
        provider_id: str,
        prompt: str,
        **kwargs
    ) -> str:
        return f"Response to: {prompt}"


class MockConversationManager(IConversationManager):
    """模拟会话管理器"""

    async def get_or_create_conversation(
        self,
        session_id: str,
        user_id: str
    ) -> Any:
        return {"session_id": session_id, "user_id": user_id}

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str
    ) -> None:
        pass


class MockEventQueue(IEventQueue):
    """模拟事件队列"""

    async def put(self, event: Dict[str, Any]) -> None:
        pass

    async def get(self) -> Dict[str, Any]:
        return {"type": "test", "data": {}}


# ============== 测试接口 ==============

class TestInterfaces:
    """测试接口定义"""

    def test_i_config_manager(self):
        """测试配置管理器接口"""
        manager = MockConfigManager()

        # 测试同步方法
        assert manager.get("key", "default") == "default"
        manager._data["key"] = "value"
        assert manager.get("key") == "value"

    def test_i_platform_manager(self):
        """测试平台管理器接口"""
        manager = MockPlatformManager()

        # 接口定义了方法签名
        assert hasattr(manager, 'send_message')
        assert hasattr(manager, 'get_platform')

    def test_i_plugin_manager(self):
        """测试插件管理器接口"""
        manager = MockPluginManager()

        assert hasattr(manager, 'enable_plugin')
        assert hasattr(manager, 'disable_plugin')
        assert hasattr(manager, 'get_plugin')
        assert hasattr(manager, 'handle_message')


# ============== 测试类型安全的上下文 ==============

class TestTypedPipelineContext:
    """测试类型安全的 Pipeline 上下文"""

    @pytest.fixture
    def mock_deps(self):
        """创建模拟依赖"""
        return {
            'config': MockConfigManager(),
            'platform_manager': MockPlatformManager(),
            'plugin_manager': MockPluginManager(),
            'llm_manager': MockLLMManager(),
            'conversation_manager': MockConversationManager(),
            'event_queue': MockEventQueue()
        }

    def test_creation(self, mock_deps):
        """测试创建上下文"""
        ctx = TypedPipelineContext(
            config=mock_deps['config'],
            platform_manager=mock_deps['platform_manager'],
            plugin_manager=mock_deps['plugin_manager']
        )

        assert ctx.config is not None
        assert ctx.platform_manager is not None
        assert ctx.plugin_manager is not None

    def test_optional_dependencies(self, mock_deps):
        """测试可选依赖"""
        ctx = TypedPipelineContext(
            config=mock_deps['config'],
            platform_manager=mock_deps['platform_manager'],
            plugin_manager=mock_deps['plugin_manager'],
            llm_manager=mock_deps['llm_manager'],
            conversation_manager=mock_deps['conversation_manager'],
            event_queue=mock_deps['event_queue']
        )

        assert ctx.llm_manager is not None
        assert ctx.conversation_manager is not None
        assert ctx.event_queue is not None

    def test_extra_data(self, mock_deps):
        """测试额外数据"""
        ctx = TypedPipelineContext(
            config=mock_deps['config'],
            platform_manager=mock_deps['platform_manager'],
            plugin_manager=mock_deps['plugin_manager'],
            extra={"custom_key": "custom_value"}
        )

        assert ctx.get("custom_key") == "custom_value"

    def test_set_and_get_extra(self, mock_deps):
        """测试设置和获取额外数据"""
        ctx = TypedPipelineContext(
            config=mock_deps['config'],
            platform_manager=mock_deps['platform_manager'],
            plugin_manager=mock_deps['plugin_manager']
        )

        ctx.set("test_key", "test_value")

        assert ctx.get("test_key") == "test_value"

    def test_session_identifiers(self, mock_deps):
        """测试会话标识符"""
        ctx = TypedPipelineContext(
            config=mock_deps['config'],
            platform_manager=mock_deps['platform_manager'],
            plugin_manager=mock_deps['plugin_manager'],
            session_id="session_123",
            user_id="user_456",
            group_id="group_789",
            message_id="msg_abc"
        )

        assert ctx.session_id == "session_123"
        assert ctx.user_id == "user_456"
        assert ctx.group_id == "group_789"
        assert ctx.message_id == "msg_abc"

    def test_has_conversation(self, mock_deps):
        """测试检查会话管理器"""
        ctx_without = TypedPipelineContext(
            config=mock_deps['config'],
            platform_manager=mock_deps['platform_manager'],
            plugin_manager=mock_deps['plugin_manager']
        )

        assert ctx_without.has_conversation() is False

        ctx_with = TypedPipelineContext(
            config=mock_deps['config'],
            platform_manager=mock_deps['platform_manager'],
            plugin_manager=mock_deps['plugin_manager'],
            conversation_manager=mock_deps['conversation_manager']
        )

        assert ctx_with.has_conversation() is True

    def test_has_llm(self, mock_deps):
        """测试检查 LLM 管理器"""
        ctx_without = TypedPipelineContext(
            config=mock_deps['config'],
            platform_manager=mock_deps['platform_manager'],
            plugin_manager=mock_deps['plugin_manager']
        )

        assert ctx_without.has_llm() is False

        ctx_with = TypedPipelineContext(
            config=mock_deps['config'],
            platform_manager=mock_deps['platform_manager'],
            plugin_manager=mock_deps['plugin_manager'],
            llm_manager=mock_deps['llm_manager']
        )

        assert ctx_with.has_llm() is True

    def test_get_session_identifier(self, mock_deps):
        """测试获取会话标识符"""
        # 有 session_id
        ctx1 = TypedPipelineContext(
            config=mock_deps['config'],
            platform_manager=mock_deps['platform_manager'],
            plugin_manager=mock_deps['plugin_manager'],
            session_id="custom_session"
        )

        assert ctx1.get_session_identifier() == "custom_session"

        # 有 user_id 和 group_id
        ctx2 = TypedPipelineContext(
            config=mock_deps['config'],
            platform_manager=mock_deps['platform_manager'],
            plugin_manager=mock_deps['plugin_manager'],
            user_id="user123",
            group_id="group456"
        )

        assert ctx2.get_session_identifier() == "group456_user123"

        # 只有 user_id
        ctx3 = TypedPipelineContext(
            config=mock_deps['config'],
            platform_manager=mock_deps['platform_manager'],
            plugin_manager=mock_deps['plugin_manager'],
            user_id="user123"
        )

        assert ctx3.get_session_identifier() == "private_user123"

    def test_metadata(self, mock_deps):
        """测试元数据"""
        ctx = TypedPipelineContext(
            config=mock_deps['config'],
            platform_manager=mock_deps['platform_manager'],
            plugin_manager=mock_deps['plugin_manager'],
            metadata={"request_id": "abc123", "trace_id": "xyz789"}
        )

        assert ctx.metadata["request_id"] == "abc123"
        assert ctx.metadata["trace_id"] == "xyz789"

    def test_backward_compatibility_alias(self, mock_deps):
        """测试向后兼容别名"""
        ctx1 = TypedPipelineContext(
            config=mock_deps['config'],
            platform_manager=mock_deps['platform_manager'],
            plugin_manager=mock_deps['plugin_manager']
        )

        ctx2 = PipelineContext(
            config=mock_deps['config'],
            platform_manager=mock_deps['platform_manager'],
            plugin_manager=mock_deps['plugin_manager']
        )

        # 应该是同一个类
        assert type(ctx1) == type(ctx2)


# ============== 测试依赖注入容器 ==============

class TestDependencyContainer:
    """测试依赖注入容器"""

    @pytest.fixture
    def container(self):
        """创建容器实例"""
        return DependencyContainer()

    def test_register_singleton(self, container):
        """测试注册单例服务"""
        service = Mock()

        container.register_singleton("my_service", service)

        assert container.has("my_service") is True

    def test_register_transient(self, container):
        """测试注册瞬态服务"""
        call_count = 0

        def factory():
            nonlocal call_count
            call_count += 1
            return Mock()

        container.register_transient("my_service", factory)

        assert container.has("my_service") is True

    def test_register_factory(self, container):
        """测试注册工厂服务"""
        def factory():
            return Mock()

        container.register_factory("my_service", factory)

        assert container.has("my_service") is True

    @pytest.mark.asyncio
    async def test_get_singleton(self, container):
        """测试获取单例服务"""
        service = Mock()
        container.register_singleton("my_service", service)

        result = await container.get("my_service")

        assert result is service

    @pytest.mark.asyncio
    async def test_get_transient(self, container):
        """测试获取瞬态服务"""
        instances = []

        def factory():
            instance = Mock()
            instances.append(instance)
            return instance

        container.register_transient("my_service", factory)

        # 每次获取应该返回新实例
        result1 = await container.get("my_service")
        result2 = await container.get("my_service")

        assert result1 is not result2
        assert len(instances) == 2

    @pytest.mark.asyncio
    async def test_get_factory(self, container):
        """测试获取工厂服务"""
        def factory():
            return "factory_result"

        container.register_factory("my_service", factory)

        result = await container.get("my_service")

        assert result == "factory_result"

    @pytest.mark.asyncio
    async def test_get_nonexistent_service(self, container):
        """测试获取不存在的服务"""
        with pytest.raises(ValueError, match="服务不存在"):
            await container.get("nonexistent")

    def test_has_service(self, container):
        """测试检查服务是否存在"""
        service = Mock()
        container.register_singleton("existing", service)

        assert container.has("existing") is True
        assert container.has("nonexistent") is False

    def test_get_sync(self, container):
        """测试同步获取服务"""
        service = Mock()
        container.register_singleton("my_service", service)

        result = container.get_sync("my_service")

        assert result is service

    def test_get_sync_nonexistent(self, container):
        """测试同步获取不存在的服务"""
        with pytest.raises(ValueError, match="服务不存在（同步）"):
            container.get_sync("nonexistent")


# ============== 测试全局容器 ==============

class TestGlobalContainer:
    """测试全局依赖容器"""

    def test_get_container_singleton(self):
        """测试获取单例容器"""
        container1 = get_container()
        container2 = get_container()

        assert container1 is container2

    def test_global_container_persistence(self):
        """测试全局容器持久化"""
        container = get_container()
        service = Mock()

        container.register_singleton("global_service", service)

        # 从另一个获取的容器应该能访问
        container2 = get_container()
        result = container2.get_sync("global_service")

        assert result is service


# ============== 测试便捷函数 ==============

class TestConvenienceFunctions:
    """测试便捷函数"""

    @pytest.mark.asyncio
    async def test_create_pipeline_context(self):
        """测试创建 Pipeline 上下文"""
        config = MockConfigManager()
        platform = MockPlatformManager()
        plugin = MockPluginManager()

        ctx = await create_pipeline_context(
            config=config,
            platform_manager=platform,
            plugin_manager=plugin
        )

        assert isinstance(ctx, TypedPipelineContext)
        assert ctx.config is config
        assert ctx.platform_manager is platform
        assert ctx.plugin_manager is plugin

    @pytest.mark.asyncio
    async def test_create_pipeline_context_with_optional_deps(self):
        """测试创建带可选依赖的上下文"""
        config = MockConfigManager()
        platform = MockPlatformManager()
        plugin = MockPluginManager()
        llm = MockLLMManager()

        ctx = await create_pipeline_context(
            config=config,
            platform_manager=platform,
            plugin_manager=plugin,
            llm_manager=llm
        )

        assert ctx.llm_manager is llm

    @pytest.mark.asyncio
    async def test_create_pipeline_context_with_extra(self):
        """测试创建带额外参数的上下文"""
        config = MockConfigManager()
        platform = MockPlatformManager()
        plugin = MockPluginManager()

        ctx = await create_pipeline_context(
            config=config,
            platform_manager=platform,
            plugin_manager=plugin,
            custom_data="value",
            another_key=123
        )

        assert ctx.get("custom_data") == "value"
        assert ctx.get("another_key") == 123


# ============== 集成测试 ==============

class TestIntegration:
    """集成测试"""

    @pytest.mark.asyncio
    async def test_full_di_workflow(self):
        """测试完整的依赖注入工作流"""
        # 1. 创建容器
        container = get_container()

        # 2. 注册服务
        config = MockConfigManager()
        platform = MockPlatformManager()
        plugin = MockPluginManager()

        container.register_singleton("config", config)
        container.register_singleton("platform_manager", platform)
        container.register_singleton("plugin_manager", plugin)

        # 3. 从容器创建上下文
        ctx = TypedPipelineContext(
            config=container.get_sync("config"),
            platform_manager=container.get_sync("platform_manager"),
            plugin_manager=container.get_sync("plugin_manager")
        )

        # 4. 验证上下文
        assert ctx.config is config
        assert ctx.platform_manager is platform
        assert ctx.plugin_manager is plugin

    @pytest.mark.asyncio
    async def test_context_with_injected_services(self):
        """测试带注入服务的上下文"""
        container = get_container()

        # 注册异步工厂
        async def create_llm_manager():
            return MockLLMManager()

        container.register_factory("llm_manager", create_llm_manager)

        # 获取服务
        llm = await container.get("llm_manager")

        # 创建上下文
        ctx = TypedPipelineContext(
            config=MockConfigManager(),
            platform_manager=MockPlatformManager(),
            plugin_manager=MockPluginManager(),
            llm_manager=llm
        )

        assert ctx.has_llm() is True
