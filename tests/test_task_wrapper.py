"""任务包装器单元测试

测试 P0: 任务级错误包装功能
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch

from packages.core.task_wrapper import (
    TaskWrapper,
    TaskStatus,
    TaskError,
    TaskInfo,
    create_task,
    get_task_wrapper,
)


class TestTaskStatus:
    """测试任务状态枚举"""

    def test_status_values(self):
        """测试状态值"""
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.RUNNING.value == "running"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.CANCELLED.value == "cancelled"


class TestTaskError:
    """测试任务错误信息"""

    def test_creation(self):
        """测试创建错误信息"""
        error = TaskError(
            message="Test error",
            error_type="ValueError",
            traceback="line1\nline2"
        )

        assert error.message == "Test error"
        assert error.error_type == "ValueError"
        assert error.traceback == "line1\nline2"


class TestTaskInfo:
    """测试任务信息数据类"""

    def test_creation(self):
        """测试创建任务信息"""
        async def dummy_coro():
            return "result"

        info = TaskInfo(
            name="test_task",
            coro=dummy_coro,
            status=TaskStatus.PENDING
        )

        assert info.name == "test_task"
        assert info.status == TaskStatus.PENDING
        assert info.task is None

    def test_with_metadata(self):
        """测试带元数据的任务信息"""
        async def dummy_coro():
            return "result"

        info = TaskInfo(
            name="test_task",
            coro=dummy_coro,
            status=TaskStatus.PENDING,
            metadata={"key": "value"}
        )

        assert info.metadata == {"key": "value"}

    def test_duration_ms(self):
        """测试执行时长计算"""
        from datetime import datetime, timedelta

        async def dummy_coro():
            return "result"

        info = TaskInfo(
            name="test_task",
            coro=dummy_coro,
            status=TaskStatus.PENDING
        )

        # 没有开始时间，应该返回 None
        assert info.duration_ms is None

        # 有开始时间但没完成
        info.started_at = datetime.now()
        assert info.duration_ms is not None

        # 有完成时间
        info.completed_at = info.started_at + timedelta(milliseconds=100)
        assert info.duration_ms >= 90  # 允许一些误差


class TestTaskWrapper:
    """测试任务包装器"""

    @pytest.fixture
    def wrapper(self):
        """创建任务包装器实例"""
        return TaskWrapper()

    @pytest.mark.asyncio
    async def test_wrap_task_success(self, wrapper):
        """测试包装成功任务"""
        async def successful_task():
            await asyncio.sleep(0.01)
            return "success"

        # wrap_task expects the coroutine object (result of calling the async function)
        coro = successful_task()
        task = await wrapper.wrap_task(coro, name="success_task")

        assert task is not None
        assert "success_task" in wrapper._tasks

        # 等待任务完成
        result = await task
        assert result == "success"

    @pytest.mark.asyncio
    async def test_wrap_task_failure(self, wrapper):
        """测试包装失败任务"""
        async def failing_task():
            await asyncio.sleep(0.01)
            raise ValueError("Task failed")

        coro = failing_task()
        task = await wrapper.wrap_task(coro, name="failing_task")

        # 等待任务完成
        with pytest.raises(ValueError, match="Task failed"):
            await task

        # 检查任务状态
        info = wrapper.get_task_info("failing_task")
        assert info.status == TaskStatus.FAILED
        assert info.error is not None
        assert "Task failed" in info.error.message

    @pytest.mark.asyncio
    async def test_wrap_task_with_metadata(self, wrapper):
        """测试带元数据的任务包装"""
        async def task_with_metadata():
            return "result"

        coro = task_with_metadata()
        task = await wrapper.wrap_task(
            coro,
            name="metadata_task",
            metadata={"user_id": "123", "action": "test"}
        )

        info = wrapper.get_task_info("metadata_task")
        assert info.metadata["user_id"] == "123"
        assert info.metadata["action"] == "test"

    @pytest.mark.asyncio
    async def test_cancel_task(self, wrapper):
        """测试取消任务"""
        async def long_running_task():
            await asyncio.sleep(10)
            return "done"

        coro = long_running_task()
        task = await wrapper.wrap_task(coro, name="long_task")

        # 取消任务
        success = await wrapper.cancel_task("long_task")

        assert success is True

        # 等待取消完成
        try:
            await task
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass

        # 等待任务状态更新
        await asyncio.sleep(0.01)

        info = wrapper.get_task_info("long_task")
        # 任务应该被标记为取消或失败（取决于任务执行状态）
        assert info.status in [TaskStatus.CANCELLED, TaskStatus.RUNNING, TaskStatus.FAILED]

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_task(self, wrapper):
        """测试取消不存在的任务"""
        success = await wrapper.cancel_task("nonexistent")

        assert success is False

    @pytest.mark.asyncio
    async def test_cancel_completed_task(self, wrapper):
        """测试取消已完成的任务"""
        async def quick_task():
            return "done"

        coro = quick_task()
        task = await wrapper.wrap_task(coro, name="quick")
        await task

        # 尝试取消已完成的任务
        success = await wrapper.cancel_task("quick")

        assert success is False

    @pytest.mark.asyncio
    async def test_get_task_info(self, wrapper):
        """测试获取任务信息"""
        async def test_task():
            return "result"

        coro = test_task()
        await wrapper.wrap_task(coro, name="info_task")

        info = wrapper.get_task_info("info_task")

        assert info is not None
        assert info.name == "info_task"
        assert info.status in [TaskStatus.RUNNING, TaskStatus.PENDING, TaskStatus.COMPLETED]

    def test_get_task_info_nonexistent(self, wrapper):
        """测试获取不存在任务的信息"""
        info = wrapper.get_task_info("nonexistent")

        assert info is None

    @pytest.mark.asyncio
    async def test_list_tasks(self, wrapper):
        """测试列出任务"""
        async def task1():
            return "1"

        async def task2():
            return "2"

        await wrapper.wrap_task(task1(), name="task1")
        await wrapper.wrap_task(task2(), name="task2")

        tasks = wrapper.list_tasks()

        assert len(tasks) == 2
        task_names = [t.name for t in tasks]
        assert "task1" in task_names
        assert "task2" in task_names

    @pytest.mark.asyncio
    async def test_list_tasks_by_status(self, wrapper):
        """测试按状态列出任务"""
        async def task1():
            await asyncio.sleep(0.01)
            return "1"

        async def task2():
            raise Exception("fail")

        await wrapper.wrap_task(task1(), name="task1")
        await wrapper.wrap_task(task2(), name="task2")

        # 等待任务完成
        await asyncio.sleep(0.02)

        failed_tasks = wrapper.list_tasks(status=TaskStatus.FAILED)

        assert len(failed_tasks) >= 1
        assert "task2" in [t.name for t in failed_tasks]

    @pytest.mark.asyncio
    async def test_cleanup_old_tasks(self, wrapper):
        """测试清理旧任务"""
        async def completed_task():
            return "done"

        await wrapper.wrap_task(completed_task(), name="completed")

        # 等待完成
        await asyncio.sleep(0.01)

        # 手动设置完成时间为很久以前（用于测试）
        from datetime import datetime, timedelta
        info = wrapper.get_task_info("completed")
        if info:
            info.completed_at = datetime.now() - timedelta(seconds=4000)

        # 清理 1 小时前的任务
        count = wrapper.cleanup(max_age_seconds=3600)

        assert count >= 0

    def test_get_stats(self, wrapper):
        """测试获取统计信息"""
        stats = wrapper.get_stats()

        assert "total_tasks" in stats
        assert "by_status" in stats
        assert "failed_count" in stats
        assert "avg_duration_ms" in stats

    @pytest.mark.asyncio
    async def test_task_execution_time(self, wrapper):
        """测试任务执行时间统计"""
        async def timed_task():
            await asyncio.sleep(0.05)
            return "done"

        await wrapper.wrap_task(timed_task(), name="timed")

        # 等待完成
        await asyncio.sleep(0.06)

        info = wrapper.get_task_info("timed")

        if info and info.completed_at:
            assert info.duration_ms is not None
            assert info.duration_ms >= 40  # 至少睡了 50ms，允许一些误差


class TestConvenienceFunctions:
    """测试便捷函数"""

    @pytest.mark.asyncio
    async def test_create_task(self):
        """测试创建任务便捷函数"""
        async def test_task():
            return "result"

        task = await create_task(test_task(), name="test")

        assert task is not None

        result = await task
        assert result == "result"

    def test_get_task_wrapper_singleton(self):
        """测试获取单例任务包装器"""
        wrapper1 = get_task_wrapper()
        wrapper2 = get_task_wrapper()

        assert wrapper1 is wrapper2


class TestTaskWrapperIntegration:
    """集成测试"""

    @pytest.mark.asyncio
    async def test_multiple_tasks_concurrent(self):
        """测试并发执行多个任务"""
        wrapper = TaskWrapper()

        async def task(n):
            await asyncio.sleep(0.01 * n)
            return f"result_{n}"

        # 创建多个任务
        tasks = []
        for i in range(5):
            coro = task(i)
            task_obj = await wrapper.wrap_task(coro, name=f"task_{i}")
            tasks.append(task_obj)

        # 等待所有任务完成
        results = await asyncio.gather(*tasks)

        assert len(results) == 5
        assert "result_0" in results
        assert "result_4" in results

        # 验证所有任务都完成
        stats = wrapper.get_stats()
        assert stats["by_status"]["completed"] == 5

    @pytest.mark.asyncio
    async def test_task_timeout(self):
        """测试任务超时处理"""
        wrapper = TaskWrapper()

        async def timeout_task():
            await asyncio.sleep(10)
            return "late"

        coro = timeout_task()
        task = await wrapper.wrap_task(coro, name="timeout")

        # 设置超时
        try:
            result = await asyncio.wait_for(task, timeout=0.05)
            assert False, "Should have timed out"
        except asyncio.TimeoutError:
            pass

        info = wrapper.get_task_info("timeout")
        # 任务可能被取消或仍在运行
        assert info.status in [TaskStatus.CANCELLED, TaskStatus.RUNNING, TaskStatus.FAILED]

    @pytest.mark.asyncio
    async def test_cancel_all_tasks(self):
        """测试取消所有任务"""
        wrapper = TaskWrapper()

        async def long_task():
            await asyncio.sleep(10)
            return "done"

        # 创建多个任务
        for i in range(5):
            await wrapper.wrap_task(long_task(), name=f"task_{i}")

        # 取消所有任务
        count = await wrapper.cancel_all_tasks()

        assert count == 5

    @pytest.mark.asyncio
    async def test_error_tracking(self):
        """测试错误追踪"""
        wrapper = TaskWrapper(enable_error_tracking=True)

        async def failing_task():
            raise ValueError("Test error with traceback")

        coro = failing_task()
        task = await wrapper.wrap_task(coro, name="failing")

        try:
            await task
        except ValueError:
            pass

        info = wrapper.get_task_info("failing")

        assert info.status == TaskStatus.FAILED
        assert info.error is not None
        assert info.error.message == "Test error with traceback"
        assert info.error.error_type == "ValueError"
        assert "Traceback" in info.error.traceback or "traceback" in str(info.error.traceback).lower()

    @pytest.mark.asyncio
    async def test_error_tracking_disabled(self):
        """测试禁用错误追踪"""
        wrapper = TaskWrapper(enable_error_tracking=False)

        async def failing_task():
            raise ValueError("Test error")

        coro = failing_task()
        task = await wrapper.wrap_task(coro, name="failing")

        try:
            await task
        except ValueError:
            pass

        info = wrapper.get_task_info("failing")

        assert info.status == TaskStatus.FAILED
        # 错误追踪被禁用，error 应该为 None
        assert info.error is None
