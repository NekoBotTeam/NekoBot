"""并发管理器单元测试

测试 P1: 并发限制控制
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch

from packages.core.concurrency import (
    ConcurrencyLimiter,
    ConcurrencyStats,
    RateLimiter,
    ConcurrencyManager,
    get_concurrency_manager,
    with_concurrency_limit,
)


class TestConcurrencyLimiter:
    """测试并发限制器"""

    @pytest.mark.asyncio
    async def test_basic_limiting(self):
        """测试基本并发限制"""
        limiter = ConcurrencyLimiter(max_concurrent=2)

        async def task(name, delay=0.05):
            await limiter.acquire()
            try:
                await asyncio.sleep(delay)
                return name
            finally:
                await limiter.release()

        # 启动 4 个任务，但只有 2 个能同时运行
        tasks = [task(f"task_{i}") for i in range(4)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 4
        assert all(f"task_{i}" in results for i in range(4))

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """测试上下文管理器"""
        limiter = ConcurrencyLimiter(max_concurrent=2)

        async def task():
            async with limiter:
                await asyncio.sleep(0.05)
                return "done"

        # 启动多个任务
        tasks = [asyncio.create_task(task()) for _ in range(4)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 4

    @pytest.mark.asyncio
    async def test_max_concurrent_enforced(self):
        """测试最大并发数强制执行"""
        limiter = ConcurrencyLimiter(max_concurrent=2)
        running_count = 0
        max_running = 0
        lock = asyncio.Lock()

        async def tracking_task():
            nonlocal running_count, max_running
            await limiter.acquire()
            async with lock:
                running_count += 1
                if running_count > max_running:
                    max_running = running_count
            try:
                await asyncio.sleep(0.05)
            finally:
                async with lock:
                    running_count -= 1
                await limiter.release()

        # 启动 10 个任务
        tasks = [tracking_task() for _ in range(10)]
        await asyncio.gather(*tasks)

        # 最大并发数不应该超过 2
        assert max_running <= 2

    @pytest.mark.asyncio
    async def test_timeout(self):
        """测试超时处理"""
        limiter = ConcurrencyLimiter(max_concurrent=1, timeout=0.1)

        # 先获取许可
        await limiter.acquire()

        # 第二次获取应该超时
        success = await limiter.acquire()
        assert success is False

        # 释放许可
        await limiter.release()

    @pytest.mark.asyncio
    async def test_get_stats(self):
        """测试获取统计信息"""
        limiter = ConcurrencyLimiter(max_concurrent=3)

        stats = limiter.get_stats()

        assert "max_concurrent" in stats
        assert "timeout" in stats
        assert stats["max_concurrent"] == 3
        assert stats["current_concurrent"] == 0

    @pytest.mark.asyncio
    async def test_stats_update(self):
        """测试统计信息更新"""
        limiter = ConcurrencyLimiter(max_concurrent=2)

        async def task():
            await limiter.acquire()
            await asyncio.sleep(0.05)
            await limiter.release()

        # 运行任务
        task1 = asyncio.create_task(task())
        await asyncio.sleep(0.01)  # 让任务1开始

        stats = limiter.get_stats()
        assert stats["current_concurrent"] == 1

        await task1

    @pytest.mark.asyncio
    async def test_reset_stats(self):
        """测试重置统计"""
        limiter = ConcurrencyLimiter(max_concurrent=2)

        # 进行一些操作
        await limiter.acquire()
        await limiter.release()

        stats = limiter.get_stats()
        assert stats["total_acquires"] == 1

        # 重置
        limiter.reset_stats()

        stats = limiter.get_stats()
        assert stats["total_acquires"] == 0


class TestRateLimiter:
    """测试速率限制器"""

    @pytest.mark.asyncio
    async def test_basic_rate_limiting(self):
        """测试基本速率限制"""
        limiter = RateLimiter(max_requests=3, time_window_seconds=0.1)

        # 前 3 个请求应该成功
        assert await limiter.acquire(key="user1") is True
        assert await limiter.acquire(key="user1") is True
        assert await limiter.acquire(key="user1") is True

        # 第 4 个请求应该被限制
        assert await limiter.acquire(key="user1") is False

    @pytest.mark.asyncio
    async def test_time_window_reset(self):
        """测试时间窗口重置"""
        limiter = RateLimiter(max_requests=2, time_window_seconds=0.1)

        # 使用所有配额
        assert await limiter.acquire(key="user1") is True
        assert await limiter.acquire(key="user1") is True
        assert await limiter.acquire(key="user1") is False

        # 等待时间窗口重置
        await asyncio.sleep(0.15)

        # 现在应该可以再次请求
        assert await limiter.acquire(key="user1") is True

    @pytest.mark.asyncio
    async def test_separate_keys(self):
        """测试不同的 key 独立计数"""
        limiter = RateLimiter(max_requests=2, time_window_seconds=1)

        # 用户1
        assert await limiter.acquire(key="user1") is True
        assert await limiter.acquire(key="user1") is True
        assert await limiter.acquire(key="user1") is False

        # 用户2 应该有自己的配额
        assert await limiter.acquire(key="user2") is True
        assert await limiter.acquire(key="user2") is True

    @pytest.mark.asyncio
    async def test_get_stats(self):
        """测试获取统计信息"""
        limiter = RateLimiter(max_requests=5, time_window_seconds=1)

        await limiter.acquire(key="test")
        await limiter.acquire(key="test")

        stats = limiter.get_stats(key="test")

        assert stats["current_requests"] == 2
        assert stats["remaining_requests"] == 3
        assert stats["max_requests"] == 5

    @pytest.mark.asyncio
    async def test_stats_decay_over_time(self):
        """测试统计随时间衰减"""
        limiter = RateLimiter(max_requests=3, time_window_seconds=0.1)

        # 使用所有配额
        await limiter.acquire(key="test")
        await limiter.acquire(key="test")
        await limiter.acquire(key="test")

        stats = limiter.get_stats(key="test")
        assert stats["current_requests"] == 3

        # 等待时间窗口过期
        await asyncio.sleep(0.15)

        # 旧请求应该被清理
        stats = limiter.get_stats(key="test")
        assert stats["current_requests"] < 3


class TestConcurrencyManager:
    """测试并发管理器"""

    @pytest.fixture
    def manager(self):
        """创建并发管理器实例"""
        return ConcurrencyManager()

    @pytest.mark.asyncio
    async def test_get_limiter(self, manager):
        """测试获取并发限制器"""
        limiter = await manager.get_limiter("api_calls", max_concurrent=10)

        assert isinstance(limiter, ConcurrencyLimiter)
        assert limiter.max_concurrent == 10

    @pytest.mark.asyncio
    async def test_get_rate_limiter(self, manager):
        """测试获取速率限制器"""
        rate_limiter = await manager.get_rate_limiter(
            "user_api",
            max_requests=100,
            time_window_seconds=60
        )

        assert isinstance(rate_limiter, RateLimiter)

    @pytest.mark.asyncio
    async def test_limiter_reuse(self, manager):
        """测试限制器复用"""
        limiter1 = await manager.get_limiter("shared", max_concurrent=5)
        limiter2 = await manager.get_limiter("shared", max_concurrent=5)

        # 应该返回同一个实例
        assert limiter1 is limiter2

    @pytest.mark.asyncio
    async def test_get_all_stats(self, manager):
        """测试获取所有统计信息"""
        await manager.get_limiter("test", max_concurrent=5)
        await manager.get_rate_limiter("rate1", max_requests=100, time_window_seconds=60)

        stats = manager.get_all_stats()

        assert "concurrency_limiters" in stats
        assert "rate_limiters" in stats
        assert "test" in stats["concurrency_limiters"]
        assert "rate1" in stats["rate_limiters"]

    @pytest.mark.asyncio
    async def test_close(self, manager):
        """测试关闭管理器"""
        await manager.get_limiter("temp", max_concurrent=5)

        await manager.close()

        # 限制器应该被清空
        stats = manager.get_all_stats()
        assert len(stats["concurrency_limiters"]) == 0


class TestConvenienceFunctions:
    """测试便捷函数"""

    def test_get_concurrency_manager_singleton(self):
        """测试获取单例并发管理器"""
        manager1 = get_concurrency_manager()
        manager2 = get_concurrency_manager()

        assert manager1 is manager2

    @pytest.mark.asyncio
    async def test_with_concurrency_limit(self):
        """测试并发限制便捷函数"""
        async def protected_task():
            await asyncio.sleep(0.05)
            return "success"

        # 使用并发限制
        result = await with_concurrency_limit(
            protected_task(),
            limiter_name="test_resource",
            max_concurrent=1
        )

        assert result == "success"


class TestConcurrencyIntegration:
    """集成测试"""

    @pytest.mark.asyncio
    async def test_combined_limits(self):
        """测试组合限制"""
        manager = ConcurrencyManager()

        # 同时使用并发限制和速率限制
        conc_limiter = await manager.get_limiter("api", max_concurrent=2)
        rate_limiter = await manager.get_rate_limiter("api", max_requests=3, time_window_seconds=0.1)

        success_count = 0
        rate_limited_count = 0

        async def limited_task():
            nonlocal success_count, rate_limited_count

            if not await rate_limiter.acquire(key="test"):
                rate_limited_count += 1
                return

            await conc_limiter.acquire()
            try:
                success_count += 1
                await asyncio.sleep(0.02)
            finally:
                await conc_limiter.release()

        # 尝试执行 5 个任务
        tasks = [limited_task() for _ in range(5)]
        await asyncio.gather(*tasks)

        # 应该有部分被速率限制
        assert success_count <= 3
        assert rate_limited_count >= 2

    @pytest.mark.asyncio
    async def test_concurrent_acquisitions(self):
        """测试并发获取许可"""
        limiter = ConcurrencyLimiter(max_concurrent=3)

        async def worker():
            await limiter.acquire()
            await asyncio.sleep(0.05)
            await limiter.release()
            return "done"

        # 启动多个任务
        tasks = [worker() for _ in range(10)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 10

    @pytest.mark.asyncio
    async def test_stats_tracking(self):
        """测试统计追踪"""
        limiter = ConcurrencyLimiter(max_concurrent=2)

        # 执行一些操作
        await limiter.acquire()
        await limiter.release()

        await limiter.acquire()
        await limiter.release()

        stats = limiter.get_stats()

        assert stats["total_acquires"] == 2
        assert stats["total_releases"] == 2
        assert stats["peak_concurrent"] >= 1

    @pytest.mark.asyncio
    async def test_timeout_behavior(self):
        """测试超时行为"""
        limiter = ConcurrencyLimiter(max_concurrent=1, timeout=0.05)

        # 获取许可
        await limiter.acquire()

        # 尝试再次获取（应该超时）
        success = await limiter.acquire()
        assert success is False

        # 检查统计
        stats = limiter.get_stats()
        assert stats["total_timeouts"] >= 1

        # 释放许可
        await limiter.release()

        # 现在应该可以获取
        success = await limiter.acquire()
        assert success is True
