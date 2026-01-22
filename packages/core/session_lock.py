"""会话锁管理器

参考 AstrBot 实现，提供细粒度的会话级并发控制
支持智能锁回收，避免内存泄漏
"""

import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from loguru import logger


class SessionLockManager:
    """会话锁管理器

    提供会话级别的并发控制，自动回收未使用的锁

    特性：
    - 细粒度会话级锁（每个会话独立锁）
    - 引用计数追踪锁的使用
    - 自动回收未使用的锁
    - 线程安全的锁管理
    """

    def __init__(self):
        """初始化会话锁管理器"""
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._lock_count: dict[str, int] = defaultdict(int)
        self._access_lock = asyncio.Lock()

    @asynccontextmanager
    async def acquire_lock(self, session_id: str) -> AsyncGenerator[None, None]:
        """获取会话锁

        Args:
            session_id: 会话标识符

        Yields:
            None

        Example:
            >>> async with session_lock_manager.acquire_lock("user_123"):
            ...     # 执行需要加锁的操作
            ...     pass
        """
        # 获取访问锁并更新引用计数
        async with self._access_lock:
            lock = self._locks[session_id]
            self._lock_count[session_id] += 1
            logger.debug(
                f"获取会话锁: {session_id}, "
                f"当前引用计数: {self._lock_count[session_id]}"
            )

        try:
            # 获取会话锁
            async with lock:
                yield
        finally:
            # 释放访问锁并更新引用计数
            async with self._access_lock:
                self._lock_count[session_id] -= 1

                # 当引用计数为 0 时，自动回收锁
                if self._lock_count[session_id] == 0:
                    self._locks.pop(session_id, None)
                    self._lock_count.pop(session_id, None)
                    logger.debug(f"回收会话锁: {session_id}")

    async def acquire(self, session_id: str) -> bool:
        """获取会话锁（非上下文管理器方式）

        Args:
            session_id: 会话标识符

        Returns:
            是否成功获取锁
        """
        try:
            async with self._access_lock:
                lock = self._locks[session_id]
                self._lock_count[session_id] += 1
            await lock.acquire()
            return True
        except Exception as e:
            logger.error(f"获取会话锁失败 {session_id}: {e}")
            return False

    async def release(self, session_id: str) -> None:
        """释放会话锁（非上下文管理器方式）

        Args:
            session_id: 会话标识符
        """
        async with self._access_lock:
            if session_id in self._locks:
                self._locks[session_id].release()
                self._lock_count[session_id] -= 1

                # 当引用计数为 0 时，自动回收锁
                if self._lock_count[session_id] == 0:
                    self._locks.pop(session_id, None)
                    self._lock_count.pop(session_id, None)
                    logger.debug(f"回收会话锁: {session_id}")

    def get_active_sessions(self) -> list[str]:
        """获取当前活跃的会话列表

        Returns:
            活跃会话ID列表
        """
        return list(self._locks.keys())

    def get_session_lock_count(self, session_id: str) -> int:
        """获取指定会话的锁引用计数

        Args:
            session_id: 会话标识符

        Returns:
            锁引用计数
        """
        return self._lock_count.get(session_id, 0)

    def get_stats(self) -> dict:
        """获取会话锁统计信息

        Returns:
            统计信息字典
        """
        return {
            "active_sessions": len(self._locks),
            "total_lock_count": sum(self._lock_count.values()),
            "sessions": {
                session_id: {
                    "lock_count": count,
                    "locked": self._locks[session_id].locked()
                }
                for session_id, count in self._lock_count.items()
            }
        }

    async def cleanup(self) -> None:
        """清理所有会话锁"""
        async with self._access_lock:
            self._locks.clear()
            self._lock_count.clear()
            logger.info("会话锁管理器已清理")


# 创建全局会话锁管理器实例
session_lock_manager = SessionLockManager()


__all__ = [
    "SessionLockManager",
    "session_lock_manager",
]
