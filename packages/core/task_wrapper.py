"""任务包装器

提供任务级错误包装和追踪功能，参考 AstrBot 框架实现
"""

import asyncio
import traceback
from typing import Any, Callable, Optional, Dict, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from loguru import logger


class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    CANCELLED = "cancelled"
    FAILED = "failed"
    COMPLETED = "completed"


@dataclass
class TaskError:
    """任务错误信息"""
    message: str
    error_type: str
    traceback: str
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class TaskInfo:
    """任务信息"""
    name: str
    coro: Callable
    status: TaskStatus = TaskStatus.PENDING
    task: Optional[asyncio.Task] = None
    error: Optional[TaskError] = None
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration_ms(self) -> Optional[float]:
        """获取任务执行时长（毫秒）"""
        if self.started_at is None:
            return None
        end_time = self.completed_at or datetime.now()
        return (end_time - self.started_at).total_seconds() * 1000


class TaskWrapper:
    """任务包装器

    包装异步任务，提供完整的错误处理和追踪
    """

    def __init__(self, enable_error_tracking: bool = True):
        """初始化任务包装器

        Args:
            enable_error_tracking: 是否启用错误追踪
        """
        self._enable_error_tracking = enable_error_tracking
        self._tasks: Dict[str, TaskInfo] = {}
        self._task_counter = 0
        self._lock = asyncio.Lock()

    async def wrap_task(
        self,
        coro: Callable,
        name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> asyncio.Task:
        """包装并创建任务

        Args:
            coro: 协程函数
            name: 任务名称
            metadata: 任务元数据

        Returns:
            异步任务对象
        """
        async with self._lock:
            self._task_counter += 1
            if name is None:
                name = f"task_{self._task_counter}"

            task_info = TaskInfo(
                name=name,
                coro=coro,
                metadata=metadata or {}
            )

            # 创建包装后的协程
            wrapped_coro = self._task_wrapper_impl(task_info)

            # 创建任务
            task = asyncio.create_task(wrapped_coro, name=name)
            task_info.task = task
            task_info.status = TaskStatus.RUNNING
            task_info.started_at = datetime.now()

            self._tasks[name] = task_info

            logger.debug(f"创建任务: {name}")
            return task

    async def _task_wrapper_impl(self, task_info: TaskInfo) -> Any:
        """任务包装器实现

        Args:
            task_info: 任务信息

        Returns:
            任务执行结果
        """
        try:
            logger.info(f"任务开始执行: {task_info.name}")
            result = await task_info.coro
            task_info.status = TaskStatus.COMPLETED
            task_info.completed_at = datetime.now()
            logger.info(f"任务执行完成: {task_info.name}, 耗时: {task_info.duration_ms:.2f}ms")
            return result

        except asyncio.CancelledError:
            task_info.status = TaskStatus.CANCELLED
            task_info.completed_at = datetime.now()
            logger.info(f"任务被取消: {task_info.name}")
            raise

        except Exception as e:
            task_info.status = TaskStatus.FAILED
            task_info.completed_at = datetime.now()

            # 记录错误信息
            if self._enable_error_tracking:
                tb_str = traceback.format_exc()
                task_info.error = TaskError(
                    message=str(e),
                    error_type=type(e).__name__,
                    traceback=tb_str
                )

                # 格式化输出错误
                logger.error(f"------- 任务 {task_info.name} 发生错误 -------")
                logger.error(f"错误类型: {type(e).__name__}")
                logger.error(f"错误消息: {e}")
                for line in tb_str.split("\n"):
                    logger.error(f"| {line}")
                logger.error(f"耗时: {task_info.duration_ms:.2f}ms")
                logger.error("-------")

            raise

    def get_task_info(self, name: str) -> Optional[TaskInfo]:
        """获取任务信息

        Args:
            name: 任务名称

        Returns:
            任务信息，如果不存在则返回 None
        """
        return self._tasks.get(name)

    def list_tasks(
        self,
        status: Optional[TaskStatus] = None
    ) -> List[TaskInfo]:
        """列出任务

        Args:
            status: 过滤状态，为 None 则返回所有任务

        Returns:
            任务信息列表
        """
        tasks = list(self._tasks.values())

        if status is not None:
            tasks = [t for t in tasks if t.status == status]

        return tasks

    def get_stats(self) -> Dict[str, Any]:
        """获取任务统计信息

        Returns:
            统计信息字典
        """
        total = len(self._tasks)
        by_status = {
            status.value: sum(1 for t in self._tasks.values() if t.status == status)
            for status in TaskStatus
        }

        failed_tasks = [t for t in self._tasks.values() if t.status == TaskStatus.FAILED]
        avg_duration = (
            sum(t.duration_ms or 0 for t in self._tasks.values() if t.duration_ms)
            / total
            if total > 0 else 0
        )

        return {
            "total_tasks": total,
            "by_status": by_status,
            "failed_count": len(failed_tasks),
            "avg_duration_ms": avg_duration,
        }

    async def cancel_task(self, name: str) -> bool:
        """取消任务

        Args:
            name: 任务名称

        Returns:
            是否成功取消
        """
        task_info = self._tasks.get(name)
        if not task_info or not task_info.task:
            logger.warning(f"任务不存在: {name}")
            return False

        if task_info.task.done():
            logger.warning(f"任务已完成，无法取消: {name}")
            return False

        task_info.task.cancel()
        logger.info(f"已请求取消任务: {name}")
        return True

    async def cancel_all_tasks(self) -> int:
        """取消所有运行中的任务

        Returns:
            取消的任务数量
        """
        running_tasks = [
            t for t in self._tasks.values()
            if t.status == TaskStatus.RUNNING and t.task and not t.task.done()
        ]

        for task_info in running_tasks:
            task_info.task.cancel()

        logger.info(f"已请求取消 {len(running_tasks)} 个运行中的任务")
        return len(running_tasks)

    def cleanup(self, max_age_seconds: int = 3600) -> int:
        """清理旧任务记录

        Args:
            max_age_seconds: 最大保留时长（秒）

        Returns:
            清理的任务数量
        """
        from datetime import timedelta

        cutoff = datetime.now() - timedelta(seconds=max_age_seconds)
        to_remove = [
            name for name, info in self._tasks.items()
            if info.completed_at and info.completed_at < cutoff
        ]

        for name in to_remove:
            del self._tasks[name]

        if to_remove:
            logger.debug(f"清理了 {len(to_remove)} 个旧任务记录")

        return len(to_remove)


# 全局任务包装器实例
_global_task_wrapper: Optional[TaskWrapper] = None


def get_task_wrapper() -> TaskWrapper:
    """获取全局任务包装器实例

    Returns:
        任务包装器实例
    """
    global _global_task_wrapper
    if _global_task_wrapper is None:
        _global_task_wrapper = TaskWrapper()
    return _global_task_wrapper


async def create_task(
    coro: Callable,
    name: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> asyncio.Task:
    """创建并包装任务（便捷函数）

    Args:
        coro: 协程函数
        name: 任务名称
        metadata: 任务元数据

    Returns:
        异步任务对象
    """
    wrapper = get_task_wrapper()
    return await wrapper.wrap_task(coro, name, metadata)


__all__ = [
    "TaskStatus",
    "TaskError",
    "TaskInfo",
    "TaskWrapper",
    "get_task_wrapper",
    "create_task",
]
