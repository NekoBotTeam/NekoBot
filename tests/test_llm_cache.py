"""LLM 响应缓存单元测试

测试 LLM 响应缓存的功能
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from packages.provider.llm_cache import (
    CacheStrategy,
    CacheEntry,
    CacheStorageBackend,
    MemoryCacheStorage,
    LLMResponseCache,
    get_global_cache,
    set_global_cache,
)


class TestCacheEntry:
    """缓存条目测试"""

    def test_create_entry(self):
        """测试创建缓存条目"""
        entry = CacheEntry(
            key="test_key",
            request_hash="hash123",
            response="Test response",
            model="gpt-4",
            provider="openai",
            created_at=datetime.now(),
            last_accessed=datetime.now(),
        )

        assert entry.key == "test_key"
        assert entry.response == "Test response"
        assert entry.access_count == 0

    def test_age_seconds(self):
        """测试计算缓存年龄"""
        now = datetime.now()
        entry = CacheEntry(
            key="test",
            request_hash="hash",
            response="response",
            model="gpt-4",
            provider="openai",
            created_at=now,
            last_accessed=now,
        )

        # 刚创建，年龄应该很小
        assert entry.age_seconds < 10

    def test_is_expired(self):
        """测试过期检查"""
        entry = CacheEntry(
            key="test",
            request_hash="hash",
            response="response",
            model="gpt-4",
            provider="openai",
            created_at=datetime.now() - timedelta(seconds=61),
            last_accessed=datetime.now(),
        )

        # 61 秒前创建，TTL 为 60 秒
        assert entry.is_expired(ttl_seconds=60) is True
        assert entry.is_expired(ttl_seconds=120) is False

    def test_touch(self):
        """测试更新访问信息"""
        entry = CacheEntry(
            key="test",
            request_hash="hash",
            response="response",
            model="gpt-4",
            provider="openai",
            created_at=datetime.now(),
            last_accessed=datetime.now(),
        )

        assert entry.access_count == 0

        entry.touch()
        assert entry.access_count == 1

        entry.touch()
        assert entry.access_count == 2


class TestMemoryCacheStorage:
    """内存缓存存储测试"""

    @pytest.fixture
    def storage(self):
        return MemoryCacheStorage(max_size=5)

    @pytest.mark.asyncio
    async def test_set_and_get(self, storage):
        """测试设置和获取"""
        entry = CacheEntry(
            key="key1",
            request_hash="hash1",
            response="response1",
            model="gpt-4",
            provider="openai",
            created_at=datetime.now(),
            last_accessed=datetime.now(),
        )

        await storage.set(entry)
        result = await storage.get("key1")

        assert result is not None
        assert result.response == "response1"

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, storage):
        """测试获取不存在的键"""
        result = await storage.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete(self, storage):
        """测试删除"""
        entry = CacheEntry(
            key="key1",
            request_hash="hash1",
            response="response1",
            model="gpt-4",
            provider="openai",
            created_at=datetime.now(),
            last_accessed=datetime.now(),
        )

        await storage.set(entry)
        assert await storage.delete("key1") is True

        # 再次删除应该失败
        assert await storage.delete("key1") is False

    @pytest.mark.asyncio
    async def test_clear(self, storage):
        """测试清空"""
        entry = CacheEntry(
            key="key1",
            request_hash="hash1",
            response="response1",
            model="gpt-4",
            provider="openai",
            created_at=datetime.now(),
            last_accessed=datetime.now(),
        )

        await storage.set(entry)
        await storage.clear()

        result = await storage.get("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_keys(self, storage):
        """测试列出键"""
        for i in range(3):
            entry = CacheEntry(
                key=f"key{i}",
                request_hash=f"hash{i}",
                response=f"response{i}",
                model="gpt-4",
                provider="openai",
                created_at=datetime.now(),
                last_accessed=datetime.now(),
            )
            await storage.set(entry)

        keys = await storage.list_keys()
        assert len(keys) == 3
        assert set(keys) == {"key0", "key1", "key2"}

    @pytest.mark.asyncio
    async def test_lru_eviction(self, storage):
        """测试 LRU 淘汰"""
        storage = MemoryCacheStorage(max_size=3)

        # 添加 3 个条目
        for i in range(3):
            entry = CacheEntry(
                key=f"key{i}",
                request_hash=f"hash{i}",
                response=f"response{i}",
                model="gpt-4",
                provider="openai",
                created_at=datetime.now(),
                last_accessed=datetime.now(),
            )
            await storage.set(entry)

        # 访问 key0，使其成为最近使用的
        await storage.get("key0")

        # 添加第 4 个条目
        entry4 = CacheEntry(
            key="key4",
            request_hash="hash4",
            response="response4",
            model="gpt-4",
            provider="openai",
            created_at=datetime.now(),
            last_accessed=datetime.now(),
        )
        await storage.set(entry4)

        keys = await storage.list_keys()
        # key1 应该被淘汰（最久未使用）
        assert set(keys) == {"key0", "key2", "key4"}

    @pytest.mark.asyncio
    async def test_update_existing(self, storage):
        """测试更新已存在的条目"""
        entry1 = CacheEntry(
            key="key1",
            request_hash="hash1",
            response="response1",
            model="gpt-4",
            provider="openai",
            created_at=datetime.now(),
            last_accessed=datetime.now(),
        )
        await storage.set(entry1)

        # 更新
        entry2 = CacheEntry(
            key="key1",
            request_hash="hash2",
            response="response2",
            model="gpt-4",
            provider="openai",
            created_at=datetime.now(),
            last_accessed=datetime.now(),
        )
        await storage.set(entry2)

        result = await storage.get("key1")
        assert result.response == "response2"


class TestLLMResponseCache:
    """LLM 响应缓存管理器测试"""

    @pytest.fixture
    def cache(self):
        return LLMResponseCache(ttl_seconds=60)

    @pytest.mark.asyncio
    async def test_cache_miss(self, cache):
        """测试缓存未命中"""
        messages = [{"role": "user", "content": "Hello"}]
        result = await cache.get(messages, "gpt-4", "openai")
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_set_and_get(self, cache):
        """测试缓存设置和获取"""
        messages = [{"role": "user", "content": "Hello"}]

        # 设置缓存
        entry = await cache.set(
            messages=messages,
            response="Hi there!",
            model="gpt-4",
            provider="openai",
            tokens_used=10,
        )

        assert entry.response == "Hi there!"

        # 获取缓存
        result = await cache.get(messages, "gpt-4", "openai")
        assert result is not None
        assert result.response == "Hi there!"

    @pytest.mark.asyncio
    async def test_cache_key_different_params(self, cache):
        """测试不同参数生成不同缓存键"""
        messages = [{"role": "user", "content": "Hello"}]

        await cache.set(messages, "Response1", "gpt-4", "openai", temperature=0.7)
        await cache.set(messages, "Response2", "gpt-4", "openai", temperature=1.0)

        result1 = await cache.get(messages, "gpt-4", "openai", temperature=0.7)
        result2 = await cache.get(messages, "gpt-4", "openai", temperature=1.0)

        assert result1.response == "Response1"
        assert result2.response == "Response2"

    @pytest.mark.asyncio
    async def test_cache_expiration(self, cache):
        """测试缓存过期"""
        cache = LLMResponseCache(ttl_seconds=1)  # 1 秒 TTL
        messages = [{"role": "user", "content": "Hello"}]

        await cache.set(messages, "Response", "gpt-4", "openai")

        # 立即获取应该命中
        result = await cache.get(messages, "gpt-4", "openai")
        assert result is not None

        # 等待过期
        await asyncio.sleep(1.5)

        # 过期后应该未命中
        result = await cache.get(messages, "gpt-4", "openai")
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_invalidation(self, cache):
        """测试缓存失效"""
        messages = [{"role": "user", "content": "Hello"}]

        # 添加多个缓存
        await cache.set(messages, "Response1", "gpt-4", "openai")
        await cache.set(messages, "Response2", "gpt-3.5", "openai")

        # 使特定模型的缓存失效
        deleted = await cache.invalidate(model="gpt-4")

        assert deleted > 0

        # gpt-4 应该失效
        result = await cache.get(messages, "gpt-4", "openai")
        assert result is None

        # gpt-3.5 应该还在
        result = await cache.get(messages, "gpt-3.5", "openai")
        assert result is not None

    @pytest.mark.asyncio
    async def test_cache_stats(self, cache):
        """测试缓存统计"""
        messages = [{"role": "user", "content": "Hello"}]

        # 未命中
        await cache.get(messages, "gpt-4", "openai")

        # 设置
        await cache.set(messages, "Response", "gpt-4", "openai")

        # 命中
        await cache.get(messages, "gpt-4", "openai")

        stats = cache.get_stats()
        assert stats["hit_count"] == 1
        assert stats["miss_count"] == 1
        assert stats["hit_rate"] == 0.5

    @pytest.mark.asyncio
    async def test_cleanup_expired(self, cache):
        """测试清理过期缓存"""
        cache = LLMResponseCache(ttl_seconds=1)
        messages = [{"role": "user", "content": "Hello"}]

        await cache.set(messages, "Response", "gpt-4", "openai")

        # 等待过期
        await asyncio.sleep(1.5)

        # 清理
        cleaned = await cache.cleanup_expired()
        assert cleaned > 0

    @pytest.mark.asyncio
    async def test_clear_cache(self, cache):
        """测试清空缓存"""
        messages = [{"role": "user", "content": "Hello"}]

        await cache.set(messages, "Response", "gpt-4", "openai")
        assert await cache.get(messages, "gpt-4", "openai") is not None

        await cache.clear()
        assert await cache.get(messages, "gpt-4", "openai") is None

        # 统计应该重置
        stats = cache.get_stats()
        assert stats["hit_count"] == 0
        assert stats["miss_count"] == 0


class TestGlobalCache:
    """全局缓存测试"""

    @pytest.mark.asyncio
    async def test_global_cache_singleton(self):
        """测试全局缓存单例"""
        cache1 = get_global_cache()
        cache2 = get_global_cache()

        assert cache1 is cache2

    @pytest.mark.asyncio
    async def test_set_global_cache(self):
        """测试设置全局缓存"""
        custom_cache = LLMResponseCache(ttl_seconds=120)
        set_global_cache(custom_cache)

        result = get_global_cache()
        assert result is custom_cache

    @pytest.mark.asyncio
    async def test_global_cache_usage(self):
        """测试使用全局缓存"""
        cache = get_global_cache()
        messages = [{"role": "user", "content": "Test"}]

        await cache.set(messages, "Response", "gpt-4", "openai")
        result = await cache.get(messages, "gpt-4", "openai")

        assert result is not None
        assert result.response == "Response"


class TestCacheStrategies:
    """缓存策略测试"""

    def test_cache_strategy_enum(self):
        """测试缓存策略枚举"""
        assert CacheStrategy.EXACT.value == "exact"
        assert CacheStrategy.SEMANTIC.value == "semantic"
        assert CacheStrategy.HYBRID.value == "hybrid"


class TestCacheIntegration:
    """缓存集成测试"""

    @pytest.mark.asyncio
    async def test_real_world_scenario(self):
        """测试真实场景"""
        cache = LLMResponseCache(ttl_seconds=3600)

        # 模拟用户对话
        conversation = [
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": "What is Python?"},
        ]

        # 第一次请求 - 缓存未命中
        result1 = await cache.get(conversation, "gpt-4", "openai")
        assert result1 is None

        # 模拟 LLM 响应并缓存
        await cache.set(
            messages=conversation,
            response="Python is a programming language",
            model="gpt-4",
            provider="openai",
            tokens_used=50,
        )

        # 第二次请求 - 缓存命中
        result2 = await cache.get(conversation, "gpt-4", "openai")
        assert result2 is not None
        assert result2.response == "Python is a programming language"
        assert result2.tokens_used == 50
        assert result2.access_count >= 1

    @pytest.mark.asyncio
    async def test_multiple_providers(self):
        """测试多个提供商"""
        cache = LLMResponseCache()
        messages = [{"role": "user", "content": "Hello"}]

        # 不同提供商的响应应该分别缓存
        await cache.set(messages, "OpenAI response", "gpt-4", "openai")
        await cache.set(messages, "Claude response", "claude-3", "anthropic")

        result_openai = await cache.get(messages, "gpt-4", "openai")
        result_claude = await cache.get(messages, "claude-3", "anthropic")

        assert result_openai.response == "OpenAI response"
        assert result_claude.response == "Claude response"

    @pytest.mark.asyncio
    async def test_cache_hit_rate_tracking(self):
        """测试缓存命中率跟踪"""
        cache = LLMResponseCache()
        messages = [{"role": "user", "content": "Test"}]

        # 10 次请求，5 次命中
        for i in range(5):
            await cache.set(messages, f"Response{i}", "gpt-4", "openai")

        # 前 5 次未命中
        for _ in range(5):
            await cache.get(messages, "gpt-4", "openai")

        # 后 5 次命中
        for _ in range(5):
            await cache.get(messages, "gpt-4", "openai")

        stats = cache.get_stats()
        assert stats["miss_count"] == 5
        assert stats["hit_count"] == 5
        assert stats["hit_rate"] == 0.5
