"""日志代理系统

提供发布-订阅模式的日志系统，支持多个订阅者
参考 AstrBot 框架的 LogBroker 实现
"""

import asyncio
from collections import deque
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class LogLevel(str, Enum):
    """日志级别"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass
class LogEntry:
    """日志条目"""
    level: LogLevel
    message: str
    logger_name: str
    timestamp: datetime = field(default_factory=datetime.now)
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    function_name: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "level": self.level.value,
            "message": self.message,
            "logger_name": self.logger_name,
            "timestamp": self.timestamp.isoformat(),
            "file_path": self.file_path,
            "line_number": self.line_number,
            "function_name": self.function_name,
            "extra": self.extra,
        }


class LogQueue(asyncio.Queue):
    """日志队列，带大小限制"""

    def __init__(self, maxsize: int = 1000):
        super().__init__(maxsize=maxsize)

    def put_nowait(self, item: LogEntry) -> None:
        """非阻塞放入日志

        Args:
            item: 日志条目
        """
        try:
            super().put_nowait(item)
        except asyncio.QueueFull:
            # 队列满时，移除最旧的日志
            try:
                self.get_nowait()
                self.put_nowait(item)
            except asyncio.QueueEmpty:
                pass


class LogBroker:
    """日志代理类

    管理日志发布和订阅，支持多个订阅者
    """

    def __init__(self, cache_size: int = 1000):
        """初始化日志代理

        Args:
            cache_size: 日志缓存大小
        """
        # 日志缓存（环形缓冲区）
        self.log_cache: deque[LogEntry] = deque(maxlen=cache_size)

        # 订阅者列表
        self._subscribers: List[LogQueue] = []
        self._subscriber_lock = asyncio.Lock()

        # 日志级别过滤
        self._min_level: LogLevel = LogLevel.DEBUG

        # 统计信息
        self._total_published = 0
        self._total_by_level: Dict[LogLevel, int] = dict.fromkeys(LogLevel, 0)

    async def subscribe(self, queue_size: int = 1100) -> LogQueue:
        """订阅日志

        Args:
            queue_size: 订阅者队列大小（略大于缓存大小）

        Returns:
            日志队列
        """
        async with self._subscriber_lock:
            queue = LogQueue(maxsize=queue_size)

            # 发送缓存的日志给新订阅者
            for log_entry in self.log_cache:
                try:
                    queue.put_nowait(log_entry)
                except asyncio.QueueFull:
                    break

            self._subscribers.append(queue)
            return queue

    async def unsubscribe(self, queue: LogQueue) -> bool:
        """取消订阅

        Args:
            queue: 日志队列

        Returns:
            是否成功取消
        """
        async with self._subscriber_lock:
            if queue in self._subscribers:
                self._subscribers.remove(queue)
                return True
            return False

    async def publish(self, log_entry: LogEntry) -> None:
        """发布日志

        Args:
            log_entry: 日志条目
        """
        # 添加到缓存
        self.log_cache.append(log_entry)

        # 更新统计
        self._total_published += 1
        self._total_by_level[log_entry.level] += 1

        # 分发给所有订阅者
        async with self._subscriber_lock:
            for queue in self._subscribers[:]:  # 复制列表，允许在遍历中修改
                try:
                    queue.put_nowait(log_entry)
                except asyncio.QueueFull:
                    # 订阅者队列满，移除该订阅者
                    self._subscribers.remove(queue)

    def set_min_level(self, level: LogLevel) -> None:
        """设置最小日志级别

        Args:
            level: 最小日志级别
        """
        self._min_level = level

    def should_log(self, level: LogLevel) -> bool:
        """判断是否应该记录日志

        Args:
            level: 日志级别

        Returns:
            是否应该记录
        """
        level_order = [LogLevel.DEBUG, LogLevel.INFO, LogLevel.WARNING, LogLevel.ERROR, LogLevel.CRITICAL]
        return level_order.index(level) >= level_order.index(self._min_level)

    def get_cache(self, limit: Optional[int] = None) -> List[LogEntry]:
        """获取日志缓存

        Args:
            limit: 返回的最大数量

        Returns:
            日志条目列表
        """
        cache_list = list(self.log_cache)
        if limit is not None:
            return cache_list[-limit:]
        return cache_list

    def clear_cache(self) -> None:
        """清空日志缓存"""
        self.log_cache.clear()

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息

        Returns:
            统计信息字典
        """
        return {
            "total_published": self._total_published,
            "by_level": {
                level.value: count
                for level, count in self._total_by_level.items()
            },
            "cache_size": len(self.log_cache),
            "subscriber_count": len(self._subscribers),
            "min_level": self._min_level.value,
        }

    async def close(self) -> None:
        """关闭日志代理，清理资源"""
        async with self._subscriber_lock:
            self._subscribers.clear()
        self.log_cache.clear()


class LogHandler:
    """日志处理器

    集成到 loguru，将日志发布到 LogBroker
    """

    def __init__(self, broker: LogBroker):
        """初始化日志处理器

        Args:
            broker: 日志代理
        """
        self.broker = broker

    def write(self, message: str) -> None:
        """写入日志（由 loguru 调用）

        Args:
            message: 日志消息
        """
        # 解析 loguru 格式的日志
        # loguru 格式: [时间] [级别] [文件名:行号]: 消息
        try:
            log_entry = self._parse_loguru_message(message)
            if self.broker.should_log(log_entry.level):
                # 注意：这里需要异步发布，但 loguru 的 handler 是同步的
                # 我们使用 asyncio.create_task 在后台发布
                asyncio.create_task(self.broker.publish(log_entry))
        except Exception:
            # 避免日志记录出错导致无限循环
            pass

    def _parse_loguru_message(self, message: str) -> LogEntry:
        """解析 loguru 日志消息

        Args:
            message: loguru 格式的日志消息

        Returns:
            日志条目
        """
        # 简单解析，实际可以根据 loguru 格式进行更精确的解析
        level = LogLevel.INFO
        logger_name = "nekobot"

        # 检测日志级别
        for log_level in LogLevel:
            if f"[{log_level.value}]" in message:
                level = log_level
                break

        # 提取消息内容
        # 假设格式: [时间] [级别] 消息
        parts = message.split("]", 2)
        if len(parts) >= 3:
            log_message = parts[2].strip()
        else:
            log_message = message

        return LogEntry(
            level=level,
            message=log_message,
            logger_name=logger_name,
        )

    def flush(self) -> None:
        """刷新日志（由 loguru 调用）"""
        pass


# 全局日志代理实例
_global_log_broker: Optional[LogBroker] = None


def get_log_broker() -> LogBroker:
    """获取全局日志代理实例

    Returns:
        日志代理实例
    """
    global _global_log_broker
    if _global_log_broker is None:
        _global_log_broker = LogBroker()
    return _global_log_broker


def setup_log_broker_integration(cache_size: int = 1000) -> LogHandler:
    """设置日志代理集成

    在 loguru 中添加日志处理器

    Args:
        cache_size: 日志缓存大小

    Returns:
        日志处理器
    """
    from loguru import logger as loguru_logger

    broker = get_log_broker()
    handler = LogHandler(broker)

    # 添加到 loguru
    # 注意：这里使用简单的 add 方式，实际可能需要更精细的配置
    loguru_logger.add(
        handler,
        format="{message}",  # 简单格式，因为我们会重新解析
        level="DEBUG",
    )

    return handler


__all__ = [
    "LogLevel",
    "LogEntry",
    "LogQueue",
    "LogBroker",
    "LogHandler",
    "get_log_broker",
    "setup_log_broker_integration",
]
