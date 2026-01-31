"""消息路由模块

提供平台消息到消息处理系统的统一入口、优先级队列和去重机制。
"""

import asyncio
import hashlib
import time
from typing import Dict, Any, Optional, Callable, List
from loguru import logger
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, IntEnum
import json


class MessagePriority(IntEnum):
    """消息优先级（数值越大优先级越高）"""

    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


class MessageStatus(Enum):
    """消息状态"""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    DROPPED = "dropped"


@dataclass
class Message:
    """消息模型"""

    message_id: str
    platform_id: str
    message_type: str
    content: Dict[str, Any]
    priority: MessagePriority = MessagePriority.NORMAL
    timestamp: datetime = field(default_factory=datetime.now)
    retry_count: int = 0
    max_retries: int = 3
    status: MessageStatus = MessageStatus.PENDING
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def unique_id(self) -> str:
        """获取消息唯一标识"""
        data = f"{self.platform_id}_{self.message_type}_{self.message_id}"
        return hashlib.sha256(data.encode()).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "message_id": self.message_id,
            "platform_id": self.platform_id,
            "message_type": self.message_type,
            "content": self.content,
            "priority": self.priority.value,
            "timestamp": self.timestamp.isoformat(),
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "status": self.status.value,
            "metadata": self.metadata,
            "unique_id": self.unique_id,
        }


class MessageRouter:
    """消息路由器

    提供以下功能：
    - 平台消息到消息处理系统的统一入口
    - 消息优先级队列（重要消息优先处理）
    - 消息去重和幂等性保证
    """

    def __init__(
        self,
        max_queue_size: int = 1000,
        dedup_window_seconds: int = 300,
        enable_dedup: bool = True,
    ):
        self.max_queue_size = max_queue_size
        self.dedup_window_seconds = dedup_window_seconds
        self.enable_dedup = enable_dedup

        self._queues: Dict[MessagePriority, asyncio.PriorityQueue] = {
            priority: asyncio.PriorityQueue() for priority in MessagePriority
        }

        self._processed_messages: Dict[str, datetime] = {}
        self._message_handlers: Dict[str, List[Callable]] = {}
        self._default_handlers: List[Callable] = []

        self._processing_task: Optional[asyncio.Task] = None
        self._running = False

        self._stats = {
            "total_received": 0,
            "total_processed": 0,
            "total_failed": 0,
            "total_dropped": 0,
            "total_deduplicated": 0,
            "queue_sizes": {p.value: 0 for p in MessagePriority},
        }

    async def start(self):
        """启动消息路由器"""
        if self._running:
            logger.warning("消息路由器已在运行")
            return

        self._running = True
        self._processing_task = asyncio.create_task(self._processing_loop())
        logger.info("消息路由器已启动")

    async def stop(self):
        """停止消息路由器"""
        if not self._running:
            return

        self._running = False

        if self._processing_task:
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                pass

        logger.info("消息路由器已停止")

    async def route_message(
        self,
        platform_id: str,
        message_type: str,
        content: Dict[str, Any],
        priority: MessagePriority = MessagePriority.NORMAL,
        **kwargs,
    ) -> bool:
        """路由消息到处理系统

        Args:
            platform_id: 平台ID
            message_type: 消息类型
            content: 消息内容
            priority: 消息优先级
            **kwargs: 其他参数

        Returns:
            是否路由成功
        """
        self._stats["total_received"] += 1

        message = Message(
            message_id=content.get("message_id", str(time.time())),
            platform_id=platform_id,
            message_type=message_type,
            content=content,
            priority=priority,
            metadata=kwargs,
        )

        # 去重检查
        if self.enable_dedup and await self._is_duplicate(message):
            self._stats["total_deduplicated"] += 1
            logger.debug(f"消息已去重: {message.unique_id}")
            return False

        # 检查队列大小
        queue_size = sum(q.qsize() for q in self._queues.values())
        if queue_size >= self.max_queue_size:
            self._stats["total_dropped"] += 1
            logger.warning("消息队列已满，丢弃消息")
            return False

        # 加入优先级队列
        try:
            queue = self._queues[priority]
            await queue.put((-priority.value, message.timestamp.timestamp(), message))
            self._stats["queue_sizes"][priority.value] = queue.qsize()
            logger.debug(
                f"消息已加入 {priority.value} 优先级队列: {platform_id}/{message_type}"
            )
            return True
        except Exception as e:
            logger.error(f"路由消息失败: {e}")
            self._stats["total_dropped"] += 1
            return False

    async def _is_duplicate(self, message: Message) -> bool:
        """检查是否为重复消息"""
        unique_id = message.unique_id

        if unique_id in self._processed_messages:
            # 检查是否在去重窗口内
            processed_time = self._processed_messages[unique_id]
            if datetime.now() - processed_time < timedelta(
                seconds=self.dedup_window_seconds
            ):
                return True

        # 记录已处理的消息
        self._processed_messages[unique_id] = datetime.now()

        # 清理过期的去重记录
        await self._cleanup_dedup_records()

        return False

    async def _cleanup_dedup_records(self):
        """清理过期的去重记录"""
        now = datetime.now()
        cutoff = now - timedelta(seconds=self.dedup_window_seconds)

        expired_ids = [
            msg_id
            for msg_id, processed_time in self._processed_messages.items()
            if processed_time < cutoff
        ]

        for msg_id in expired_ids:
            del self._processed_messages[msg_id]

    async def _processing_loop(self):
        """消息处理循环"""
        while self._running:
            try:
                message = await self._get_next_message()
                if message:
                    await self._process_message(message)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"消息处理循环出错: {e}")
                await asyncio.sleep(1)

    async def _get_next_message(self) -> Optional[Message]:
        """获取下一条待处理消息（优先级队列）"""
        for priority in sorted(MessagePriority, key=lambda p: p.value, reverse=True):
            queue = self._queues[priority]
            if not queue.empty():
                _, _, message = await queue.get()
                self._stats["queue_sizes"][priority.value] = queue.qsize()
                return message
        return None

    async def _process_message(self, message: Message):
        """处理单条消息"""
        message.status = MessageStatus.PROCESSING

        try:
            # 查找消息处理器
            handlers = self._message_handlers.get(
                message.message_type, self._default_handlers
            )

            if not handlers:
                logger.warning(f"未找到消息处理器: {message.message_type}")
                message.status = MessageStatus.FAILED
                self._stats["total_failed"] += 1
                return

            # 执行所有处理器
            success = True
            for handler in handlers:
                try:
                    result = await handler(message)
                    if not result:
                        success = False
                        logger.warning(f"消息处理器返回失败: {message.message_type}")
                except Exception as e:
                    logger.error(f"消息处理器执行失败: {message.message_type}: {e}")
                    success = False

            if success:
                message.status = MessageStatus.COMPLETED
                self._stats["total_processed"] += 1
                logger.debug(f"消息处理成功: {message.message_id}")
            else:
                # 重试机制
                if message.retry_count < message.max_retries:
                    message.retry_count += 1
                    message.status = MessageStatus.PENDING
                    await self._queues[message.priority].put(
                        (
                            -message.priority.value,
                            message.timestamp.timestamp(),
                            message,
                        )
                    )
                    logger.info(
                        f"消息处理失败，将重试 ({message.retry_count}/{message.max_retries}): {message.message_id}"
                    )
                else:
                    message.status = MessageStatus.FAILED
                    self._stats["total_failed"] += 1
                    logger.error(
                        f"消息处理失败，已达最大重试次数: {message.message_id}"
                    )

        except Exception as e:
            logger.error(f"处理消息时发生异常: {e}")
            message.status = MessageStatus.FAILED
            self._stats["total_failed"] += 1

    def register_handler(
        self,
        message_type: str,
        handler: Callable[[Message], bool],
    ):
        """注册消息处理器

        Args:
            message_type: 消息类型
            handler: 处理函数，返回是否成功
        """
        if message_type not in self._message_handlers:
            self._message_handlers[message_type] = []
        self._message_handlers[message_type].append(handler)
        logger.info(f"已注册消息处理器: {message_type}")

    def register_default_handler(
        self,
        handler: Callable[[Message], bool],
    ):
        """注册默认消息处理器（处理未注册类型的消息）"""
        self._default_handlers.append(handler)
        logger.info("已注册默认消息处理器")

    def unregister_handler(
        self,
        message_type: str,
        handler: Callable[[Message], bool],
    ):
        """取消注册消息处理器"""
        if message_type in self._message_handlers:
            if handler in self._message_handlers[message_type]:
                self._message_handlers[message_type].remove(handler)
                logger.info(f"已取消注册消息处理器: {message_type}")

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self._stats,
            "running": self._running,
            "queue_size_total": sum(q.qsize() for q in self._queues.values()),
            "dedup_records_count": len(self._processed_messages),
            "registered_handlers": {
                msg_type: len(handlers)
                for msg_type, handlers in self._message_handlers.items()
            },
        }

    async def clear_queue(self, priority: MessagePriority | None = None):
        """清空队列

        Args:
            priority: 要清空的优先级，None表示清空所有
        """
        if priority:
            queue = self._queues[priority]
            while not queue.empty():
                queue.get_nowait()
            self._stats["queue_sizes"][priority.value] = 0
        else:
            for p, queue in self._queues.items():
                while not queue.empty():
                    queue.get_nowait()
                self._stats["queue_sizes"][p.value] = 0
        logger.info("消息队列已清空")
