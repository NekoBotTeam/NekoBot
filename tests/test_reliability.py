"""重试和熔断机制单元测试

测试重试和熔断机制的功能
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from packages.provider.reliability import (
    CircuitBreakerState,
    RetryConfig,
    CircuitBreakerConfig,
    CallResult,
    RetryStrategy,
    CircuitBreaker,
    with_retry,
    with_circuit_breaker,
    RetryWithCircuitBreaker,
)


class TestRetryConfig:
    """重试配置测试"""

    def test_default_config(self):
        """测试默认配置"""
        config = RetryConfig()
        assert config.max_attempts == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 60.0
        assert config.exponential_base == 2.0
        assert config.jitter is True

    def test_custom_config(self):
        """测试自定义配置"""
        config = RetryConfig(
            max_attempts=5,
            base_delay=2.0,
            max_delay=120.0,
            jitter=False,
        )
        assert config.max_attempts == 5
        assert config.base_delay == 2.0


class TestCircuitBreakerConfig:
    """熔断器配置测试"""

    def test_default_config(self):
        """测试默认配置"""
        config = CircuitBreakerConfig()
        assert config.failure_threshold == 5
        assert config.success_threshold == 2
        assert config.timeout == 60.0

    def test_custom_config(self):
        """测试自定义配置"""
        config = CircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=1,
            timeout=30.0,
        )
        assert config.failure_threshold == 3


class TestRetryStrategy:
    """重试策略测试"""

    def test_calculate_delay(self):
        """测试计算延迟"""
        config = RetryConfig(base_delay=1.0, exponential_base=2.0, jitter=False)

        # 第 0 次: 1.0 * 2^0 = 1.0
        assert RetryStrategy.calculate_delay(0, config) == 1.0
        # 第 1 次: 1.0 * 2^1 = 2.0
        assert RetryStrategy.calculate_delay(1, config) == 2.0
        # 第 2 次: 1.0 * 2^2 = 4.0
        assert RetryStrategy.calculate_delay(2, config) == 4.0

    def test_max_delay_limit(self):
        """测试最大延迟限制"""
        config = RetryConfig(base_delay=10.0, exponential_base=3.0, max_delay=50.0, jitter=False)

        # 应该被限制在 max_delay
        delay = RetryStrategy.calculate_delay(3, config)
        assert delay <= 50.0

    def test_jitter(self):
        """测试随机抖动"""
        config = RetryConfig(base_delay=1.0, jitter=True)

        delays = [RetryStrategy.calculate_delay(0, config) for _ in range(10)]

        # 应该有一些变化
        assert len(set(delays)) > 1

    def test_should_retry(self):
        """测试是否应该重试"""
        config = RetryConfig(max_attempts=3)

        # 可重试的异常
        assert RetryStrategy.should_retry(ConnectionError(), 0, config) is True
        assert RetryStrategy.should_retry(TimeoutError(), 1, config) is True

        # 不可重试的异常
        assert RetryStrategy.should_retry(ValueError("test"), 0, config) is False
        assert RetryStrategy.should_retry(RuntimeError("test"), 0, config) is False

        # 达到最大重试次数
        assert RetryStrategy.should_retry(ConnectionError(), 3, config) is False


class TestCircuitBreaker:
    """熔断器测试"""

    @pytest.fixture
    def circuit_breaker(self):
        return CircuitBreaker(CircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=2,
            timeout=1.0,
        ))

    @pytest.mark.asyncio
    async def test_initial_state(self, circuit_breaker):
        """测试初始状态"""
        assert circuit_breaker.get_state() == CircuitBreakerState.CLOSED

    @pytest.mark.asyncio
    async def test_successful_call(self, circuit_breaker):
        """测试成功调用"""
        async def success_func():
            return "success"

        result = await circuit_breaker.call(success_func)
        assert result == "success"

        # 状态应该仍然是关闭的
        assert circuit_breaker.get_state() == CircuitBreakerState.CLOSED

        stats = circuit_breaker.get_stats()
        assert stats["failure_count"] == 0

    @pytest.mark.asyncio
    async def test_failure_opens_circuit(self, circuit_breaker):
        """测试失败导致熔断器打开"""
        async def fail_func():
            raise ConnectionError("Connection failed")

        # 连续失败直到达到阈值
        for _ in range(3):
            try:
                await circuit_breaker.call(fail_func)
            except ConnectionError:
                pass

        # 熔断器应该打开
        assert circuit_breaker.get_state() == CircuitBreakerState.OPEN

    @pytest.mark.asyncio
    async def test_open_circuit_rejects_calls(self, circuit_breaker):
        """测试打开的熔断器拒绝调用"""
        # 先让熔断器打开
        async def fail_func():
            raise ConnectionError()

        for _ in range(3):
            try:
                await circuit_breaker.call(fail_func)
            except ConnectionError:
                pass

        assert circuit_breaker.get_state() == CircuitBreakerState.OPEN

        # 现在应该拒绝新调用
        async def success_func():
            return "success"

        with pytest.raises(Exception, match="熔断器已打开"):
            await circuit_breaker.call(success_func)

    @pytest.mark.asyncio
    async def test_half_open_state(self, circuit_breaker):
        """测试半开状态"""
        # 让熔断器打开
        async def fail_func():
            raise ConnectionError()

        for _ in range(3):
            try:
                await circuit_breaker.call(fail_func)
            except ConnectionError:
                pass

        assert circuit_breaker.get_state() == CircuitBreakerState.OPEN

        # 等待超时
        await asyncio.sleep(1.1)

        # 尝试调用，应该进入半开状态
        async def success_func():
            return "success"

        result = await circuit_breaker.call(success_func)
        assert result == "success"
        assert circuit_breaker.get_state() == CircuitBreakerState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_recovery_to_closed(self, circuit_breaker):
        """测试恢复到关闭状态"""
        # 让熔断器打开
        async def fail_func():
            raise ConnectionError()

        for _ in range(3):
            try:
                await circuit_breaker.call(fail_func)
            except ConnectionError:
                pass

        # 等待超时
        await asyncio.sleep(1.1)

        # 连续成功调用
        async def success_func():
            return "success"

        await circuit_breaker.call(success_func)
        await circuit_breaker.call(success_func)

        # 应该恢复到关闭状态
        assert circuit_breaker.get_state() == CircuitBreakerState.CLOSED

    @pytest.mark.asyncio
    async def test_get_stats(self, circuit_breaker):
        """测试获取统计信息"""
        async def fail_func():
            raise ConnectionError()

        # 记录一些失败
        for _ in range(2):
            try:
                await circuit_breaker.call(fail_func)
            except ConnectionError:
                pass

        stats = circuit_breaker.get_stats()
        assert stats["failure_count"] == 2
        assert stats["total_calls"] == 2

    @pytest.mark.asyncio
    async def test_reset(self, circuit_breaker):
        """测试重置熔断器"""
        # 让熔断器打开
        async def fail_func():
            raise ConnectionError()

        for _ in range(3):
            try:
                await circuit_breaker.call(fail_func)
            except ConnectionError:
                pass

        assert circuit_breaker.get_state() == CircuitBreakerState.OPEN

        # 重置
        await circuit_breaker.reset()

        # 应该回到关闭状态
        assert circuit_breaker.get_state() == CircuitBreakerState.CLOSED
        assert circuit_breaker.get_stats()["failure_count"] == 0


class TestWithRetryDecorator:
    """重试装饰器测试"""

    @pytest.mark.asyncio
    async def test_successful_call_no_retry(self):
        """测试成功调用不需要重试"""
        @with_retry(max_attempts=3)
        async def success_func():
            return "success"

        result = await success_func()
        assert result == "success"

    @pytest.mark.asyncio
    async def test_retry_on_connection_error(self):
        """测试连接错误时重试"""
        call_count = 0

        @with_retry(max_attempts=3, base_delay=0.01)
        async def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("Connection failed")
            return "success"

        result = await fail_then_succeed()
        assert result == "success"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_max_attempts_reached(self):
        """测试达到最大重试次数"""
        @with_retry(max_attempts=3, base_delay=0.01)
        async def always_fail():
            raise ConnectionError("Always fails")

        with pytest.raises(ConnectionError):
            await always_fail()

    @pytest.mark.asyncio
    async def test_no_retry_on_value_error(self):
        """测试 ValueError 不重试"""
        @with_retry(max_attempts=3)
        async def raise_value_error():
            raise ValueError("Not retryable")

        with pytest.raises(ValueError):
            await raise_value_error()


class TestWithCircuitBreakerDecorator:
    """熔断器装饰器测试"""

    @pytest.mark.asyncio
    async def test_decorator_creates_breaker(self):
        """测试装饰器创建熔断器"""
        class TestService:
            @with_circuit_breaker(failure_threshold=2)
            async def method(self):
                return "result"

        service = TestService()
        result = await service.method()

        assert result == "result"
        # 应该创建了熔断器属性
        assert hasattr(service, "_circuit_breaker")

    @pytest.mark.asyncio
    async def test_decorator_opens_circuit(self):
        """测试装饰器熔断器打开"""
        class TestService:
            @with_circuit_breaker(failure_threshold=2)
            async def method(self):
                raise ConnectionError()

        service = TestService()

        # 触发熔断
        for _ in range(2):
            try:
                await service.method()
            except ConnectionError:
                pass

        # 熔断器应该打开
        breaker = getattr(service, "_circuit_breaker")
        assert breaker.get_state() == CircuitBreakerState.OPEN


class TestRetryWithCircuitBreaker:
    """重试和熔断组合测试"""

    @pytest.fixture
    def wrapper(self):
        return RetryWithCircuitBreaker(
            retry_config=RetryConfig(max_attempts=2, base_delay=0.01),
            circuit_breaker_config=CircuitBreakerConfig(failure_threshold=2),
        )

    @pytest.mark.asyncio
    async def test_combined_success(self, wrapper):
        """测试组合使用成功"""
        async def success_func():
            return "success"

        result = await wrapper.call(success_func)
        assert result == "success"

    @pytest.mark.asyncio
    async def test_retry_then_success(self, wrapper):
        """测试重试后成功"""
        call_count = 0

        async def fail_once():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError()
            return "success"

        result = await wrapper.call(fail_once)
        assert result == "success"

    @pytest.mark.asyncio
    async def test_circuit_breaker_opens(self, wrapper):
        """测试熔断器打开"""
        async def always_fail():
            raise ConnectionError()

        # 触发熔断
        for _ in range(3):
            try:
                await wrapper.call(always_fail)
            except:
                pass

        stats = wrapper.get_stats()
        assert stats["circuit_breaker"]["state"] == "open"

    @pytest.mark.asyncio
    async def test_get_stats(self, wrapper):
        """测试获取统计信息"""
        stats = wrapper.get_stats()

        assert "circuit_breaker" in stats
        assert "retry_config" in stats
        assert stats["retry_config"]["max_attempts"] == 2


class TestIntegrationScenarios:
    """集成场景测试"""

    @pytest.mark.asyncio
    async def test_api_call_with_retry_and_circuit_breaker(self):
        """测试模拟 API 调用"""
        wrapper = RetryWithCircuitBreaker(
            retry_config=RetryConfig(max_attempts=3, base_delay=0.01),
            circuit_breaker_config=CircuitBreakerConfig(failure_threshold=2),
        )

        call_count = 0

        async def mock_api_call():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise ConnectionError("API unavailable")
            return {"status": "ok", "data": "result"}

        result = await wrapper.call(mock_api_call)
        assert result["status"] == "ok"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_timeout_protection(self):
        """测试超时保护"""
        wrapper = RetryWithCircuitBreaker(
            retry_config=RetryConfig(max_attempts=2, base_delay=0.01),
        )

        async def slow_func():
            await asyncio.sleep(1)
            return "done"

        # 应该在超时前完成
        result = await wrapper.call(slow_func)
        assert result == "done"

    @pytest.mark.asyncio
    async def test_graceful_degradation(self):
        """测试优雅降级"""
        wrapper = RetryWithCircuitBreaker(
            retry_config=RetryConfig(max_attempts=2, base_delay=0.01),
            circuit_breaker_config=CircuitBreakerConfig(failure_threshold=3),
        )

        # 让服务失败
        async def failing_service():
            raise ConnectionError()

        for _ in range(4):
            try:
                await wrapper.call(failing_service)
            except:
                pass

        # 熔断器应该打开
        stats = wrapper.get_stats()
        assert stats["circuit_breaker"]["state"] == "open"

        # 后续调用应该快速失败而不是等待
        import time
        start = time.time()
        try:
            await wrapper.call(failing_service)
        except:
            pass
        elapsed = time.time() - start

        # 应该快速失败（不等待重试）
        assert elapsed < 0.5
