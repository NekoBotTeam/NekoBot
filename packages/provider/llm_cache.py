"""LLM 响应缓存模块

参考 AstrBot 实现，提供智能的 LLM 响应缓存功能
减少重复请求，降低 API 成本，提高响应速度
"""

import hashlib
import json
from abc import ABC, abstractmethod
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from loguru import logger


class CacheStrategy(Enum):
    """缓存策略"""
    EXACT = "exact"          # 精确匹配（完全相同）
    SEMANTIC = "semantic"    # 语义匹配（相似查询）
    HYBRID = "hybrid"        # 混合模式


@dataclass
class CacheEntry:
    """缓存条目"""
    key: str
    """缓存键"""

    request_hash: str
    """请求内容的哈希值"""

    response: str
    """LLM 响应内容"""

    model: str
    """使用的模型"""

    provider: str
    """提供商名称"""

    created_at: datetime
    """创建时间"""

    last_accessed: datetime
    """最后访问时间"""

    access_count: int = 0
    """访问次数"""

    tokens_used: int = 0
    """使用的 token 数量"""

    metadata: Dict[str, Any] = field(default_factory=dict)
    """额外元数据"""

    @property
    def age_seconds(self) -> int:
        """缓存年龄（秒）"""
        return int((datetime.now() - self.created_at).total_seconds())

    @property
    def is_expired(self, ttl_seconds: int) -> bool:
        """检查是否过期"""
        return self.age_seconds > ttl_seconds

    def touch(self) -> None:
        """更新访问时间和次数"""
        self.last_accessed = datetime.now()
        self.access_count += 1


class CacheStorageBackend(ABC):
    """缓存存储后端抽象类"""

    @abstractmethod
    async def get(self, key: str) -> Optional[CacheEntry]:
        """获取缓存条目"""
        pass

    @abstractmethod
    async def set(self, entry: CacheEntry) -> None:
        """设置缓存条目"""
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """删除缓存条目"""
        pass

    @abstractmethod
    async def clear(self) -> None:
        """清空所有缓存"""
        pass

    @abstractmethod
    async def list_keys(self) -> List[str]:
        """列出所有缓存键"""
        pass


class MemoryCacheStorage(CacheStorageBackend):
    """内存缓存存储"""

    def __init__(self, max_size: int = 1000):
        """初始化内存缓存

        Args:
            max_size: 最大缓存条目数
        """
        self.max_size = max_size
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()

    async def get(self, key: str) -> Optional[CacheEntry]:
        """获取缓存条目"""
        entry = self._cache.get(key)
        if entry:
            # 移动到末尾（LRU）
            self._cache.move_to_end(key)
            entry.touch()
        return entry

    async def set(self, entry: CacheEntry) -> None:
        """设置缓存条目"""
        # 如果已存在，更新并移动到末尾
        if entry.key in self._cache:
            self._cache.move_to_end(entry.key)

        self._cache[entry.key] = entry

        # 检查大小限制
        while len(self._cache) > self.max_size:
            # 删除最旧的条目
            self._cache.popitem(last=False)

    async def delete(self, key: str) -> bool:
        """删除缓存条目"""
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    async def clear(self) -> None:
        """清空所有缓存"""
        self._cache.clear()

    async def list_keys(self) -> List[str]:
        """列出所有缓存键"""
        return list(self._cache.keys())


class LLMResponseCache:
    """LLM 响应缓存管理器

    特性：
    - 多种缓存策略（精确、语义、混合）
    - 自动过期和清理
    - LRU 缓存淘汰
    - 缓存统计和监控
    """

    def __init__(
        self,
        storage: Optional[CacheStorageBackend] = None,
        ttl_seconds: int = 3600,
        strategy: CacheStrategy = CacheStrategy.EXACT,
        enable_semantic: bool = False,
    ):
        """初始化缓存管理器

        Args:
            storage: 存储后端（默认内存存储）
            ttl_seconds: 缓存生存时间（秒）
            strategy: 缓存策略
            enable_semantic: 是否启用语义匹配
        """
        self.storage = storage or MemoryCacheStorage()
        self.ttl_seconds = ttl_seconds
        self.strategy = strategy
        self.enable_semantic = enable_semantic

        # 统计信息
        self._hit_count = 0
        self._miss_count = 0
        self._set_count = 0

    def _generate_cache_key(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float = 0.7,
        **kwargs
    ) -> str:
        """生成缓存键

        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度参数
            **kwargs: 其他参数

        Returns:
            缓存键
        """
        # 规范化输入
        normalized = {
            "messages": messages,
            "model": model,
            "temperature": temperature,
            **kwargs
        }

        # 序列化为 JSON 并计算哈希
        json_str = json.dumps(normalized, sort_keys=True, ensure_ascii=False)
        hash_obj = hashlib.sha256(json_str.encode("utf-8"))

        return f"llm_cache:{hash_obj.hexdigest()}"

    def _generate_request_hash(
        self,
        messages: List[Dict[str, Any]],
        **params
    ) -> str:
        """生成请求内容哈希（用于语义匹配）"""
        # 提取用户消息内容
        user_messages = [
            msg.get("content", "")
            for msg in messages
            if msg.get("role") == "user"
        ]

        combined = " ".join(user_messages) + str(params)
        return hashlib.md5(combined.encode("utf-8")).hexdigest()

    async def get(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        provider: str,
        temperature: float = 0.7,
        **kwargs
    ) -> Optional[CacheEntry]:
        """获取缓存的响应

        Args:
            messages: 消息列表
            model: 模型名称
            provider: 提供商名称
            temperature: 温度参数
            **kwargs: 其他参数

        Returns:
            缓存条目，如果不存在或已过期则返回 None
        """
        cache_key = self._generate_cache_key(messages, model, temperature, **kwargs)

        entry = await self.storage.get(cache_key)

        if entry is None:
            self._miss_count += 1
            return None

        # 检查过期
        if entry.is_expired(self.ttl_seconds):
            await self.storage.delete(cache_key)
            self._miss_count += 1
            logger.debug(f"缓存已过期: {cache_key}")
            return None

        # 检查模型和提供商是否匹配
        if entry.model != model or entry.provider != provider:
            self._miss_count += 1
            return None

        self._hit_count += 1
        logger.debug(f"缓存命中: {cache_key}, 访问次数: {entry.access_count + 1}")
        return entry

    async def set(
        self,
        messages: List[Dict[str, Any]],
        response: str,
        model: str,
        provider: str,
        temperature: float = 0.7,
        tokens_used: int = 0,
        **kwargs
    ) -> CacheEntry:
        """设置缓存条目

        Args:
            messages: 消息列表
            response: LLM 响应
            model: 模型名称
            provider: 提供商名称
            temperature: 温度参数
            tokens_used: 使用的 token 数量
            **kwargs: 其他参数

        Returns:
            创建的缓存条目
        """
        cache_key = self._generate_cache_key(messages, model, temperature, **kwargs)
        request_hash = self._generate_request_hash(messages, temperature=temperature)

        now = datetime.now()
        entry = CacheEntry(
            key=cache_key,
            request_hash=request_hash,
            response=response,
            model=model,
            provider=provider,
            created_at=now,
            last_accessed=now,
            tokens_used=tokens_used,
            metadata=kwargs
        )

        await self.storage.set(entry)
        self._set_count += 1

        logger.debug(f"缓存已设置: {cache_key}, token: {tokens_used}")
        return entry

    async def invalidate(self, model: Optional[str] = None, provider: Optional[str] = None) -> int:
        """使缓存失效

        Args:
            model: 指定模型（None 表示所有模型）
            provider: 指定提供商（None 表示所有提供商）

        Returns:
            删除的缓存条目数
        """
        keys = await self.storage.list_keys()
        deleted_count = 0

        for key in keys:
            entry = await self.storage.get(key)
            if entry is None:
                continue

            # 检查匹配条件
            if model and entry.model != model:
                continue
            if provider and entry.provider != provider:
                continue

            # 删除匹配的条目
            if await self.storage.delete(key):
                deleted_count += 1

        logger.info(f"缓存已失效: 模型={model}, 提供商={provider}, 删除={deleted_count}")
        return deleted_count

    async def clear(self) -> None:
        """清空所有缓存"""
        await self.storage.clear()
        self._hit_count = 0
        self._miss_count = 0
        self._set_count = 0
        logger.info("所有缓存已清空")

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息

        Returns:
            统计信息字典
        """
        total = self._hit_count + self._miss_count
        hit_rate = self._hit_count / total if total > 0 else 0

        return {
            "hit_count": self._hit_count,
            "miss_count": self._miss_count,
            "set_count": self._set_count,
            "total_requests": total,
            "hit_rate": hit_rate,
            "ttl_seconds": self.ttl_seconds,
            "strategy": self.strategy.value,
        }

    async def cleanup_expired(self) -> int:
        """清理过期的缓存条目

        Returns:
            清理的条目数
        """
        keys = await self.storage.list_keys()
        cleaned_count = 0

        for key in keys:
            entry = await self.storage.get(key)
            if entry and entry.is_expired(self.ttl_seconds):
                if await self.storage.delete(key):
                    cleaned_count += 1

        if cleaned_count > 0:
            logger.info(f"清理了 {cleaned_count} 个过期缓存条目")

        return cleaned_count


# 全局缓存实例
_global_cache: Optional[LLMResponseCache] = None


def get_global_cache() -> LLMResponseCache:
    """获取全局缓存实例"""
    global _global_cache
    if _global_cache is None:
        _global_cache = LLMResponseCache()
    return _global_cache


def set_global_cache(cache: LLMResponseCache) -> None:
    """设置全局缓存实例"""
    global _global_cache
    _global_cache = cache


__all__ = [
    "CacheStrategy",
    "CacheEntry",
    "CacheStorageBackend",
    "MemoryCacheStorage",
    "LLMResponseCache",
    "get_global_cache",
    "set_global_cache",
]
