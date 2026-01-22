"""LLM 重试和熔断机制

参考 AstrBot 实现，提供完善的错误处理和可靠性保障
包括指数退避重试、熔断器模式等
"""

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional, TypeVar, List, Dict
from functools import wraps
from loguru import logger


T = TypeVar("T")


class CircuitBreakerState(Enum):
    """熔断器状态"""
    CLOSED = "closed"       # 关闭（正常工作）
    OPEN = "open"           # 打开（熔断中，请求被拒绝）
    HALF_OPEN = "half_open"  # 半开（尝试恢复）


@dataclass
class RetryConfig:
    """重试配置"""
    max_attempts: int = 3
    """最大重试次数"""

    base_delay: float = 1.0
    """基础延迟（秒）"""

    max_delay: float = 60.0
    """最大延迟（秒）"""

    exponential_base: float = 2.0
    """指数退避基数"""

    jitter: bool = True
    """是否添加随机抖动"""

    retryable_exceptions: tuple = (
        ConnectionError,
        TimeoutError,
        asyncio.TimeoutError,
    )
    """可重试的异常类型"""


@dataclass
class CircuitBreakerConfig:
    """熔断器配置"""
    failure_threshold: int = 5
    """失败阈值（连续失败多少次后熔断）"""

    success_threshold: int = 2
    """成功阈值（半开状态下连续成功多少次后恢复）"""

    timeout: float = 60.0
    """熔断超时（秒），熔断后多久尝试恢复"""

    half_open_max_calls: int = 3
    """半开状态下最大尝试次数"""

    window_size: int = 10
    """统计窗口大小（用于计算失败率）"""


@dataclass
class CallResult:
    """调用结果"""
    success: bool
    """是否成功"""

    duration: float
    """调用耗时（秒）"""

    error: Optional[Exception] = None
    """错误信息"""

    timestamp: datetime = field(default_factory=datetime.now)
    """调用时间"""


class RetryStrategy:
    """重试策略"""

    @staticmethod
    def calculate_delay(attempt: int, config: RetryConfig) -> float:
        """计算重试延迟

        Args:
            attempt: 当前重试次数（从 0 开始）
            config: 重试配置

        Returns:
            延迟时间（秒）
        """
        # 指数退避
        delay = min(
            config.base_delay * (config.exponential_base ** attempt),
            config.max_delay
        )

        # 添加随机抖动（避免雷鸣 herd 效应）
        if config.jitter:
            import random
            delay = delay * (0.5 + random.random())

        return delay

    @staticmethod
    def should_retry(
        exception: Exception,
        attempt: int,
        config: RetryConfig
    ) -> bool:
        """判断是否应该重试

        Args:
            exception: 发生的异常
            attempt: 当前重试次数
            config: 重试配置

        Returns:
            是否应该重试
        """
        # 检查重试次数
        if attempt >= config.max_attempts:
            return False

        # 检查异常类型
        if not isinstance(exception, config.retryable_exceptions):
            return False

        return True


class CircuitBreaker:
    """熔断器

    实现熔断器模式，防止级联故障
    """

    def __init__(self, config: CircuitBreakerConfig):
        """初始化熔断器

        Args:
            config: 熔断器配置
        """
        self.config = config
        self.state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[datetime] = None
        self._call_history: List[CallResult] = []
        self._lock = asyncio.Lock()

    async def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """通过熔断器调用函数

        Args:
            func: 要调用的函数
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            函数返回值

        Raises:
            Exception: 调用失败或熔断器打开
        """
        async with self._lock:
            # 检查熔断器状态
            if self.state == CircuitBreakerState.OPEN:
                # 检查是否可以尝试恢复
                if self._should_attempt_reset():
                    self.state = CircuitBreakerState.HALF_OPEN
                    self._success_count = 0
                    logger.info("熔断器进入半开状态，尝试恢复")
                else:
                    raise Exception("熔断器已打开，请求被拒绝")

        start_time = time.time()
        try:
            result = await func(*args, **kwargs)

            # 调用成功
            duration = time.time() - start_time
            await self._on_success(duration)

            return result

        except Exception as e:
            # 调用失败
            duration = time.time() - start_time
            await self._on_failure(e, duration)
            raise

    async def _on_success(self, duration: float) -> None:
        """处理调用成功"""
        async with self._lock:
            self._success_count += 1
            self._failure_count = 0

            # 记录调用历史
            self._call_history.append(CallResult(
                success=True,
                duration=duration
            ))

            # 限制历史记录大小
            if len(self._call_history) > self.config.window_size:
                self._call_history.pop(0)

            # 半开状态下，成功达到阈值则恢复
            if self.state == CircuitBreakerState.HALF_OPEN:
                if self._success_count >= self.config.success_threshold:
                    self.state = CircuitBreakerState.CLOSED
                    logger.info("熔断器已恢复到关闭状态")

    async def _on_failure(self, error: Exception, duration: float) -> None:
        """处理调用失败"""
        async with self._lock:
            self._failure_count += 1
            self._success_count = 0
            self._last_failure_time = datetime.now()

            # 记录调用历史
            self._call_history.append(CallResult(
                success=False,
                duration=duration,
                error=error
            ))

            # 限制历史记录大小
            if len(self._call_history) > self.config.window_size:
                self._call_history.pop(0)

            # 检查是否需要熔断
            if self._failure_count >= self.config.failure_threshold:
                if self.state != CircuitBreakerState.OPEN:
                    self.state = CircuitBreakerState.OPEN
                    logger.error(
                        f"熔断器已打开（连续失败 {self._failure_count} 次），"
                        f"将在 {self.config.timeout} 秒后尝试恢复"
                    )

    def _should_attempt_reset(self) -> bool:
        """检查是否应该尝试恢复"""
        if self._last_failure_time is None:
            return True

        elapsed = (datetime.now() - self._last_failure_time).total_seconds()
        return elapsed >= self.config.timeout

    def get_state(self) -> CircuitBreakerState:
        """获取熔断器状态"""
        return self.state

    def get_stats(self) -> Dict[str, Any]:
        """获取熔断器统计信息"""
        total_calls = len(self._call_history)
        success_calls = sum(1 for r in self._call_history if r.success)

        return {
            "state": self.state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "total_calls": total_calls,
            "success_rate": success_calls / total_calls if total_calls > 0 else 0,
            "last_failure_time": self._last_failure_time.isoformat() if self._last_failure_time else None,
        }

    async def reset(self) -> None:
        """重置熔断器"""
        async with self._lock:
            self.state = CircuitBreakerState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._call_history.clear()
            logger.info("熔断器已重置")


def with_retry(
    config: Optional[RetryConfig] = None,
    on_retry: Optional[Callable[[int, Exception], Any]] = None,
):
    """重试装饰器

    Args:
        config: 重试配置
        on_retry: 重试时的回调函数

    Returns:
        装饰器函数

    Examples:
        >>> @with_retry(max_attempts=3)
        ... async def my_function():
        ...     pass
    """
    if config is None:
        config = RetryConfig()

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exception = None

            for attempt in range(config.max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e

                    if not RetryStrategy.should_retry(e, attempt, config):
                        raise

                    # 计算延迟
                    delay = RetryStrategy.calculate_delay(attempt, config)

                    logger.warning(
                        f"调用 {func.__name__} 失败（第 {attempt + 1} 次），"
                        f"将在 {delay:.2f} 秒后重试: {e}"
                    )

                    # 调用重试回调
                    if on_retry:
                        try:
                            await on_retry(attempt, e)
                        except Exception:
                            pass

                    # 等待后重试
                    await asyncio.sleep(delay)

            # 所有重试都失败
            logger.error(
                f"调用 {func.__name__} 失败，已达到最大重试次数 ({config.max_attempts})"
            )
            raise last_exception

        return wrapper
    return decorator


def with_circuit_breaker(
    config: Optional[CircuitBreakerConfig] = None,
    circuit_breaker_attr: str = "_circuit_breaker",
):
    """熔断器装饰器

    Args:
        config: 熔断器配置
        circuit_breaker_attr: 熔断器属性名

    Returns:
        装饰器函数

    Examples:
        >>> @with_circuit_breaker(failure_threshold=5)
        ... async def my_function():
        ...     pass
    """
    if config is None:
        config = CircuitBreakerConfig()

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(self, *args, **kwargs) -> T:
            # 获取或创建熔断器
            if not hasattr(self, circuit_breaker_attr):
                cb = CircuitBreaker(config)
                setattr(self, circuit_breaker_attr, cb)
            else:
                cb = getattr(self, circuit_breaker_attr)

            # 通过熔断器调用
            return await cb.call(func, self, *args, **kwargs)

        return wrapper
    return decorator


class RetryWithCircuitBreaker:
    """结合重试和熔断的调用包装器

    同时提供重试和熔断功能
    """

    def __init__(
        self,
        retry_config: Optional[RetryConfig] = None,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
    ):
        """初始化包装器

        Args:
            retry_config: 重试配置
            circuit_breaker_config: 熔断器配置
        """
        self.retry_config = retry_config or RetryConfig()
        self.circuit_breaker_config = circuit_breaker_config or CircuitBreakerConfig()
        self._circuit_breaker = CircuitBreaker(self.circuit_breaker_config)

    async def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """调用函数（带重试和熔断）

        Args:
            func: 要调用的函数
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            函数返回值
        """
        # 通过熔断器调用
        return await self._circuit_breaker.call(
            self._call_with_retry,
            func,
            *args,
            **kwargs
        )

    async def _call_with_retry(self, func: Callable[..., T], *args, **kwargs) -> T:
        """带重试的调用"""
        last_exception = None

        for attempt in range(self.retry_config.max_attempts):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_exception = e

                if not RetryStrategy.should_retry(e, attempt, self.retry_config):
                    raise

                delay = RetryStrategy.calculate_delay(attempt, self.retry_config)
                await asyncio.sleep(delay)

        raise last_exception

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "circuit_breaker": self._circuit_breaker.get_stats(),
            "retry_config": {
                "max_attempts": self.retry_config.max_attempts,
                "base_delay": self.retry_config.base_delay,
                "max_delay": self.retry_config.max_delay,
            },
        }


__all__ = [
    "CircuitBreakerState",
    "RetryConfig",
    "CircuitBreakerConfig",
    "CallResult",
    "RetryStrategy",
    "CircuitBreaker",
    "with_retry",
    "with_circuit_breaker",
    "RetryWithCircuitBreaker",
]
