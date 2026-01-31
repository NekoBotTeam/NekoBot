"""消息缓冲模块

提供平台离线时的消息暂存机制、平台恢复后的消息回放、缓冲区大小和过期策略。
"""

import asyncio
import json
from typing import Dict, Any, Optional, List, Callable
from loguru import logger
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from collections import deque
import os


class BufferPolicy(Enum):
    """缓冲策略"""

    FIFO = "fifo"
    LIFO = "lifo"
    PRIORITY = "priority"


class BufferOverflowStrategy(Enum):
    """缓冲区溢出策略"""

    DROP_OLDEST = "drop_oldest"
    DROP_NEWEST = "drop_newest"
    DROP_LOW_PRIORITY = "drop_low_priority"
    COMPRESS = "compress"


@dataclass
class BufferedMessage:
    """缓冲消息"""

    message_id: str
    platform_id: str
    message_type: str
    content: Dict[str, Any]
    priority: int = 1
    timestamp: datetime = field(default_factory=datetime.now)
    ttl: Optional[int] = None  # Time to live in seconds
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        """是否已过期"""
        if self.ttl is None:
            return False
        return (datetime.now() - self.timestamp).total_seconds() > self.ttl


class MessageBuffer:
    """消息缓冲器

    提供以下功能：
    - 平台离线时的消息暂存机制
    - 平台恢复后的消息回放
    - 缓冲区大小和过期策略
    """

    def __init__(
        self,
        max_size: int = 1000,
        buffer_policy: BufferPolicy = BufferPolicy.FIFO,
        overflow_strategy: BufferOverflowStrategy = BufferOverflowStrategy.DROP_OLDEST,
        enable_persistence: bool = False,
        persistence_path: str = "data/message_buffer.json",
        default_ttl: Optional[int] = None,
    ):
        self.max_size = max_size
        self.buffer_policy = buffer_policy
        self.overflow_strategy = overflow_strategy
        self.enable_persistence = enable_persistence
        self.persistence_path = persistence_path
        self.default_ttl = default_ttl

        self._buffer: deque[BufferedMessage] = deque(maxlen=max_size)
        self._platform_status: Dict[str, bool] = {}
        self._replay_handlers: List[Callable] = []
        self._overflow_callbacks: List[Callable] = []

        self._stats = {
            "total_buffered": 0,
            "total_replayed": 0,
            "total_dropped": 0,
            "total_expired": 0,
            "current_size": 0,
            "platform_buffers": {},
        }

        if self.enable_persistence:
            self._load_from_disk()

    async def add_message(
        self,
        platform_id: str,
        message_type: str,
        content: Dict[str, Any],
        priority: int = 1,
        ttl: Optional[int] = None,
        **kwargs,
    ) -> bool:
        """添加消息到缓冲区

        Args:
            platform_id: 平台ID
            message_type: 消息类型
            content: 消息内容
            priority: 优先级
            ttl: 过期时间（秒）
            **kwargs: 其他元数据

        Returns:
            是否添加成功
        """
        message = BufferedMessage(
            message_id=content.get("message_id", ""),
            platform_id=platform_id,
            message_type=message_type,
            content=content,
            priority=priority,
            ttl=ttl or self.default_ttl,
            metadata=kwargs,
        )

        # 检查是否需要缓冲（平台离线时）
        if not self._platform_status.get(platform_id, True):
            return await self._buffer_message(message)

        return True

    async def _buffer_message(self, message: BufferedMessage) -> bool:
        """缓冲消息"""
        # 清理过期消息
        await self._cleanup_expired_messages()

        # 检查缓冲区是否已满
        if len(self._buffer) >= self.max_size:
            dropped = await self._handle_overflow()
            if dropped:
                logger.warning(f"缓冲区已满，丢弃了 {dropped} 条消息")
                self._stats["total_dropped"] += dropped

        # 根据策略添加消息
        if self.buffer_policy == BufferPolicy.FIFO:
            self._buffer.append(message)
        elif self.buffer_policy == BufferPolicy.LIFO:
            self._buffer.appendleft(message)
        elif self.buffer_policy == BufferPolicy.PRIORITY:
            self._buffer.append(message)
            if len(self._buffer) > 1:
                self._buffer = deque(
                    sorted(self._buffer, key=lambda m: m.priority, reverse=True),
                    maxlen=self.max_size,
                )

        self._stats["total_buffered"] += 1
        self._stats["current_size"] = len(self._buffer)

        # 更新平台缓冲统计
        if message.platform_id not in self._stats["platform_buffers"]:
            self._stats["platform_buffers"][message.platform_id] = 0
        self._stats["platform_buffers"][message.platform_id] += 1

        # 持久化
        if self.enable_persistence:
            await self._save_to_disk()

        logger.debug(
            f"消息已缓冲: {message.platform_id}/{message.message_type} "
            f"(当前缓冲区大小: {len(self._buffer)})"
        )
        return True

    async def _handle_overflow(self) -> int:
        """处理缓冲区溢出"""
        dropped_count = 0

        if self.overflow_strategy == BufferOverflowStrategy.DROP_OLDEST:
            if self._buffer:
                self._buffer.popleft()
                dropped_count = 1
        elif self.overflow_strategy == BufferOverflowStrategy.DROP_NEWEST:
            if self._buffer:
                self._buffer.pop()
                dropped_count = 1
        elif self.overflow_strategy == BufferOverflowStrategy.DROP_LOW_PRIORITY:
            if self._buffer:
                min_priority = min(m.priority for m in self._buffer)
                low_priority_msgs = [
                    i for i, m in enumerate(self._buffer) if m.priority == min_priority
                ]
                for idx in reversed(low_priority_msgs):
                    del self._buffer[idx]
                    dropped_count += 1
        elif self.overflow_strategy == BufferOverflowStrategy.COMPRESS:
            # 压缩消息（简化内容）
            for msg in self._buffer:
                if "raw_message" in msg.content:
                    msg.content["raw_message"] = (
                        msg.content["raw_message"][:100] + "..."
                    )
            dropped_count = 0

        # 触发溢出回调
        for callback in self._overflow_callbacks:
            try:
                await callback(dropped_count)
            except Exception as e:
                logger.error(f"溢出回调执行失败: {e}")

        return dropped_count

    async def _cleanup_expired_messages(self) -> int:
        """清理过期消息"""
        expired_count = 0
        original_size = len(self._buffer)

        self._buffer = deque(
            [m for m in self._buffer if not m.is_expired],
            maxlen=self.max_size,
        )

        expired_count = original_size - len(self._buffer)
        if expired_count > 0:
            self._stats["total_expired"] += expired_count
            logger.debug(f"清理了 {expired_count} 条过期消息")

        return expired_count

    async def replay_messages(
        self,
        platform_id: str,
        max_count: Optional[int] = None,
    ) -> List[BufferedMessage]:
        """回放平台的消息

        Args:
            platform_id: 平台ID
            max_count: 最大回放数量

        Returns:
            回放的消息列表
        """
        # 标记平台为在线
        self._platform_status[platform_id] = True

        replayed = []
        remaining = deque()

        for message in self._buffer:
            if message.platform_id == platform_id and not message.is_expired:
                if max_count is None or len(replayed) < max_count:
                    replayed.append(message)
                    self._stats["total_replayed"] += 1
                else:
                    remaining.append(message)
            else:
                remaining.append(message)

        # 更新缓冲区
        self._buffer = remaining
        self._stats["current_size"] = len(self._buffer)

        # 触发回放处理器
        for message in replayed:
            for handler in self._replay_handlers:
                try:
                    await handler(message)
                except Exception as e:
                    logger.error(f"消息回放处理器执行失败: {e}")

        logger.info(f"平台 {platform_id} 回放了 {len(replayed)} 条消息")

        # 持久化
        if self.enable_persistence:
            await self._save_to_disk()

        return replayed

    def mark_platform_offline(self, platform_id: str):
        """标记平台为离线"""
        self._platform_status[platform_id] = False
        logger.info(f"平台 {platform_id} 已标记为离线，开始缓冲消息")

    def mark_platform_online(self, platform_id: str):
        """标记平台为在线"""
        self._platform_status[platform_id] = True
        logger.info(f"平台 {platform_id} 已标记为在线")

    def is_platform_offline(self, platform_id: str) -> bool:
        """检查平台是否离线"""
        return not self._platform_status.get(platform_id, True)

    def register_replay_handler(self, handler: Callable):
        """注册消息回放处理器"""
        self._replay_handlers.append(handler)
        logger.info("已注册消息回放处理器")

    def register_overflow_callback(self, callback: Callable):
        """注册溢出回调"""
        self._overflow_callbacks.append(callback)
        logger.info("已注册缓冲区溢出回调")

    async def clear_buffer(self, platform_id: Optional[str] = None):
        """清空缓冲区

        Args:
            platform_id: 平台ID，为None时清空所有
        """
        if platform_id:
            self._buffer = deque(
                [m for m in self._buffer if m.platform_id != platform_id],
                maxlen=self.max_size,
            )
            logger.info(f"已清空平台 {platform_id} 的缓冲区")
        else:
            self._buffer.clear()
            logger.info("已清空所有缓冲区")

        self._stats["current_size"] = len(self._buffer)

        # 持久化
        if self.enable_persistence:
            await self._save_to_disk()

    def get_buffer_stats(self) -> Dict[str, Any]:
        """获取缓冲区统计信息"""
        return {
            **self._stats,
            "max_size": self.max_size,
            "buffer_policy": self.buffer_policy.value,
            "overflow_strategy": self.overflow_strategy.value,
            "enable_persistence": self.enable_persistence,
            "persistence_path": self.persistence_path,
            "default_ttl": self.default_ttl,
        }

    def get_buffered_messages(
        self, platform_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """获取缓冲的消息

        Args:
            platform_id: 平台ID，为None时返回所有

        Returns:
            消息列表
        """
        messages = []
        for msg in self._buffer:
            if platform_id is None or msg.platform_id == platform_id:
                messages.append(
                    {
                        "message_id": msg.message_id,
                        "platform_id": msg.platform_id,
                        "message_type": msg.message_type,
                        "priority": msg.priority,
                        "timestamp": msg.timestamp.isoformat(),
                        "ttl": msg.ttl,
                        "is_expired": msg.is_expired,
                        "metadata": msg.metadata,
                    }
                )
        return messages

    async def _save_to_disk(self):
        """保存到磁盘"""
        try:
            os.makedirs(os.path.dirname(self.persistence_path), exist_ok=True)

            data = [
                {
                    "message_id": msg.message_id,
                    "platform_id": msg.platform_id,
                    "message_type": msg.message_type,
                    "content": msg.content,
                    "priority": msg.priority,
                    "timestamp": msg.timestamp.isoformat(),
                    "ttl": msg.ttl,
                    "metadata": msg.metadata,
                }
                for msg in self._buffer
            ]

            with open(self.persistence_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            logger.debug(f"消息缓冲区已保存到 {self.persistence_path}")
        except Exception as e:
            logger.error(f"保存消息缓冲区到磁盘失败: {e}")

    def _load_from_disk(self):
        """从磁盘加载"""
        try:
            if not os.path.exists(self.persistence_path):
                return

            with open(self.persistence_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            for item in data:
                message = BufferedMessage(
                    message_id=item["message_id"],
                    platform_id=item["platform_id"],
                    message_type=item["message_type"],
                    content=item["content"],
                    priority=item.get("priority", 1),
                    timestamp=datetime.fromisoformat(item["timestamp"]),
                    ttl=item.get("ttl"),
                    metadata=item.get("metadata", {}),
                )

                if not message.is_expired:
                    self._buffer.append(message)

            logger.info(f"从磁盘加载了 {len(self._buffer)} 条缓冲消息")
        except Exception as e:
            logger.error(f"从磁盘加载消息缓冲区失败: {e}")
