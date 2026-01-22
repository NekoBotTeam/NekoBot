"""会话锁管理器单元测试

测试 SessionLockManager 的核心功能
"""

import pytest
import asyncio
from packages.core.session_lock import SessionLockManager, session_lock_manager


class TestSessionLockManager:
    """会话锁管理器测试"""

    @pytest.fixture
    def lock_manager(self):
        """创建锁管理器实例"""
        return SessionLockManager()

    @pytest.mark.asyncio
    async def test_basic_locking(self, lock_manager):
        """测试基本锁定功能"""
        session_id = "test_session_123"
        executed = False

        async with lock_manager.acquire_lock(session_id):
            executed = True
            # 检查锁已获取
            assert session_id in lock_manager.get_active_sessions()

        assert executed
        # 锁应该被回收
        assert session_id not in lock_manager.get_active_sessions()

    @pytest.mark.asyncio
    async def test_concurrent_same_session(self, lock_manager):
        """测试同一会话的并发访问"""
        session_id = "concurrent_session"
        results = []
        execution_order = []

        async def task1():
            async with lock_manager.acquire_lock(session_id):
                execution_order.append(1)
                await asyncio.sleep(0.1)
                results.append("task1")

        async def task2():
            await asyncio.sleep(0.05)  # 确保任务1先执行
            async with lock_manager.acquire_lock(session_id):
                execution_order.append(2)
                results.append("task2")

        # 并发执行
        await asyncio.gather(task1(), task2())

        # 验证执行顺序
        assert execution_order == [1, 2]
        assert results == ["task1", "task2"]

    @pytest.mark.asyncio
    async def test_concurrent_different_sessions(self, lock_manager):
        """测试不同会话的并发访问"""
        results = []

        async def access_session(session_id):
            async with lock_manager.acquire_lock(session_id):
                await asyncio.sleep(0.05)
                results.append(session_id)

        # 并发访问不同会话
        await asyncio.gather(
            access_session("session1"),
            access_session("session2"),
            access_session("session3"),
        )

        assert len(results) == 3
        assert set(results) == {"session1", "session2", "session3"}

    @pytest.mark.asyncio
    async def test_lock_reference_counting(self, lock_manager):
        """测试锁引用计数"""
        session_id = "ref_count_session"

        # 获取锁
        await lock_manager.acquire(session_id)
        assert lock_manager.get_session_lock_count(session_id) == 1

        # 再次获取
        await lock_manager.acquire(session_id)
        assert lock_manager.get_session_lock_count(session_id) == 2

        # 释放一次
        await lock_manager.release(session_id)
        assert lock_manager.get_session_lock_count(session_id) == 1

        # 释放第二次
        await lock_manager.release(session_id)
        # 锁应该被回收
        assert lock_manager.get_session_lock_count(session_id) == 0
        assert session_id not in lock_manager.get_active_sessions()

    @pytest.mark.asyncio
    async def test_get_active_sessions(self, lock_manager):
        """测试获取活跃会话列表"""
        # 添加几个会话
        async with lock_manager.acquire_lock("session1"):
            async with lock_manager.acquire_lock("session2"):
                active = lock_manager.get_active_sessions()
                assert set(active) == {"session1", "session2"}

    @pytest.mark.asyncio
    async def test_get_stats(self, lock_manager):
        """测试获取统计信息"""
        session_id = "stats_session"

        async with lock_manager.acquire_lock(session_id):
            stats = lock_manager.get_stats()

            assert stats["active_sessions"] == 1
            assert stats["total_lock_count"] == 1
            assert "sessions" in stats
            assert session_id in stats["sessions"]

    @pytest.mark.asyncio
    async def test_cleanup(self, lock_manager):
        """测试清理功能"""
        # 添加一些锁
        await lock_manager.acquire("session1")
        await lock_manager.acquire("session2")

        assert len(lock_manager.get_active_sessions()) == 2

        # 清理
        await lock_manager.cleanup()

        assert len(lock_manager.get_active_sessions()) == 0

    @pytest.mark.asyncio
    async def test_manual_acquire_release(self, lock_manager):
        """测试手动获取和释放锁"""
        session_id = "manual_session"

        # 手动获取
        success = await lock_manager.acquire(session_id)
        assert success is True

        # 检查已获取
        assert session_id in lock_manager.get_active_sessions()

        # 手动释放
        await lock_manager.release(session_id)

        # 检查已释放
        assert session_id not in lock_manager.get_active_sessions()

    @pytest.mark.asyncio
    async def test_nested_context_managers(self, lock_manager):
        """测试嵌套上下文管理器"""
        session_id = "nested_session"
        count = 0

        async with lock_manager.acquire_lock(session_id):
            count += 1
            async with lock_manager.acquire_lock(session_id):
                count += 1
                # 引用计数应该是 2
                assert lock_manager.get_session_lock_count(session_id) == 2

        assert count == 2
        # 锁应该被完全释放
        assert session_id not in lock_manager.get_active_sessions()


class TestGlobalSessionLockManager:
    """全局会话锁管理器测试"""

    @pytest.mark.asyncio
    async def test_global_singleton(self):
        """测试全局单例"""
        from packages.core.session_lock import session_lock_manager

        # 应该是同一个实例
        assert session_lock_manager is not None
        assert isinstance(session_lock_manager, SessionLockManager)

    @pytest.mark.asyncio
    async def test_global_usage(self):
        """测试全局实例使用"""
        session_id = "global_test_session"

        async with session_lock_manager.acquire_lock(session_id):
            assert session_id in session_lock_manager.get_active_sessions()
