"""LLM 模块

提供统一的 LLM 服务商接口
"""

from .base import BaseLLMProvider
from .entities import LLMResponse, TokenUsage
from .sources import (
    OpenAIProvider,
    OpenAICompatibleProvider,
    ClaudeProvider,
    GeminiProvider,
    GLMProvider,
    DashScopeProvider,
    DeepSeekProvider,
    MoonshotProvider,
    OllamaProvider,
    LMStudioProvider,
    ZhipuProvider,
)
from .token_counter import (
    TokenCounterBackend,
    BaseTokenCounter,
    EstimateTokenCounter,
    TikTokenCounter,
    CachedTokenCounter,
    TokenCounterFactory,
)
from .safe_calculator import (
    SafeCalculator,
    AdvancedSafeCalculator,
    safe_calculate,
)
from .llm_cache import (
    CacheStrategy,
    CacheEntry,
    CacheStorageBackend,
    MemoryCacheStorage,
    LLMResponseCache,
    get_global_cache,
    set_global_cache,
)
from .reliability import (
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

__all__ = [
    # Base 类
    "BaseLLMProvider",
    # Entity 类
    "LLMResponse",
    "TokenUsage",
    # Provider 类
    "OpenAIProvider",
    "OpenAICompatibleProvider",
    "ClaudeProvider",
    "GeminiProvider",
    "GLMProvider",
    "DashScopeProvider",
    "DeepSeekProvider",
    "MoonshotProvider",
    "OllamaProvider",
    "LMStudioProvider",
    "ZhipuProvider",
    # Token Counter 类
    "TokenCounterBackend",
    "BaseTokenCounter",
    "EstimateTokenCounter",
    "TikTokenCounter",
    "CachedTokenCounter",
    "TokenCounterFactory",
    # Safe Calculator 类
    "SafeCalculator",
    "AdvancedSafeCalculator",
    "safe_calculate",
    # LLM Cache 类
    "CacheStrategy",
    "CacheEntry",
    "CacheStorageBackend",
    "MemoryCacheStorage",
    "LLMResponseCache",
    "get_global_cache",
    "set_global_cache",
    # Reliability 类
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
