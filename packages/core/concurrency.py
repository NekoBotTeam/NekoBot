"""并发管理器

提供并发限制和控制功能，防止系统过载
"""

import asyncio
import time
from typing import Optional, Dict, Any, Awaitable
from dataclasses import dataclass
from datetime import datetime, timedelta
from loguru import logger
from collections import defaultdict


@dataclass
class ConcurrencyStats:
    """并发统计信息"""
    total_acquires: int = 0
    total_releases: int = 0
    total_waits: int = 0
    total_timeouts: int = 0
    peak_concurrent: int = 0
    current_concurrent: int = 0
    total_wait_time_ms: float = 0
    avg_wait_time_ms: float = 0


class ConcurrencyLimiter:
    """并发限制器

    使用信号量控制并发操作数量
    """

    def __init__(self, max_concurrent: int = 100, timeout: float = 30.0):
        """初始化并发限制器

        Args:
            max_concurrent: 最大并发数
            timeout: 获取许可的超时时间（秒）
        """
        self.max_concurrent = max_concurrent
        self.timeout = timeout
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._stats = ConcurrencyStats()
        self._lock = asyncio.Lock()

    async def acquire(self, name: Optional[str] = None) -> bool:
        """获取并发许可

        Args:
            name: 操作名称（用于日志和追踪）

        Returns:
            是否成功获取许可
        """
        start_time = time.time()
        op_name = name or "unknown"

        try:
            # 等待获取信号量
            await asyncio.wait_for(self._semaphore.acquire(), timeout=self.timeout)

            wait_time = (time.time() - start_time) * 1000

            async with self._lock:
                self._stats.total_acquires += 1
                self._stats.total_waits += 1
                self._stats.total_wait_time_ms += wait_time
                self._stats.current_concurrent += 1

                # 更新峰值
                if self._stats.current_concurrent > self._stats.peak_concurrent:
                    self._stats.peak_concurrent = self._stats.current_concurrent

                # 更新平均等待时间
                if self._stats.total_waits > 0:
                    self._stats.avg_wait_time_ms = (
                        self._stats.total_wait_time_ms / self._stats.total_waits
                    )

            logger.debug(f"并发许可获取成功: {op_name}, 等待: {wait_time:.2f}ms")
            return True

        except asyncio.TimeoutError:
            async with self._lock:
                self._stats.total_timeouts += 1

            logger.warning(f"并发许可获取超时: {op_name}, 超时: {self.timeout}秒")
            return False

    async def release(self, name: Optional[str] = None) -> None:
        """释放并发许可

        Args:
            name: 操作名称
        """
        op_name = name or "unknown"

        self._semaphore.release()

        async with self._lock:
            self._stats.total_releases += 1
            self._stats.current_concurrent -= 1

        logger.debug(f"并发许可已释放: {op_name}")

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.release()

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息

        Returns:
            统计信息字典
        """
        return {
            "max_concurrent": self.max_concurrent,
            "timeout": self.timeout,
            "total_acquires": self._stats.total_acquires,
            "total_releases": self._stats.total_releases,
            "total_waits": self._stats.total_waits,
            "total_timeouts": self._stats.total_timeouts,
            "peak_concurrent": self._stats.peak_concurrent,
            "current_concurrent": self._stats.current_concurrent,
            "avg_wait_time_ms": self._stats.avg_wait_time_ms,
        }

    def reset_stats(self) -> None:
        """重置统计信息"""
        self._stats = ConcurrencyStats()
        logger.debug("并发统计信息已重置")


class RateLimiter:
    """速率限制器

    控制操作的执行速率
    """

    def __init__(self, max_requests: int, time_window_seconds: float = 1.0):
        """初始化速率限制器

        Args:
            max_requests: 时间窗口内最大请求数
            time_window_seconds: 时间窗口（秒）
        """
        self.max_requests = max_requests
        self.time_window = timedelta(seconds=time_window_seconds)
        self._requests: defaultdict = defaultdict(list)
        self._lock = asyncio.Lock()

    async def acquire(self, key: str = "default") -> bool:
        """获取执行许可

        Args:
            key: 限制键（例如用户ID、IP地址等）

        Returns:
            是否允许执行
        """
        async with self._lock:
            now = datetime.now()
            window_start = now - self.time_window

            # 清理过期的请求记录
            self._requests[key] = [
                req_time for req_time in self._requests[key]
                if req_time > window_start
            ]

            # 检查是否超过限制
            if len(self._requests[key]) >= self.max_requests:
                logger.warning(f"速率限制触发: {key}, 请求数: {len(self._requests[key])}")
                return False

            # 记录本次请求
            self._requests[key].append(now)
            return True

    def get_stats(self, key: str = "default") -> Dict[str, Any]:
        """获取统计信息

        Args:
            key: 限制键

        Returns:
            统计信息字典
        """
        now = datetime.now()
        window_start = now - self.time_window

        recent_requests = [
            req_time for req_time in self._requests.get(key, [])
            if req_time > window_start
        ]

        return {
            "key": key,
            "max_requests": self.max_requests,
            "time_window_seconds": self.time_window.total_seconds(),
            "current_requests": len(recent_requests),
            "remaining_requests": max(0, self.max_requests - len(recent_requests)),
        }


class ConcurrencyManager:
    """并发管理器

    管理多个并发限制器和速率限制器
    """

    def __init__(self):
        """初始化并发管理器"""
        self._limiters: Dict[str, ConcurrencyLimiter] = {}
        self._rate_limiters: Dict[str, RateLimiter] = {}
        self._lock = asyncio.Lock()

    async def get_limiter(
        self,
        name: str,
        max_concurrent: int = 100,
        timeout: float = 30.0
    ) -> ConcurrencyLimiter:
        """获取或创建并发限制器

        Args:
            name: 限制器名称
            max_concurrent: 最大并发数
            timeout: 超时时间

        Returns:
            并发限制器
        """
        async with self._lock:
            if name not in self._limiters:
                self._limiters[name] = ConcurrencyLimiter(max_concurrent, timeout)
                logger.info(f"创建并发限制器: {name}, 最大并发: {max_concurrent}")
            return self._limiters[name]

    async def get_rate_limiter(
        self,
        name: str,
        max_requests: int,
        time_window_seconds: float = 1.0
    ) -> RateLimiter:
        """获取或创建速率限制器

        Args:
            name: 限制器名称
            max_requests: 最大请求数
            time_window_seconds: 时间窗口

        Returns:
            速率限制器
        """
        async with self._lock:
            if name not in self._rate_limiters:
                self._rate_limiters[name] = RateLimiter(max_requests, time_window_seconds)
                logger.info(f"创建速率限制器: {name}, 最大请求: {max_requests}/{time_window_seconds}s")
            return self._rate_limiters[name]

    def get_all_stats(self) -> Dict[str, Any]:
        """获取所有限制器的统计信息

        Returns:
            统计信息字典
        """
        return {
            "concurrency_limiters": {
                name: limiter.get_stats()
                for name, limiter in self._limiters.items()
            },
            "rate_limiters": {
                name: limiter.get_stats()
                for name, limiter in self._rate_limiters.items()
            },
        }

    async def close(self) -> None:
        """关闭并发管理器，清理资源"""
        async with self._lock:
            self._limiters.clear()
            self._rate_limiters.clear()
        logger.info("并发管理器已关闭")


# 全局并发管理器实例
_global_concurrency_manager: Optional[ConcurrencyManager] = None


def get_concurrency_manager() -> ConcurrencyManager:
    """获取全局并发管理器实例

    Returns:
        并发管理器实例
    """
    global _global_concurrency_manager
    if _global_concurrency_manager is None:
        _global_concurrency_manager = ConcurrencyManager()
    return _global_concurrency_manager


# 预定义的并发限制器
async def with_concurrency_limit(
    coro: Awaitable,
    limiter_name: str = "default",
    max_concurrent: int = 100,
    timeout: float = 30.0
) -> Any:
    """在并发限制下执行协程

    Args:
        coro: 协程
        limiter_name: 限制器名称
        max_concurrent: 最大并发数
        timeout: 超时时间

    Returns:
        协程执行结果
    """
    manager = get_concurrency_manager()
    limiter = await manager.get_limiter(limiter_name, max_concurrent, timeout)

    async with limiter:
        return await coro


__all__ = [
    "ConcurrencyStats",
    "ConcurrencyLimiter",
    "RateLimiter",
    "ConcurrencyManager",
    "get_concurrency_manager",
    "with_concurrency_limit",
]
