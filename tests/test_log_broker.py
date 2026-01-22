"""日志代理单元测试

测试 P1: 发布-订阅日志模式
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import Mock, AsyncMock

from packages.core.log_broker import (
    LogBroker,
    LogEntry,
    LogLevel,
    LogQueue,
    get_log_broker,
)


class TestLogLevel:
    """测试日志级别枚举"""

    def test_level_values(self):
        """测试级别值"""
        assert LogLevel.DEBUG.value == "DEBUG"
        assert LogLevel.INFO.value == "INFO"
        assert LogLevel.WARNING.value == "WARNING"
        assert LogLevel.ERROR.value == "ERROR"
        assert LogLevel.CRITICAL.value == "CRITICAL"


class TestLogEntry:
    """测试日志条目数据类"""

    def test_creation(self):
        """测试创建日志条目"""
        entry = LogEntry(
            level=LogLevel.INFO,
            message="Test message",
            logger_name="test_module"
        )

        assert entry.level == LogLevel.INFO
        assert entry.message == "Test message"
        assert entry.logger_name == "test_module"
        assert isinstance(entry.timestamp, datetime)

    def test_with_extra_data(self):
        """测试带额外数据的日志条目"""
        entry = LogEntry(
            level=LogLevel.DEBUG,
            message="Debug info",
            logger_name="test_logger",
            extra={"function": "test_func", "line": 42}
        )

        assert entry.extra["function"] == "test_func"
        assert entry.extra["line"] == 42

    def test_to_dict(self):
        """测试转换为字典"""
        entry = LogEntry(
            level=LogLevel.INFO,
            message="Test",
            logger_name="test"
        )

        d = entry.to_dict()

        assert d["level"] == "INFO"
        assert d["message"] == "Test"
        assert d["logger_name"] == "test"
        assert "timestamp" in d


class TestLogQueue:
    """测试日志队列"""

    @pytest.mark.asyncio
    async def test_put_and_get(self):
        """测试放入和获取日志"""
        queue = LogQueue(maxsize=10)

        entry = LogEntry(LogLevel.INFO, "Test", "test")

        queue.put_nowait(entry)

        assert queue.qsize() == 1

        retrieved = await queue.get()

        assert retrieved is entry


class TestLogBroker:
    """测试日志代理"""

    @pytest.fixture
    def broker(self):
        """创建日志代理实例"""
        return LogBroker(cache_size=10)

    @pytest.mark.asyncio
    async def test_publish_log(self, broker):
        """测试发布日志"""
        entry = LogEntry(
            level=LogLevel.INFO,
            message="Test message",
            logger_name="test"
        )

        await broker.publish(entry)

        assert len(broker.log_cache) == 1
        assert broker.log_cache[0] == entry

    @pytest.mark.asyncio
    async def test_subscribe_and_receive(self, broker):
        """测试订阅和接收日志"""
        queue = await broker.subscribe()

        entry = LogEntry(
            level=LogLevel.INFO,
            message="Hello, subscriber!",
            logger_name="test"
        )

        await broker.publish(entry)

        # 接收日志
        received_entry = await asyncio.wait_for(queue.get(), timeout=0.1)

        assert received_entry.message == "Hello, subscriber!"
        assert received_entry.level == LogLevel.INFO

    @pytest.mark.asyncio
    async def test_multiple_subscribers(self, broker):
        """测试多个订阅者"""
        queue1 = await broker.subscribe()
        queue2 = await broker.subscribe()

        entry = LogEntry(
            level=LogLevel.WARNING,
            message="Warning message",
            logger_name="test"
        )

        await broker.publish(entry)

        # 两个订阅者都应该收到
        received1 = await asyncio.wait_for(queue1.get(), timeout=0.1)
        received2 = await asyncio.wait_for(queue2.get(), timeout=0.1)

        assert received1.message == "Warning message"
        assert received2.message == "Warning message"

    @pytest.mark.asyncio
    async def test_unsubscribe(self, broker):
        """测试取消订阅"""
        queue = await broker.subscribe()

        # 取消订阅
        success = await broker.unsubscribe(queue)

        assert success is True

        entry = LogEntry(
            level=LogLevel.INFO,
            message="Test",
            logger_name="test"
        )

        await broker.publish(entry)

        # 尝试接收应该超时
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(queue.get(), timeout=0.05)

    @pytest.mark.asyncio
    async def test_cache_size_limit(self, broker):
        """测试缓存大小限制"""
        # broker 的 cache_size 是 10
        for i in range(15):
            entry = LogEntry(
                level=LogLevel.INFO,
                message=f"Message {i}",
                logger_name="test"
            )
            await broker.publish(entry)

        # 缓存应该只保留最后 10 条
        assert len(broker.log_cache) == 10

    @pytest.mark.asyncio
    async def test_get_cache(self, broker):
        """测试获取缓存"""
        for i in range(5):
            entry = LogEntry(
                level=LogLevel.INFO,
                message=f"Log {i}",
                logger_name="test"
            )
            await broker.publish(entry)

        recent = broker.get_cache(limit=3)

        assert len(recent) == 3

    @pytest.mark.asyncio
    async def test_clear_cache(self, broker):
        """测试清空缓存"""
        for i in range(5):
            entry = LogEntry(
                level=LogLevel.INFO,
                message=f"Msg {i}",
                logger_name="test"
            )
            await broker.publish(entry)

        assert len(broker.log_cache) == 5

        broker.clear_cache()

        assert len(broker.log_cache) == 0

    def test_get_stats(self, broker):
        """测试获取统计信息"""
        stats = broker.get_stats()

        assert "total_published" in stats
        assert "cache_size" in stats
        assert "subscriber_count" in stats
        assert "by_level" in stats

    @pytest.mark.asyncio
    async def test_stats_update(self, broker):
        """测试统计信息更新"""
        await broker.publish(LogEntry(LogLevel.INFO, "Info", "test"))
        await broker.publish(LogEntry(LogLevel.ERROR, "Error", "test"))

        stats = broker.get_stats()

        assert stats["total_published"] == 2
        assert stats["by_level"]["INFO"] == 1
        assert stats["by_level"]["ERROR"] == 1

    @pytest.mark.asyncio
    async def test_set_min_level(self, broker):
        """测试设置最小日志级别"""
        broker.set_min_level(LogLevel.WARNING)

        # DEBUG 和 INFO 应该被过滤
        assert broker.should_log(LogLevel.DEBUG) is False
        assert broker.should_log(LogLevel.INFO) is False
        assert broker.should_log(LogLevel.WARNING) is True
        assert broker.should_log(LogLevel.ERROR) is True

    @pytest.mark.asyncio
    async def test_subscribe_with_cache(self, broker):
        """测试订阅时接收缓存日志"""
        # 先发布一些日志
        for i in range(3):
            await broker.publish(LogEntry(LogLevel.INFO, f"Msg {i}", "test"))

        # 新订阅者应该收到缓存的日志
        queue = await broker.subscribe()

        # 应该能收到缓存的 3 条日志
        received = []
        for _ in range(3):
            try:
                entry = await asyncio.wait_for(queue.get(), timeout=0.1)
                received.append(entry)
            except asyncio.TimeoutError:
                break

        assert len(received) == 3

    @pytest.mark.asyncio
    async def test_close(self, broker):
        """测试关闭日志代理"""
        queue = await broker.subscribe()

        await broker.close()

        # 订阅者应该被清空
        stats = broker.get_stats()
        assert stats["subscriber_count"] == 0

        # 缓存应该被清空
        assert len(broker.log_cache) == 0


class TestConvenienceFunctions:
    """测试便捷函数"""

    def test_get_log_broker_singleton(self):
        """测试获取单例日志代理"""
        broker1 = get_log_broker()
        broker2 = get_log_broker()

        assert broker1 is broker2


class TestLogBrokerIntegration:
    """集成测试"""

    @pytest.mark.asyncio
    async def test_concurrent_logging(self):
        """测试并发日志记录"""
        broker = LogBroker(cache_size=1000)
        queue = await broker.subscribe()

        # 并发发布 100 条日志
        tasks = []
        for i in range(100):
            entry = LogEntry(
                LogLevel.INFO,
                f"Concurrent message {i}",
                "test"
            )
            tasks.append(broker.publish(entry))

        await asyncio.gather(*tasks)

        # 验证所有日志都被记录
        stats = broker.get_stats()
        assert stats["total_published"] == 100

    @pytest.mark.asyncio
    async def test_full_queue_handling(self):
        """测试队列满时的处理"""
        broker = LogBroker(cache_size=10)
        queue = await broker.subscribe(queue_size=5)

        # 发布超过队列大小的日志
        for i in range(10):
            await broker.publish(LogEntry(LogLevel.INFO, f"Msg {i}", "test"))

        # 队列应该自动丢弃最旧的日志
        assert queue.qsize() <= 5

    @pytest.mark.asyncio
    async def test_log_entry_with_file_info(self):
        """测试带文件信息的日志条目"""
        entry = LogEntry(
            level=LogLevel.ERROR,
            message="Error occurred",
            logger_name="test",
            file_path="/path/to/file.py",
            line_number=42,
            function_name="test_function"
        )

        assert entry.file_path == "/path/to/file.py"
        assert entry.line_number == 42
        assert entry.function_name == "test_function"

        d = entry.to_dict()
        assert d["file_path"] == "/path/to/file.py"
        assert d["line_number"] == 42
        assert d["function_name"] == "test_function"
