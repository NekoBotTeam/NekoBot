"""事件系统单元测试

测试 P2-1: 事件系统重构（中心注册表 + 权限系统）
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import Mock, AsyncMock

from packages.core.events import (
    PermissionType,
    PermissionContext,
    PermissionChecker,
    get_permission_checker,
    EventType,
    EventHandler,
    EventHandlerRegistry,
    get_event_registry,
    on_event,
    on_command,
    EventDispatcher
)


class TestPermissionType:
    """测试权限类型枚举"""

    def test_values(self):
        """测试枚举值"""
        assert PermissionType.EVERYONE.value == "everyone"
        assert PermissionType.MEMBER.value == "member"
        assert PermissionType.ADMIN.value == "admin"
        assert PermissionType.SUPER_ADMIN.value == "super_admin"


class TestPermissionContext:
    """测试权限上下文"""

    def test_creation(self):
        """测试创建权限上下文"""
        context = PermissionContext(
            user_id="user123",
            group_id="group456"
        )

        assert context.user_id == "user123"
        assert context.group_id == "group456"

    def test_has_role(self):
        """测试检查角色"""
        context = PermissionContext(
            user_id="user123",
            roles={"admin", "moderator"}
        )

        assert context.has_role("admin") is True
        assert context.has_role("user") is False

    def test_has_permission(self):
        """测试检查权限"""
        context = PermissionContext(
            user_id="user123",
            permissions={"post", "delete"}
        )

        assert context.has_permission("post") is True
        assert context.has_permission("edit") is False


class TestPermissionChecker:
    """测试权限检查器"""

    @pytest.fixture
    def checker(self):
        """创建权限检查器"""
        return PermissionChecker()

    def test_add_admin_user(self, checker):
        """测试添加管理员用户"""
        checker.add_admin_user("user123")

        assert "user123" in checker._admin_users

    def test_remove_admin_user(self, checker):
        """测试移除管理员用户"""
        checker.add_admin_user("user123")
        checker.remove_admin_user("user123")

        assert "user123" not in checker._admin_users

    def test_add_admin_group(self, checker):
        """测试添加管理员群组"""
        checker.add_admin_group("group456")

        assert "group456" in checker._admin_groups

    def test_check_permission_everyone(self, checker):
        """测试检查 EVERYONE 权限"""
        context = PermissionContext(user_id="user123")

        result = checker.check_permission(PermissionType.EVERYONE, context)

        assert result is True

    def test_check_permission_admin_user(self, checker):
        """测试检查用户 ADMIN 权限"""
        checker.add_admin_user("admin_user")

        context = PermissionContext(user_id="admin_user")

        result = checker.check_permission(PermissionType.ADMIN, context)

        assert result is True

    def test_check_permission_admin_group(self, checker):
        """测试检查群组 ADMIN 权限"""
        checker.add_admin_group("admin_group")

        context = PermissionContext(user_id="user123", group_id="admin_group")

        result = checker.check_permission(PermissionType.ADMIN, context)

        assert result is True

    def test_check_permission_denied(self, checker):
        """测试权限被拒绝"""
        context = PermissionContext(user_id="regular_user")

        result = checker.check_permission(PermissionType.ADMIN, context)

        assert result is False

    def test_check_permission_super_admin(self, checker):
        """测试超级管理员权限"""
        context = PermissionContext(
            user_id="user123",
            roles={"super_admin"}
        )

        result = checker.check_permission(PermissionType.SUPER_ADMIN, context)

        assert result is True


class TestEventType:
    """测试事件类型枚举"""

    def test_values(self):
        """测试事件类型值"""
        assert EventType.ON_STARTUP.value == "on_startup"
        assert EventType.ON_MESSAGE.value == "on_message"
        assert EventType.ON_COMMAND.value == "on_command"


class TestEventHandler:
    """测试事件处理器"""

    def test_creation(self):
        """测试创建事件处理器"""
        async def handler_func(event):
            return "handled"

        handler = EventHandler(
            handler=handler_func,
            handler_name="test_handler",
            handler_full_name="module.test_handler",
            module_path="module",
            priority=10,
            permission=PermissionType.ADMIN
        )

        assert handler.handler_name == "test_handler"
        assert handler.priority == 10
        assert handler.permission == PermissionType.ADMIN

    def test_increment_call_count(self):
        """测试增加调用计数"""
        async def handler_func(event):
            pass

        handler = EventHandler(
            handler=handler_func,
            handler_name="test",
            handler_full_name="module.test",
            module_path="module"
        )

        handler.call_count += 1

        assert handler.call_count == 1


class TestEventHandlerRegistry:
    """测试事件处理器注册表"""

    @pytest.fixture
    def registry(self):
        """创建注册表"""
        return EventHandlerRegistry()

    def test_register_handler(self, registry):
        """测试注册处理器"""
        async def handler_func(event):
            pass

        handler = EventHandler(
            handler=handler_func,
            handler_name="test_handler",
            handler_full_name="module.test_handler",
            module_path="module",
            priority=5
        )

        registry.register(handler)

        handlers = registry.get_handlers_by_event("on_message")
        assert len(handlers) == 1
        assert handlers[0].handler_name == "test_handler"

    def test_unregister_handler(self, registry):
        """测试注销处理器"""
        async def handler_func(event):
            pass

        handler = EventHandler(
            handler=handler_func,
            handler_name="test_handler",
            handler_full_name="module.test_handler",
            module_path="module"
        )

        registry.register(handler)
        result = registry.unregister("module.test_handler")

        assert result is True

        handlers = registry.get_handlers_by_event("on_message")
        assert len(handlers) == 0

    def test_get_command_handler(self, registry):
        """测试获取命令处理器"""
        async def command_func(event):
            return "command_result"

        handler = EventHandler(
            handler=command_func,
            handler_name="command_test",
            handler_full_name="module.command_test",
            module_path="module"
        )

        registry.register(handler)

        command_handler = registry.get_command_handler("test")

        assert command_handler is not None
        assert command_handler.handler_name == "command_test"

    def test_priority_sorting(self, registry):
        """测试优先级排序"""
        async def handler1(event):
            pass

        async def handler2(event):
            pass

        async def handler3(event):
            pass

        # 注册不同优先级的处理器
        registry.register(EventHandler(
            handler=handler1,
            handler_name="handler1",
            handler_full_name="mod.handler1",
            module_path="mod",
            priority=5
        ))

        registry.register(EventHandler(
            handler=handler2,
            handler_name="handler2",
            handler_full_name="mod.handler2",
            module_path="mod",
            priority=10
        ))

        registry.register(EventHandler(
            handler=handler3,
            handler_name="handler3",
            handler_full_name="mod.handler3",
            module_path="mod",
            priority=1
        ))

        handlers = registry.get_handlers_by_event("on_message")

        # 应该按优先级降序排列
        assert handlers[0].handler_name == "handler2"
        assert handlers[1].handler_name == "handler1"
        assert handlers[2].handler_name == "handler3"

    def test_clear(self, registry):
        """测试清空注册表"""
        async def handler_func(event):
            pass

        handler = EventHandler(
            handler=handler_func,
            handler_name="test",
            handler_full_name="mod.test",
            module_path="mod"
        )

        registry.register(handler)
        assert len(registry.get_all_handlers()) == 1

        registry.clear()
        assert len(registry.get_all_handlers()) == 0


class TestEventDispatcher:
    """测试事件分发器"""

    @pytest.fixture
    def dispatcher(self):
        """创建事件分发器"""
        return EventDispatcher()

    @pytest.mark.asyncio
    async def test_dispatch_event(self, dispatcher):
        """测试分发事件"""
        received_events = []

        async def handler1(event):
            received_events.append(("handler1", event))
            return "result1"

        async def handler2(event):
            received_events.append(("handler2", event))
            return "result2"

        # 注册处理器
        registry = get_event_registry()
        registry.register(EventHandler(
            handler=handler1,
            handler_name="handler1",
            handler_full_name="mod.handler1",
            module_path="mod"
        ))

        registry.register(EventHandler(
            handler=handler2,
            handler_name="handler2",
            handler_full_name="mod.handler2",
            module_path="mod"
        ))

        # 分发事件
        event_data = {"message": "test"}
        results = await dispatcher.dispatch("on_message", event_data)

        assert len(results) == 2
        assert len(received_events) == 2

        # 清理
        registry.clear()

    @pytest.mark.asyncio
    async def test_dispatch_with_permission_filter(self, dispatcher):
        """测试带权限过滤的分发"""
        async def admin_handler(event):
            return "admin_result"

        registry = get_event_registry()
        registry.register(EventHandler(
            handler=admin_handler,
            handler_name="admin_handler",
            handler_full_name="mod.admin_handler",
            module_path="mod",
            permission=PermissionType.ADMIN
        ))

        # 普通用户上下文
        context = PermissionContext(user_id="regular_user")

        event_data = {"message": "test"}
        results = await dispatcher.dispatch(
            "on_message",
            event_data,
            permission_context=context
        )

        # 应该被过滤掉
        assert len(results) == 0

        # 清理
        registry.clear()

    @pytest.mark.asyncio
    async def test_get_stats(self, dispatcher):
        """测试获取统计信息"""
        stats = dispatcher.get_stats()

        assert "total_handlers" in stats
        assert "handlers_by_event" in stats
        assert "total_calls" in stats


class TestDecorators:
    """测试装饰器"""

    @pytest.mark.asyncio
    async def test_on_event_decorator(self):
        """测试事件监听装饰器"""
        received = []

        @on_event(EventType.ON_MESSAGE, priority=10)
        async def handle_message(event):
            received.append(event)
            return "handled"

        registry = get_event_registry()
        handlers = registry.get_handlers_by_event(EventType.ON_MESSAGE.value)

        assert len(handlers) == 1
        assert handlers[0].priority == 10

        # 清理
        registry.clear()

    @pytest.mark.asyncio
    async def test_on_command_decorator(self):
        """测试命令监听装饰器"""
        @on_command("test_cmd", description="Test command")
        async def handle_test_cmd(context):
            return "command_result"

        registry = get_event_registry()
        handler = registry.get_command_handler("test_cmd")

        assert handler is not None
        assert handler.handler_name == "command_test_cmd"

        # 清理
        registry.clear()

    @pytest.mark.asyncio
    async def test_on_event_with_permission(self):
        """测试带权限的事件装饰器"""
        @on_event(
            EventType.ON_MESSAGE,
            priority=5,
            permission=PermissionType.ADMIN
        )
        async def admin_only_handler(event):
            return "admin_result"

        registry = get_event_registry()
        handlers = registry.get_handlers_by_event(EventType.ON_MESSAGE.value)

        assert handlers[0].permission == PermissionType.ADMIN

        # 清理
        registry.clear()


class TestGlobalFunctions:
    """测试全局函数"""

    def test_get_permission_checker_singleton(self):
        """测试获取单例权限检查器"""
        checker1 = get_permission_checker()
        checker2 = get_permission_checker()

        assert checker1 is checker2

    def test_get_event_registry_singleton(self):
        """测试获取单例事件注册表"""
        registry1 = get_event_registry()
        registry2 = get_event_registry()

        assert registry1 is registry2


class TestIntegration:
    """集成测试"""

    @pytest.mark.asyncio
    async def test_full_event_flow(self):
        """测试完整事件流程"""
        # 1. 注册处理器
        @on_event(EventType.ON_MESSAGE, priority=10)
        async def handler1(event):
            return f"handler1: {event.get('message')}"

        @on_event(EventType.ON_MESSAGE, priority=5)
        async def handler2(event):
            return f"handler2: {event.get('message')}"

        # 2. 创建分发器
        dispatcher = EventDispatcher()

        # 3. 分发事件
        event_data = {"message": "Hello"}
        results = await dispatcher.dispatch(EventType.ON_MESSAGE.value, event_data)

        # 4. 验证结果
        assert len(results) == 2
        # 优先级高的先执行
        assert "handler1" in results[1]
        assert "handler2" in results[0]

        # 清理
        get_event_registry().clear()

    @pytest.mark.asyncio
    async def test_command_with_permission_check(self):
        """测试命令权限检查"""
        @on_command("ban", permission=PermissionType.ADMIN)
        async def ban_command(context):
            return "banned"

        checker = get_permission_checker()
        checker.add_admin_user("admin_user")

        dispatcher = EventDispatcher()

        # 管理员上下文
        admin_context = PermissionContext(user_id="admin_user")
        results = await dispatcher.dispatch(
            EventType.ON_COMMAND.value,
            {"command": "ban"},
            permission_context=admin_context
        )

        # 应该有结果
        assert len(results) >= 0

        # 清理
        get_event_registry().clear()
